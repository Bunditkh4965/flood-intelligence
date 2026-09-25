from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import branch_flood_situation as api
from app.db.session import get_db
from app.main import app
from app.schemas.branch_flood_situation import SituationCategory
from app.services.branch_flood_situation import classify_situation


@pytest.mark.parametrize("gistda,public,ga,pa,expected", [
    ("DIRECT", "PUBLIC_NEARBY", True, True, "GISTDA_DIRECT"),
    ("NEARBY", "PUBLIC_NEARBY", True, True, "MULTI_SOURCE_NEARBY"),
    ("NEARBY", "PUBLIC_NONE", True, True, "GISTDA_NEARBY"),
    ("NONE", "PUBLIC_NEARBY", True, True, "PUBLIC_NEARBY"),
    ("NONE", "PUBLIC_NONE", True, True, "NO_NEARBY_FLOOD"),
    ("NONE", "PUBLIC_NEARBY", False, True, "SOURCE_DATA_INCOMPLETE"),
    ("NEARBY", "PUBLIC_NONE", True, False, "SOURCE_DATA_INCOMPLETE"),
    ("DIRECT", "PUBLIC_NONE", True, False, "GISTDA_DIRECT"),
])
def test_category_precedence(gistda, public, ga, pa, expected):
    assert classify_situation(gistda, public, ga, pa) == expected


ITEM = {
    "store_number": "2044", "store_name": "Test", "city": "Bangkok",
    "latitude": 13.75, "longitude": 100.5, "situation": "MULTI_SOURCE_NEARBY",
    "gistda": {"data_available": True, "period": "3DAYS", "classification": "NEARBY",
               "inside_flood_polygon": False, "nearest_flood_distance_km": 2,
               "nearest_flood_feature_id": 1},
    "public": {"data_available": True, "lookback_hours": 24,
               "classification": "PUBLIC_NEARBY", "nearest_report_code": "FR-1",
               "nearest_report_distance_km": 1, "nearest_report_verification_status": "VERIFIED",
               "nearest_report_reported_at": None},
}


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = lambda: object()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_collection_filter_pagination_and_unique_summary(client, monkeypatch):
    def calculate(db, period, gkm, pkm, hours, situation, limit, offset):
        assert (period, gkm, pkm, hours, situation, limit, offset) == (
            "3DAYS", 10, 5, 24, SituationCategory.MULTI_SOURCE_NEARBY, 1, 2)
        return SimpleNamespace(summary={"gistda_direct": 1, "multi_source_nearby": 1,
            "gistda_nearby": 1, "public_nearby": 1, "no_nearby_flood": 1,
            "source_data_incomplete": 1}, items=[ITEM])
    monkeypatch.setattr(api, "calculate_situations", calculate)
    response = client.get("/api/v1/branch-flood-situation?gistda_proximity_km=10"
        "&public_proximity_km=5&situation=MULTI_SOURCE_NEARBY&limit=1&offset=2")
    assert response.status_code == 200
    body = response.json()
    assert sum(body["summary"].values()) == 6
    assert len({item["store_number"] for item in body["items"]}) == len(body["items"])


def test_lookup_and_unknown(client, monkeypatch):
    monkeypatch.setattr(api, "calculate_situation", lambda *args: ITEM)
    assert client.get("/api/v1/branch-flood-situation/2044?gistda_proximity_km=10&public_proximity_km=5").json() == ITEM
    monkeypatch.setattr(api, "calculate_situation", lambda *args: None)
    assert client.get("/api/v1/branch-flood-situation/nope?gistda_proximity_km=10&public_proximity_km=5").status_code == 404


@pytest.mark.parametrize("query", ["", "?gistda_proximity_km=10", "?public_proximity_km=5",
    "?gistda_proximity_km=0&public_proximity_km=5",
    "?gistda_proximity_km=10&public_proximity_km=101",
    "?gistda_proximity_km=10&public_proximity_km=5&public_lookback_hours=0",
    "?gistda_proximity_km=10&public_proximity_km=5&period=2DAYS",
    "?gistda_proximity_km=10&public_proximity_km=5&situation=HIGH",
    "?gistda_proximity_km=10&public_proximity_km=5&limit=0",
    "?gistda_proximity_km=10&public_proximity_km=5&offset=-1"])
def test_parameter_validation(client, query):
    assert client.get("/api/v1/branch-flood-situation" + query).status_code == 422


def test_service_reuses_canonical_source_queries():
    from app.services.branch_flood_situation import _combined_query
    sql = _combined_query()
    assert "ST_Intersects" in sql and "ST_Distance" in sql
    assert sql.count("JOIN public_result p USING (store_number)") == 1
    assert "lower(b.status) = 'active'" in sql


def test_unavailable_source_does_not_invent_classification():
    from app.services.branch_flood_situation import _item
    row = {
        "store_number": "1", "store_name": "A", "city": "B", "latitude": 1,
        "longitude": 2, "situation": "SOURCE_DATA_INCOMPLETE",
        "impact_classification": "NONE", "inside_flood_polygon": False,
        "nearest_flood_distance_km": None, "nearest_flood_feature_id": None,
        "public_impact_classification": "PUBLIC_NONE", "nearest_report_code": None,
        "nearest_report_distance_km": None, "nearest_report_verification_status": None,
        "nearest_report_reported_at": None,
    }
    item = _item(row, "3DAYS", 24, False, False)
    assert item["gistda"]["classification"] is None
    assert item["public"]["classification"] is None
