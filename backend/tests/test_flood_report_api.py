from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api import flood_reports as api
from app.db.session import get_db
from app.main import app
from app.models.flood_report import FloodReport


def _report() -> FloodReport:
    return FloodReport(
        report_code="FR-20260924-00001", flood_latitude=14.1, flood_longitude=100.5,
        reporter_latitude=None, reporter_longitude=None, water_level_cm=10,
        road_status="UNKNOWN", vehicle_4w_status="UNKNOWN", vehicle_6w_status="UNKNOWN", vehicle_10w_status="UNKNOWN",
        has_photo=False, verification_status="UNVERIFIED", verification_reason="NO_REPORTER_GPS_NO_PHOTO",
        source="PUBLIC", status="ACTIVE", reported_at=datetime(2026, 9, 24, tzinfo=timezone.utc),
        flood_location="SRID=4326;POINT(100.5 14.1)",
    )


def test_get_public_report_by_code(monkeypatch) -> None:
    app.dependency_overrides[get_db] = lambda: object()
    monkeypatch.setattr(api, "get_report", lambda db, code: _report() if code == "FR-20260924-00001" else None)
    try:
        response = TestClient(app).get("/api/v1/flood-reports/FR-20260924-00001")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["report_code"] == "FR-20260924-00001"
    assert "id" not in response.json()
