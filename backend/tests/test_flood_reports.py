from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.models.flood_report import FloodReport
from app.schemas.flood_report import FloodReportCreate
from app.services.flood_reports import allocate_report_code, calculate_distance_m, serialize_report, verification_for


def valid_payload(**overrides):
    payload = {
        "flood_latitude": 14.123456, "flood_longitude": 100.567890,
        "reporter_latitude": 14.124000, "reporter_longitude": 100.568100,
        "reporter_gps_accuracy_m": 10, "water_level_cm": 35,
        "road_status": "PARTIAL", "vehicle_4w_status": "PASSABLE",
        "vehicle_6w_status": "UNKNOWN", "vehicle_10w_status": "BLOCKED", "has_photo": True,
    }
    payload.update(overrides)
    return payload


def test_valid_public_report_payload_keeps_map_and_gps_coordinates_separate() -> None:
    report = FloodReportCreate(**valid_payload())
    assert report.flood_latitude == 14.123456
    assert report.reporter_latitude == 14.124
    assert report.reporter_gps_accuracy_m == 10


@pytest.mark.parametrize("field,value", [
    ("flood_latitude", 91), ("flood_longitude", 181),
    ("reporter_latitude", -91), ("reporter_longitude", -181),
    ("reporter_gps_accuracy_m", -0.1), ("water_level_cm", -1),
    ("road_status", "CLOSED"), ("vehicle_4w_status", "PARTIAL"),
])
def test_invalid_public_report_values_are_rejected(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        FloodReportCreate(**valid_payload(**{field: value}))


def test_reporter_coordinates_must_be_provided_together() -> None:
    with pytest.raises(ValidationError):
        FloodReportCreate(**valid_payload(reporter_longitude=None))


@pytest.mark.parametrize(("gps", "photo", "distance", "expected"), [
    (True, True, 300, ("VERIFIED", "GPS_WITHIN_RADIUS_AND_PHOTO")),
    (True, True, 300.01, ("PENDING_REVIEW", "GPS_OUTSIDE_RADIUS_WITH_PHOTO")),
    (True, False, 10, ("PENDING_REVIEW", "GPS_WITHOUT_PHOTO")),
    (False, True, None, ("PENDING_REVIEW", "NO_REPORTER_GPS_WITH_PHOTO")),
    (False, False, None, ("UNVERIFIED", "NO_REPORTER_GPS_NO_PHOTO")),
])
def test_gps_photo_verification_rules(gps: bool, photo: bool, distance: float | None, expected: tuple[str, str]) -> None:
    assert verification_for(reporter_gps_available=gps, has_photo=photo, distance_m=distance, radius_m=300) == expected


def test_public_response_hides_internal_and_reporter_identity() -> None:
    report = FloodReport(
        id=99, report_code="FR-20260924-00001", flood_latitude=14.1, flood_longitude=100.5,
        reporter_latitude=14.1001, reporter_longitude=100.5001, reporter_gps_accuracy_m=8,
        water_level_cm=20, road_status="UNKNOWN", vehicle_4w_status="UNKNOWN", vehicle_6w_status="UNKNOWN",
        vehicle_10w_status="UNKNOWN", has_photo=True, verification_status="VERIFIED",
        verification_reason="GPS_WITHIN_RADIUS_AND_PHOTO", source="PUBLIC", status="ACTIVE",
        reported_at=datetime(2026, 9, 24, tzinfo=timezone.utc), flood_location="SRID=4326;POINT(100.5 14.1)",
    )
    response = serialize_report(report).model_dump()
    assert response["report_code"] == "FR-20260924-00001"
    assert response["flood_location"] == {"latitude": 14.1, "longitude": 100.5}
    assert "id" not in response and "reporter_id" not in response


def test_public_client_cannot_supply_an_internal_source() -> None:
    with pytest.raises(ValidationError):
        FloodReportCreate(**valid_payload(source="GISTDA"))


class _ScalarOne:
    def scalar_one(self) -> int:
        return 1


class _CodeSession:
    def execute(self, statement):  # type: ignore[no-untyped-def]
        self.statement = statement
        return _ScalarOne()


def test_report_code_generation_uses_daily_persisted_sequence() -> None:
    assert allocate_report_code(_CodeSession(), datetime(2026, 9, 24, tzinfo=timezone.utc)) == "FR-20260924-00001"


class _DistanceSession:
    def scalar(self, statement):  # type: ignore[no-untyped-def]
        self.statement = statement
        return 72.5


def test_distance_calculation_delegates_to_postgis_geography_distance() -> None:
    session = _DistanceSession()
    assert calculate_distance_m(session, reporter_latitude=14.124, reporter_longitude=100.5681, flood_latitude=14.123456, flood_longitude=100.56789) == 72.5
    assert "ST_Distance" in str(session.statement)
