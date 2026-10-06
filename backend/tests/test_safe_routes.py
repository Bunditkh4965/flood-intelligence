import math
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from app.models.branch import Branch
from app.models.transport import DistributionCenter
from app.routing.provider import RouteProviderResult
from app.schemas.transport import RouteSafetyState, SafeRouteCalculateRequest
from app.services import safe_routes


NOW = datetime(2026, 10, 5, tzinfo=timezone.utc)
REQUEST = SafeRouteCalculateRequest.model_validate({
    "origin": {"type": "DC", "code": "LLKDC"},
    "destination": {"type": "BRANCH", "code": "6591"},
    "vehicle_profile": "6W",
})


def _result(coordinates: list[list[float]]) -> RouteProviderResult:
    return RouteProviderResult(10, 20, {"type": "LineString", "coordinates": coordinates}, "test")


def _locations(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(safe_routes, "get_distribution_center", lambda *_: DistributionCenter(
        dc_code="LLKDC", dc_name="DC", latitude=13.0, longitude=100.0,
        location="POINT(100 13)", status="ACTIVE", created_at=NOW, updated_at=NOW,
    ))
    monkeypatch.setattr(safe_routes, "get_branch_by_store_number", lambda *_: Branch(
        store_number="6591", store_name="Branch", city="Chachoengsao",
        latitude=13.1, longitude=100.1, location="POINT(100.1 13.1)", status="ACTIVE",
    ))


class _Mappings:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def __iter__(self):
        return iter(self.rows)

    def one(self):
        return self.rows[0]


def _db(exclusions, final_blockers=(), evidence=(), availability=None):
    db = Mock()
    db.execute.side_effect = [
        _Mappings(exclusions), _Mappings(final_blockers), _Mappings(evidence),
        _Mappings([availability or {"hdms": True, "gistda": True, "bma": True, "public": True}]),
    ]
    return db


def _polygon(lon: float) -> dict:
    # About 1 km long and 40 m wide at this latitude; perimeter is about 2.1 km.
    return {"type": "Polygon", "coordinates": [[
        [lon, 13.0], [lon + .009, 13.0], [lon + .009, 13.00036],
        [lon, 13.00036], [lon, 13.0],
    ]]}


def _perimeter_m(ring: list[list[float]]) -> float:
    total = 0.0
    for first, second in zip(ring, ring[1:]):
        lat1, lat2 = map(math.radians, (first[1], second[1]))
        dlat = lat2 - lat1
        dlon = math.radians(second[0] - first[0])
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        total += 6_371_000 * 2 * math.asin(math.sqrt(a))
    return total


def test_exclusion_sql_uses_local_metric_substrings_not_full_road_buffer() -> None:
    sql = str(safe_routes._EXCLUSION_POLYGONS)
    assert "ST_LineLocatePoint" in sql
    assert "ST_LineSubstring" in sql
    assert "first_m - 500.0" in sql and "last_m + 500.0" in sql
    assert "ST_Buffer(segment, 20)" in sql
    assert "ST_Buffer(h.road_geometry" not in sql
    assert "greatest(0.0" in sql and "least(ST_Length(road)" in sql


def test_crossings_are_grouped_and_each_local_window_is_bounded() -> None:
    sql = str(safe_routes._EXCLUSION_POLYGONS)
    assert "floor(measure_m / 1000.0)" in sql
    assert "AS window_index" in sql
    assert "SELECT id, window," not in sql
    assert "ORDER BY id, window\n" not in sql
    assert "min(measure_m)" in sql and "max(measure_m)" in sql
    assert _perimeter_m(_polygon(100)["coordinates"][0]) < 10_000


def test_multiple_blockers_are_sent_as_lon_lat_exclusion_polygons(monkeypatch) -> None:
    _locations(monkeypatch)
    provider = Mock()
    provider.calculate_route.return_value = _result([[100, 13], [100.1, 13.1]])
    provider.calculate_route_avoiding.return_value = _result([[100, 13], [100.05, 13.2], [100.1, 13.1]])
    db = _db([{"id": 115, "window_index": 0, "polygon": _polygon(100.01)},
              {"id": 116, "window_index": 2, "polygon": _polygon(100.04)}])

    response = safe_routes.calculate_safe_route(db, REQUEST, provider, "1day", 100, 100)

    assert response.avoidance_attempted is True
    polygons = provider.calculate_route_avoiding.call_args.args[3]
    assert polygons == [_polygon(100.01)["coordinates"][0], _polygon(100.04)["coordinates"][0]]
    assert polygons[0][0] == [100.01, 13.0]
    assert response.safety_state is RouteSafetyState.SAFE


def test_reroute_is_revalidated_against_full_geometry_and_remains_blocked(monkeypatch) -> None:
    _locations(monkeypatch)
    provider = Mock()
    provider.calculate_route.return_value = _result([[100, 13], [100.1, 13.1]])
    provider.calculate_route_avoiding.return_value = _result([[100, 13], [100.1, 13.1]])
    blocker = {"id": 115, "section_name": "บางคล้า - แปลงยาว", "road_status": "IMPASSABLE"}
    db = _db([{"id": 115, "window_index": 0, "polygon": _polygon(100.01)}], [blocker], [
        {"source": "HDMS", "evidence_id": "115", "severity": "BLOCKING"},
    ])

    response = safe_routes.calculate_safe_route(db, REQUEST, provider, "1day", 100, 100)

    assert response.safety_state is RouteSafetyState.BLOCKED
    assert response.blocking_hazards == [blocker]
    calls = db.execute.call_args_list
    assert calls[0].args[0] is safe_routes._EXCLUSION_POLYGONS
    assert calls[1].args[0] is safe_routes._BLOCKERS
    assert "ST_Buffer" not in str(safe_routes._BLOCKERS)


@pytest.mark.parametrize(("evidence", "expected"), [
    ([], RouteSafetyState.SAFE),
    ([{"source": "GISTDA", "evidence_id": "x", "severity": "WARNING"}], RouteSafetyState.WARNING),
])
def test_clear_alternate_can_be_safe_or_warning(monkeypatch, evidence, expected) -> None:
    _locations(monkeypatch)
    provider = Mock()
    provider.calculate_route.return_value = _result([[100, 13], [100.1, 13.1]])
    provider.calculate_route_avoiding.return_value = _result([[100, 13], [100.05, 13.2], [100.1, 13.1]])
    response = safe_routes.calculate_safe_route(
        _db([{"id": 115, "window_index": 0, "polygon": _polygon(100.01)}], evidence=evidence),
        REQUEST, provider, "1day", 100, 100,
    )
    assert response.safety_state is expected


@pytest.mark.parametrize("blocked,available,warning,expected", [
    (True, False, True, RouteSafetyState.BLOCKED),
    (True, True, False, RouteSafetyState.BLOCKED),
    (False, False, True, RouteSafetyState.UNVERIFIED),
    (False, False, False, RouteSafetyState.UNVERIFIED),
    (False, True, True, RouteSafetyState.WARNING),
    (False, True, False, RouteSafetyState.SAFE),
])
def test_safety_state_precedence_regression(monkeypatch, blocked, available, warning, expected):
    _locations(monkeypatch)
    provider = Mock()
    provider.calculate_route.return_value = _result([[100, 13], [100.05, 13.05], [100.1, 13.1]])
    response = safe_routes.calculate_safe_route(
        _db([], final_blockers=[{"id": 115}] if blocked else [],
            evidence=[{"source": "GISTDA", "evidence_id": "x", "severity": "WARNING"}] if warning else [],
            availability={"hdms": available, "gistda": True, "bma": True, "public": True}),
        REQUEST, provider, "1DAY", 100, 100,
    )
    assert response.safety_state is expected
    assert response.avoidance_attempted is False
    assert response.navigation_waypoints == [[100.05, 13.05]]
    provider.calculate_route_avoiding.assert_not_called()
