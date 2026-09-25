from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import public_flood_impact as api
from app.db.session import get_db
from app.main import app
from app.schemas.public_flood_impact import PublicImpactClassification


ITEM = {
    "store_number": "2044", "store_name": "Test Branch", "city": "Bangkok",
    "latitude": 13.75, "longitude": 100.5, "branch_status": "active",
    "public_impact_classification": "PUBLIC_NEARBY",
    "nearest_report_code": "FR-20260925-00001", "nearest_report_distance_km": 1.2,
    "nearest_report_verification_status": "VERIFIED",
    "nearest_report_reported_at": datetime(2026, 9, 25, tzinfo=timezone.utc),
    "source": "PUBLIC",
}


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = lambda: object()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_list_metadata_filter_and_pagination(client, monkeypatch) -> None:
    def calculate(db, proximity, lookback, classification, limit, offset):
        assert (proximity, lookback, classification, limit, offset) == (
            5, 48, PublicImpactClassification.PUBLIC_NEARBY, 25, 5)
        return SimpleNamespace(data_available=True, summary={"nearby": 1, "none": 2}, items=[ITEM])
    monkeypatch.setattr(api, "calculate_public_branch_impacts", calculate)
    response = client.get(
        "/api/v1/public-flood-impact/branches?proximity_km=5&lookback_hours=48"
        "&classification=PUBLIC_NEARBY&limit=25&offset=5"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "PUBLIC"
    assert body["proximity_km"] == 5
    assert body["lookback_hours"] == 48
    assert body["summary"] == {"nearby": 1, "none": 2}
    assert len(body["items"]) == 1


@pytest.mark.parametrize("value", ["0", "-1", "101"])
def test_proximity_validation(client, value) -> None:
    assert client.get(f"/api/v1/public-flood-impact/branches?proximity_km={value}").status_code == 422


@pytest.mark.parametrize("value", ["0", "-1", "169"])
def test_lookback_validation(client, value) -> None:
    response = client.get(f"/api/v1/public-flood-impact/branches?proximity_km=5&lookback_hours={value}")
    assert response.status_code == 422


def test_proximity_is_required_and_classification_is_validated(client) -> None:
    assert client.get("/api/v1/public-flood-impact/branches").status_code == 422
    assert client.get(
        "/api/v1/public-flood-impact/branches?proximity_km=5&classification=DIRECT"
    ).status_code == 422


def test_no_eligible_data_is_explicit(client, monkeypatch) -> None:
    monkeypatch.setattr(api, "calculate_public_branch_impacts", lambda *args: SimpleNamespace(
        data_available=False, summary={"nearby": 0, "none": 3}, items=[]))
    body = client.get("/api/v1/public-flood-impact/branches?proximity_km=5").json()
    assert body["data_available"] is False
    assert body["summary"] == {"nearby": 0, "none": 3}


def test_branch_lookup_and_unknown_branch(client, monkeypatch) -> None:
    monkeypatch.setattr(api, "calculate_public_branch_impact", lambda *args: (True, ITEM))
    response = client.get("/api/v1/public-flood-impact/branches/2044?proximity_km=5")
    assert response.status_code == 200
    assert response.json()["item"]["store_number"] == "2044"
    monkeypatch.setattr(api, "calculate_public_branch_impact", lambda *args: None)
    assert client.get("/api/v1/public-flood-impact/branches/missing?proximity_km=5").status_code == 404


def test_sql_uses_selected_flood_location_and_public_eligibility() -> None:
    from app.services.public_flood_impact import _PUBLIC_IMPACT_CTE
    assert "source = 'PUBLIC'" in _PUBLIC_IMPACT_CTE
    assert "status = 'ACTIVE'" in _PUBLIC_IMPACT_CTE
    assert "verification_status = ANY" in _PUBLIC_IMPACT_CTE
    assert "reported_at >= :reported_from" in _PUBLIC_IMPACT_CTE
    assert "r.flood_location <-> b.location" in _PUBLIC_IMPACT_CTE
    assert "ST_Distance(b.location, nearest.flood_location)" in _PUBLIC_IMPACT_CTE
    assert "reporter_location" not in _PUBLIC_IMPACT_CTE
    assert "LIMIT 1" in _PUBLIC_IMPACT_CTE
    assert "DIRECT" not in _PUBLIC_IMPACT_CTE
