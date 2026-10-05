from datetime import date, datetime, timezone
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import hdms as api
from app.core import Settings
from app.db.session import get_db
from app.integrations.hdms.client import HdmsAPIError, HdmsClient
from app.main import app
from app.services.hdms import normalize_road_status, parse_incident, parse_linestring


@pytest.mark.parametrize(("value", "expected"), [
    (True, "PASSABLE"), (False, "IMPASSABLE"), (None, "UNKNOWN"), ("false", "UNKNOWN"),
])
def test_lane_closure_semantics(value, expected):
    assert normalize_road_status(value) == expected


def test_vehicle_depth_policy_has_no_default_safety_thresholds():
    assert Settings(_env_file=None).vehicle_water_depth_thresholds_cm == {}


def test_incident_parsing_is_defensive_and_case_id_is_preferred():
    parsed = parse_incident({
        "case_id": 123, "gid": 9, "lane_closure": False, "flood_level": "17.5",
        "start_date": "2026-09-29T03:00:00Z", "unexpected": "not persisted",
    })
    assert parsed.source_record_id == "case:123"
    assert parsed.values["road_status"] == "IMPASSABLE"
    assert parsed.values["water_depth_cm"] == 17.5
    assert parsed.values["incident_at"] == datetime(2026, 9, 29, 3, tzinfo=timezone.utc)
    assert "unexpected" not in parsed.values["source_metadata"]


def test_fallback_identity_is_stable():
    record = {"road_code": "0033", "section_code": "0602", "km_start": "210+015",
              "km_end": "210+115", "start_date": "2026-09-29"}
    assert parse_incident(record).source_record_id == parse_incident(record).source_record_id
    assert parse_incident(record).source_record_id.startswith("fallback:")


def test_valid_linestring_preserves_geojson_longitude_latitude_order():
    geometry = parse_linestring({"geom": {"type": "LineString", "coordinates": [
        [101.85006578736844, 13.969482211375093], [101.85094188237831, 13.96919448296341],
    ]}})
    assert geometry["coordinates"][0] == [101.85006578736844, 13.969482211375093]


@pytest.mark.parametrize("payload", [
    {}, {"geom": None}, {"geom": {"type": "Point", "coordinates": [101, 13]}},
    {"geom": {"type": "LineString", "coordinates": [[101, 13]]}},
    {"geom": {"type": "LineString", "coordinates": [[13, 101], [14, 102]]}},
])
def test_invalid_geometry_is_rejected_not_fabricated(payload):
    with pytest.raises(ValueError):
        parse_linestring(payload)


def test_client_uses_public_dashboard_and_sequential_geometry_endpoint():
    paths = []
    def handler(request: httpx.Request):
        paths.append(request.url.path)
        assert "authorization" not in request.headers
        if request.url.path.endswith("/public/dashboard"):
            assert request.url.params["status"] == "open"
            return httpx.Response(200, json=[])
        return httpx.Response(200, json={"geom": {"type": "LineString", "coordinates": [[100, 13], [101, 14]]}})
    settings = Settings(_env_file=None, HDMS_BASE_URL="https://example.test/internal-api", HDMS_TIMEOUT_SECONDS=7)
    with HdmsClient(settings, httpx.MockTransport(handler)) as client:
        assert client.fetch_dashboard(date(2026, 9, 1), date(2026, 9, 29)) == []
        client.fetch_section_geometry("0033", "0602", "210+015", "210+115")
    assert paths == ["/internal-api/public/dashboard", "/internal-api/section_part/section-km"]


def test_client_failure_does_not_include_upstream_body():
    client = HdmsClient(Settings(_env_file=None, HDMS_BASE_URL="https://example.test"),
                        httpx.MockTransport(lambda request: httpx.Response(500, text="sensitive")))
    with pytest.raises(HdmsAPIError) as error:
        client.fetch_dashboard(date.today(), date.today())
    assert "sensitive" not in str(error.value)


def _row():
    now = datetime(2026, 9, 29, tzinfo=timezone.utc)
    return SimpleNamespace(id=1, source_record_id="case:C1", case_id="C1", gid=None,
        road_code="0033", section_code="0602", section_name="Road", km_start="1+000", km_end="1+100",
        province="Bangkok", amphoe=None, tambon=None, water_depth_cm=10, road_status="PASSABLE",
        incident_at=now, report_at=now, source_updated_at=now, survey_at=None, source_status="open",
        is_active=True, geometry_available=True, synced_at=now, created_at=now, updated_at=now)


def test_read_only_incident_endpoints(monkeypatch):
    app.dependency_overrides[get_db] = lambda: object()
    record = vars(_row()) | {"road_geometry": {
        "type": "LineString", "coordinates": [[100.5, 13.5], [100.6, 13.6]],
    }}
    monkeypatch.setattr(api, "list_incident_records", lambda db, active: [record])
    monkeypatch.setattr(api, "get_incident_record", lambda db, incident_id: record if incident_id == 1 else None)
    try:
        client = TestClient(app)
        response = client.get("/api/v1/hdms/incidents")
        assert response.status_code == 200
        assert response.json()[0]["geometry_available"] is True
        assert response.json()[0]["road_geometry"]["coordinates"][0] == [100.5, 13.5]
        assert "source_metadata" not in response.json()[0]
        assert client.get("/api/v1/hdms/incidents/999").status_code == 404
    finally:
        app.dependency_overrides.clear()
