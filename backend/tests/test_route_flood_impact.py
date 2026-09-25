from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import routes as api
from app.db.session import get_db
from app.main import app
from app.schemas.route_flood_impact import RouteFloodSituation
from app.services.route_flood_impact import (
    _GISTDA_SQL, _PUBLIC_SQL, InvalidRouteGeometry, classify_route_flood_impact,
)


@pytest.mark.parametrize("g,p,ga,pa,expected", [
    (True, True, True, True, "MULTI_SOURCE_ROUTE_IMPACT"),
    (True, False, True, False, "GISTDA_DIRECT"),
    (False, True, False, True, "PUBLIC_NEARBY_ROUTE"),
    (False, False, True, True, "NO_DETECTED_ROUTE_IMPACT"),
    (False, False, False, True, "SOURCE_DATA_INCOMPLETE"),
    (False, False, True, False, "SOURCE_DATA_INCOMPLETE"),
])
def test_factual_classification_precedence(g, p, ga, pa, expected):
    assert classify_route_flood_impact(g, p, ga, pa) == RouteFloodSituation(expected)


def test_spatial_sql_uses_real_route_and_index_friendly_postgis_operations():
    assert "ST_Intersects(f.geometry, r.route_geometry)" in _GISTDA_SQL
    assert "ST_Intersection(f.geometry, r.route_geometry)" in _GISTDA_SQL
    assert "ST_DWithin(p.flood_location, r.route_geometry::geography, :radius_meters)" in _PUBLIC_SQL
    assert "ST_Distance(p.flood_location, r.route_geometry::geography)" in _PUBLIC_SQL
    assert "verification_status = ANY" in _PUBLIC_SQL
    assert "ST_MakeLine" not in _GISTDA_SQL + _PUBLIC_SQL


def _result():
    return {"route_id": "r1", "origin": {"type": "DC", "code": "D1"},
      "destination": {"type": "BRANCH", "code": "B1"}, "vehicle_profile": "6W",
      "routing_provider": "VALHALLA", "distance_km": 10, "duration_minutes": 20,
      "calculated_at": "2026-09-25T00:00:00Z", "flood_situation": "NO_DETECTED_ROUTE_IMPACT",
      "gistda_evidence": [], "public_report_evidence": [],
      "public_route_impact_radius_meters": 300,
      "source_data_status": {"complete": True,
        "gistda": {"data_available": True, "evaluated_period_or_window": "3DAYS", "latest_source_at": None},
        "public": {"data_available": True, "evaluated_period_or_window": "24 hours", "latest_source_at": None}},
      "evaluated_at": "2026-09-25T01:00:00Z"}


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = lambda: object()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_route_impact_endpoint(client, monkeypatch):
    monkeypatch.setattr(api, "evaluate_route_flood_impact", lambda *args: _result())
    response = client.get("/api/v1/routes/r1/flood-impact")
    assert response.status_code == 200
    assert response.json()["routing_provider"] == "VALHALLA"


def test_nonexistent_route(client, monkeypatch):
    monkeypatch.setattr(api, "evaluate_route_flood_impact", lambda *args: None)
    response = client.get("/api/v1/routes/missing/flood-impact")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "ROUTE_NOT_FOUND"


def test_invalid_legacy_route_geometry(client, monkeypatch):
    def invalid(*args):
        raise InvalidRouteGeometry("bad")
    monkeypatch.setattr(api, "evaluate_route_flood_impact", invalid)
    response = client.get("/api/v1/routes/r1/flood-impact")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ROUTE_GEOMETRY_INVALID"
