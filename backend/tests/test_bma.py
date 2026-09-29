from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import bma as api
from app.core import Settings
from app.db.session import get_db
from app.integrations.bma.client import BmaAPIError, BmaClient
from app.main import app
from app.schemas.evidence import EvidenceSource, EvidenceType
from app.services.bma import normalized_evidence, parse_observation


def feature(**attributes):
    base = {"MASTER_STATION_ID": "M1", "STATION_ID": "S1", "DATA_DT": "2026-09-29 09:50:00",
            "WATER_LEVEL_CM": 0, "ROAD_NAME": "ถนนรัชดาภิเษก", "CHK_STATUSTXT": "ปกติ"}
    base.update(attributes)
    return {"attributes": base, "geometry": {"points": [[100.57528, 13.80870]]}}


def test_arcgis_pagination_and_query_contract():
    offsets = []
    def handler(request):
        offsets.append(request.url.params["resultOffset"])
        assert request.url.params["returnGeometry"] == "true"
        assert request.url.params["outSR"] == "4326"
        return httpx.Response(200, json={"features": [feature()], "exceededTransferLimit": len(offsets) == 1})
    settings = Settings(_env_file=None, BMA_BASE_URL="https://example.test/FeatureServer/1")
    with BmaClient(settings, httpx.MockTransport(handler)) as client:
        assert len(list(client.pages(page_size=1))) == 2
    assert offsets == ["0", "1"]


def test_arcgis_error_is_clean():
    client = BmaClient(Settings(_env_file=None, BMA_BASE_URL="https://example.test"),
                       httpx.MockTransport(lambda request: httpx.Response(200, json={"error": {"message": "detail"}})))
    with pytest.raises(BmaAPIError) as exc:
        list(client.pages())
    assert "detail" not in str(exc.value)


def test_field_and_multipoint_parsing_preserves_lon_lat_order():
    parsed = parse_observation(feature(STATION_NAME_TH="station", FLOOD_MAX="12.5"))
    assert parsed.source_record_id == "master:M1"
    assert (parsed.longitude, parsed.latitude) == (100.57528, 13.8087)
    assert parsed.values["water_level_cm"] == 0
    assert parsed.values["flood_max_cm"] == 12.5
    assert parsed.values["observed_at"] == datetime(2026, 9, 29, 9, 50)
    assert parsed.values["observed_at"].tzinfo is None


def test_explicit_timestamp_offset_is_preserved():
    parsed = parse_observation(feature(DATA_DT="2026-09-29T09:50:00+07:00"))
    assert parsed.values["observed_at"].utcoffset().total_seconds() == 7 * 3600


def test_stable_identity_preference_and_fallbacks():
    assert parse_observation(feature(MASTER_STATION_ID="M", STATION_ID="S", OBJECTID=1)).source_record_id == "master:M"
    assert parse_observation(feature(MASTER_STATION_ID=None, STATION_ID="S", OBJECTID=1)).source_record_id == "station:S"
    assert parse_observation(feature(MASTER_STATION_ID=None, STATION_ID=None,
                                     OBJECTID=1, OBJECTID_1=2)).source_record_id == "object:1:2"


def test_lat_lng_fallback_only_when_both_valid():
    item = feature(LAT="13.8", F_LNG="100.5")
    item["geometry"] = {"points": [["bad", 13]]}
    parsed = parse_observation(item)
    assert (parsed.longitude, parsed.latitude) == (100.5, 13.8)


@pytest.mark.parametrize("geometry,attrs", [
    ({"points": []}, {}), ({"points": [[13, 101]]}, {"LAT": 13}), (None, {"F_LNG": 100}),
])
def test_invalid_location_is_rejected(geometry, attrs):
    item = feature(**attrs); item["geometry"] = geometry
    with pytest.raises(ValueError, match="location"):
        parse_observation(item)


def test_normalized_bma_evidence_is_water_level_not_official_status():
    row = SimpleNamespace(api_source="DDS", source_record_id="master:M1", source_longitude=100.5,
        source_latitude=13.8, observed_at=datetime.now(timezone.utc), source_updated_at=None,
        water_level_cm=5, source_status="ปกติ", road_name="Road", station_name="Station")
    evidence = normalized_evidence(row)
    assert evidence.source == EvidenceSource.BMA
    assert evidence.evidence_type == EvidenceType.WATER_LEVEL
    assert evidence.official_status is False
    assert evidence.road_status is None


def _api_row():
    now = datetime(2026, 9, 29, tzinfo=timezone.utc)
    return SimpleNamespace(id=1, source_record_id="master:M1", master_station_id="M1", station_id="S1",
        station_name="Station", station_old_code=None, road_name="Road", tunnel_description=None,
        water_level_cm=5, source_status="ปกติ", observed_at=datetime(2026, 9, 29, 9, 50),
        flood_start_at=None, flood_stop_at=None, flood_max_cm=None, flood_max_at=None,
        agency="BMA", api_source="DDS", province="Bangkok", amphoe=None, tambon=None,
        source_latitude=13.8, source_longitude=100.5, source_created_at=None,
        source_updated_at=None, is_active=True, synced_at=now, created_at=now, updated_at=now)


def test_read_only_api_filters_and_detail(monkeypatch):
    captured = []
    app.dependency_overrides[get_db] = lambda: SimpleNamespace(
        get=lambda model, item_id: _api_row() if item_id == 1 else None)
    monkeypatch.setattr(api, "list_observations", lambda *args: captured.append(args) or [_api_row()])
    try:
        client = TestClient(app)
        response = client.get("/api/v1/bma/road-water", params={
            "active": "false", "status": "ปกติ", "road_name": "Road",
            "minimum_water_level": 3, "limit": 25, "offset": 5,
        })
        assert response.status_code == 200 and response.json()[0]["source_record_id"] == "master:M1"
        assert captured[0][1:] == (False, "ปกติ", "Road", 3.0, 25, 5)
        assert client.get("/api/v1/bma/road-water/1").status_code == 200
        missing = client.get("/api/v1/bma/road-water/2")
        assert missing.status_code == 404
        assert missing.json()["detail"]["code"] == "BMA_OBSERVATION_NOT_FOUND"
    finally:
        app.dependency_overrides.clear()
