from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import flood_impact as api
from app.db.session import get_db
from app.main import app
from app.schemas.flood_impact import ImpactClassification


ITEM = {
    "store_number": "2044", "store_name": "Test Branch", "city": "Bangkok",
    "latitude": 13.75, "longitude": 100.5, "branch_status": "active",
    "impact_classification": "NEARBY", "inside_flood_polygon": False,
    "nearest_flood_distance_km": 8.93, "nearest_flood_feature_id": 10,
    "gistda_period": "3DAYS",
}


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = lambda: object()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_list_endpoint_metadata_filter_and_pagination(client, monkeypatch) -> None:
    def calculate(db, period, proximity, classification, limit, offset):
        assert (period, proximity, classification, limit, offset) == (
            "3DAYS", 10, ImpactClassification.NEARBY, 25, 5)
        return SimpleNamespace(data_available=True, summary={"direct": 0, "nearby": 1, "none": 2573}, items=[ITEM])
    monkeypatch.setattr(api, "calculate_branch_impacts", calculate)
    response = client.get("/api/v1/flood-impact/branches?period=3DAYS&proximity_km=10&classification=NEARBY&limit=25&offset=5")
    assert response.status_code == 200
    assert response.json()["summary"] == {"direct": 0, "nearby": 1, "none": 2573}
    assert response.json()["items"] == [ITEM]


@pytest.mark.parametrize("value", ["0", "-1", "501"])
def test_proximity_validation(client, value) -> None:
    assert client.get(f"/api/v1/flood-impact/branches?proximity_km={value}").status_code == 422


def test_period_and_classification_validation(client) -> None:
    assert client.get("/api/v1/flood-impact/branches?period=2DAYS").status_code == 422
    assert client.get("/api/v1/flood-impact/branches?classification=IMPACTED").status_code == 422


def test_no_active_data_is_explicit(client, monkeypatch) -> None:
    monkeypatch.setattr(api, "calculate_branch_impacts", lambda *args: SimpleNamespace(
        data_available=False, summary={"direct": 0, "nearby": 0, "none": 2574}, items=[]))
    body = client.get("/api/v1/flood-impact/branches").json()
    assert body["data_available"] is False
    assert body["summary"]["none"] == 2574


def test_branch_specific_lookup(client, monkeypatch) -> None:
    monkeypatch.setattr(api, "calculate_branch_impact", lambda *args: (True, ITEM))
    response = client.get("/api/v1/flood-impact/branches/2044?period=3DAYS&proximity_km=10")
    assert response.status_code == 200
    assert response.json()["item"]["store_number"] == "2044"


def test_unknown_branch_returns_404(client, monkeypatch) -> None:
    monkeypatch.setattr(api, "calculate_branch_impact", lambda *args: None)
    response = client.get("/api/v1/flood-impact/branches/missing")
    assert response.status_code == 404


def test_service_sql_encodes_spatial_business_rules() -> None:
    from app.services.flood_impact import _IMPACT_CTE
    assert "is_active IS TRUE" in _IMPACT_CTE
    assert "period = :period" in _IMPACT_CTE
    assert "ST_Intersects" in _IMPACT_CTE
    assert "ST_Distance" in _IMPACT_CTE
    assert "geometry::geography <-> b.location" in _IMPACT_CTE
    assert "LIMIT 1" in _IMPACT_CTE
    assert "WHEN inside_flood_polygon THEN 'DIRECT'" in _IMPACT_CTE
    assert "nearest_flood_distance_km <= :proximity_km THEN 'NEARBY'" in _IMPACT_CTE
