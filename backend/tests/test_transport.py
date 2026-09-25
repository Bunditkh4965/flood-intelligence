from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.db.session import get_db
from app.main import app
from app.models.branch import Branch
from app.models.transport import DistributionCenter
from app.routing.provider import NoRoutingProvider, RouteProviderResult, RoutingProviderNotConfigured, get_routing_provider
from app.schemas.transport import DistributionCenterCreate, RouteCalculateRequest
from app.services.distribution_centers import DuplicateDistributionCenter, create_distribution_center


NOW = datetime(2026, 9, 25, tzinfo=timezone.utc)


def _dc(status: str = "ACTIVE") -> DistributionCenter:
    return DistributionCenter(dc_code="DC-01", dc_name="Central DC", latitude=13.75, longitude=100.5,
                              location="SRID=4326;POINT(100.5 13.75)", status=status, created_at=NOW, updated_at=NOW)


def _branch(status: str = "active") -> Branch:
    return Branch(store_number="1001", store_name="Branch", city="Bangkok", latitude=13.8, longitude=100.6,
                  location="SRID=4326;POINT(100.6 13.8)", status=status)


def _request(profile: str = "6W") -> dict:
    return {"origin": {"type": "DC", "code": "DC-01"},
            "destination": {"type": "BRANCH", "code": "1001"}, "vehicle_profile": profile}


def test_dc_coordinate_and_status_validation() -> None:
    with pytest.raises(ValidationError):
        DistributionCenterCreate(dc_code="X", dc_name="x", latitude=91, longitude=0)
    with pytest.raises(ValidationError):
        DistributionCenterCreate(dc_code="X", dc_name="x", latitude=0, longitude=-181)


def test_create_dc_builds_spatial_point_and_duplicate_is_rejected() -> None:
    db = Mock()
    db.scalar.return_value = None
    db.refresh.side_effect = lambda dc: (setattr(dc, "created_at", NOW), setattr(dc, "updated_at", NOW))
    created = create_distribution_center(db, DistributionCenterCreate(dc_code="DC-01", dc_name="Central", latitude=1, longitude=2))
    assert created.dc_code == "DC-01"
    db.add.assert_called_once()
    db.commit.assert_called_once()
    db.scalar.return_value = _dc()
    with pytest.raises(DuplicateDistributionCenter):
        create_distribution_center(db, DistributionCenterCreate(dc_code="DC-01", dc_name="Again", latitude=1, longitude=2))


def test_dc_list_detail_and_unknown(monkeypatch) -> None:
    from app.api import distribution_centers as api
    app.dependency_overrides[get_db] = lambda: object()
    monkeypatch.setattr(api, "list_distribution_centers", lambda db: [_dc()])
    monkeypatch.setattr(api, "get_distribution_center", lambda db, code: _dc() if code == "DC-01" else None)
    try:
        client = TestClient(app)
        assert client.get("/api/v1/distribution-centers").json()[0]["dc_code"] == "DC-01"
        assert client.get("/api/v1/distribution-centers/DC-01").status_code == 200
        response = client.get("/api/v1/distribution-centers/missing")
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "DC_NOT_FOUND"
    finally:
        app.dependency_overrides.clear()


def test_vehicle_profile_validation() -> None:
    with pytest.raises(ValidationError):
        RouteCalculateRequest.model_validate(_request("CAR"))


def test_route_endpoint_accepts_public_id_spelling() -> None:
    payload = _request()
    payload["origin"]["id"] = payload["origin"].pop("code")
    payload["destination"]["id"] = payload["destination"].pop("code")
    request = RouteCalculateRequest.model_validate(payload)
    assert request.origin.code == "DC-01"
    assert request.destination.code == "1001"


def test_no_provider_never_returns_geometry() -> None:
    with pytest.raises(RoutingProviderNotConfigured):
        NoRoutingProvider().calculate_route((100.5, 13.75), (100.6, 13.8), "6W")


def test_route_provider_invocation_normalization_and_provenance(monkeypatch) -> None:
    from app.services import routes
    provider = Mock()
    geometry = {"type": "LineString", "coordinates": [[100.5, 13.75], [100.6, 13.8]]}
    provider.calculate_route.return_value = RouteProviderResult(12.25, 31.5, geometry, "test-engine", "provider-42")
    monkeypatch.setattr(routes, "get_distribution_center", lambda db, code: _dc())
    monkeypatch.setattr(routes, "get_branch_by_store_number", lambda db, code: _branch())
    db = Mock()
    response = routes.calculate_and_store_route(db, RouteCalculateRequest.model_validate(_request()), provider)
    provider.calculate_route.assert_called_once_with((100.5, 13.75), (100.6, 13.8), "6W")
    persisted = db.add.call_args.args[0]
    assert (response.distance_km, response.duration_minutes, response.route_geometry) == (12.25, 31.5, geometry)
    assert (persisted.routing_provider, persisted.provider_route_id) == ("test-engine", "provider-42")


def test_provider_failure_does_not_persist(monkeypatch) -> None:
    from app.routing.provider import RoutingProviderConnectionError
    from app.services import routes
    monkeypatch.setattr(routes, "get_distribution_center", lambda db, code: _dc())
    monkeypatch.setattr(routes, "get_branch_by_store_number", lambda db, code: _branch())
    provider = Mock()
    provider.calculate_route.side_effect = RoutingProviderConnectionError("down")
    db = Mock()
    with pytest.raises(RoutingProviderConnectionError):
        routes.calculate_and_store_route(db, RouteCalculateRequest.model_validate(_request()), provider)
    db.add.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.parametrize("coordinates", [[], [[100.5, 13.75]], [[13.75, 100.5], [13.8, 100.6]]])
def test_route_rejects_invalid_linestring_without_persisting(monkeypatch, coordinates) -> None:
    from app.services import routes
    monkeypatch.setattr(routes, "get_distribution_center", lambda db, code: _dc())
    monkeypatch.setattr(routes, "get_branch_by_store_number", lambda db, code: _branch())
    provider = Mock()
    provider.calculate_route.return_value = RouteProviderResult(
        1, 1, {"type": "LineString", "coordinates": coordinates}, "test"
    )
    db = Mock()
    with pytest.raises(ValueError):
        routes.calculate_and_store_route(db, RouteCalculateRequest.model_validate(_request()), provider)
    db.add.assert_not_called()


@pytest.mark.parametrize("kind", ["inactive_dc", "unknown_branch", "inactive_branch"])
def test_route_rejects_unusable_locations(monkeypatch, kind: str) -> None:
    from app.services import routes
    monkeypatch.setattr(routes, "get_distribution_center", lambda db, code: _dc("INACTIVE") if kind == "inactive_dc" else _dc())
    monkeypatch.setattr(routes, "get_branch_by_store_number", lambda db, code: None if kind == "unknown_branch" else _branch("inactive" if kind == "inactive_branch" else "active"))
    with pytest.raises(routes.RouteLocationError):
        routes.calculate_and_store_route(Mock(), RouteCalculateRequest.model_validate(_request()), Mock())


def test_unconfigured_provider_api_is_explicit(monkeypatch) -> None:
    from app.services import routes
    monkeypatch.setattr(routes, "get_distribution_center", lambda db, code: _dc())
    monkeypatch.setattr(routes, "get_branch_by_store_number", lambda db, code: _branch())
    app.dependency_overrides[get_db] = lambda: Mock()
    app.dependency_overrides[get_routing_provider] = lambda: NoRoutingProvider()
    try:
        response = TestClient(app).post("/api/v1/routes/calculate", json=_request())
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "ROUTING_PROVIDER_NOT_CONFIGURED"
