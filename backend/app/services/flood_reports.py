from __future__ import annotations

from datetime import datetime, timezone

from geoalchemy2 import Geography
from sqlalchemy import cast, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core import get_settings
from app.models.flood_report import FloodReport, FloodReportCodeSequence, FloodReportPhoto, SystemConfiguration
from app.schemas.flood_report import FloodReportCreate, FloodReportRead, LocationRead

VERIFY_RADIUS_CONFIG_KEY = "REPORTER_GPS_VERIFY_RADIUS_M"
def _point(longitude: float, latitude: float):
    return cast(func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326), Geography(geometry_type="POINT", srid=4326))


def calculate_distance_m(db: Session, *, reporter_latitude: float, reporter_longitude: float, flood_latitude: float, flood_longitude: float) -> float:
    """Ask PostGIS to calculate ellipsoidal geography distance in metres."""
    return float(db.scalar(select(func.ST_Distance(_point(reporter_longitude, reporter_latitude), _point(flood_longitude, flood_latitude)))))


def get_verification_radius_m(db: Session) -> float:
    configured = db.scalar(select(SystemConfiguration.value).where(SystemConfiguration.key == VERIFY_RADIUS_CONFIG_KEY))
    if configured is None:
        return get_settings().reporter_gps_verify_radius_m
    try:
        value = float(configured)
    except (TypeError, ValueError):
        return get_settings().reporter_gps_verify_radius_m
    return value if value >= 0 else get_settings().reporter_gps_verify_radius_m


def verification_for(*, reporter_gps_available: bool, has_photo: bool, distance_m: float | None, radius_m: float) -> tuple[str, str]:
    if not reporter_gps_available:
        return ("PENDING_REVIEW", "NO_REPORTER_GPS_WITH_PHOTO") if has_photo else ("UNVERIFIED", "NO_REPORTER_GPS_NO_PHOTO")
    if not has_photo:
        return "PENDING_REVIEW", "GPS_WITHOUT_PHOTO"
    if distance_m is not None and distance_m <= radius_m:
        return "VERIFIED", "GPS_WITHIN_RADIUS_AND_PHOTO"
    return "PENDING_REVIEW", "GPS_OUTSIDE_RADIUS_WITH_PHOTO"


def allocate_report_code(db: Session, reported_at: datetime) -> str:
    report_date = reported_at.astimezone(timezone.utc).date() if reported_at.tzinfo else reported_at.date()
    statement = (
        insert(FloodReportCodeSequence)
        .values(report_date=report_date, last_value=1)
        .on_conflict_do_update(index_elements=[FloodReportCodeSequence.report_date], set_={"last_value": FloodReportCodeSequence.last_value + 1})
        .returning(FloodReportCodeSequence.last_value)
    )
    sequence = db.execute(statement).scalar_one()
    return f"FR-{report_date:%Y%m%d}-{sequence:05d}"


def create_public_report(db: Session, payload: FloodReportCreate) -> FloodReport:
    reported_at = payload.reported_at or datetime.now(timezone.utc)
    gps_available = payload.reporter_latitude is not None
    distance_m = None
    if gps_available:
        distance_m = calculate_distance_m(
            db, reporter_latitude=payload.reporter_latitude, reporter_longitude=payload.reporter_longitude,
            flood_latitude=payload.flood_latitude, flood_longitude=payload.flood_longitude,
        )
    verification_status, verification_reason = verification_for(
        reporter_gps_available=gps_available, has_photo=False, distance_m=distance_m, radius_m=get_verification_radius_m(db)
    )
    report = FloodReport(
        report_code=allocate_report_code(db, reported_at),
        reporter_latitude=payload.reporter_latitude, reporter_longitude=payload.reporter_longitude,
        reporter_location=(f"SRID=4326;POINT({payload.reporter_longitude} {payload.reporter_latitude})" if gps_available else None),
        reporter_gps_accuracy_m=payload.reporter_gps_accuracy_m,
        flood_latitude=payload.flood_latitude, flood_longitude=payload.flood_longitude,
        flood_location=f"SRID=4326;POINT({payload.flood_longitude} {payload.flood_latitude})",
        reporter_flood_distance_m=distance_m, water_level_cm=payload.water_level_cm,
        road_status=payload.road_status, vehicle_4w_status=payload.vehicle_4w_status,
        vehicle_6w_status=payload.vehicle_6w_status, vehicle_10w_status=payload.vehicle_10w_status,
        # Evidence is true only after the upload service has persisted accepted bytes.
        description=payload.description, has_photo=False,
        verification_status=verification_status, verification_reason=verification_reason,
        source="PUBLIC", status="ACTIVE", reported_at=reported_at,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def serialize_report(report: FloodReport) -> FloodReportRead:
    return FloodReportRead(
        report_code=report.report_code,
        flood_location=LocationRead(latitude=report.flood_latitude, longitude=report.flood_longitude),
        water_level_cm=report.water_level_cm,
        road_status=report.road_status, vehicle_4w_status=report.vehicle_4w_status,
        vehicle_6w_status=report.vehicle_6w_status, vehicle_10w_status=report.vehicle_10w_status,
        description=report.description, has_photo=report.has_photo, verification_status=report.verification_status,
        verification_reason=report.verification_reason, source=report.source, status=report.status,
        reported_at=report.reported_at,
    )


def list_reports(db: Session, *, status: str | None = None, verification_status: str | None = None, reported_from: datetime | None = None, reported_to: datetime | None = None, min_latitude: float | None = None, max_latitude: float | None = None, min_longitude: float | None = None, max_longitude: float | None = None) -> list[FloodReport]:
    query = select(FloodReport)
    if status: query = query.where(FloodReport.status == status)
    if verification_status: query = query.where(FloodReport.verification_status == verification_status)
    if reported_from: query = query.where(FloodReport.reported_at >= reported_from)
    if reported_to: query = query.where(FloodReport.reported_at <= reported_to)
    if min_latitude is not None: query = query.where(FloodReport.flood_latitude >= min_latitude)
    if max_latitude is not None: query = query.where(FloodReport.flood_latitude <= max_latitude)
    if min_longitude is not None: query = query.where(FloodReport.flood_longitude >= min_longitude)
    if max_longitude is not None: query = query.where(FloodReport.flood_longitude <= max_longitude)
    return list(db.scalars(query.order_by(FloodReport.reported_at.desc())))


def get_report(db: Session, report_code: str) -> FloodReport | None:
    return db.scalar(select(FloodReport).where(FloodReport.report_code == report_code))


def record_photo_and_recalculate(db: Session, report: FloodReport, *, storage_key: str, content_type: str, file_size: int) -> FloodReport:
    """Attach persisted evidence and re-run the authoritative verification rule."""
    db.add(FloodReportPhoto(flood_report_id=report.id, storage_key=storage_key, content_type=content_type, file_size=file_size))
    report.has_photo = True
    report.verification_status, report.verification_reason = verification_for(
        reporter_gps_available=report.reporter_latitude is not None,
        has_photo=True,
        distance_m=report.reporter_flood_distance_m,
        radius_m=get_verification_radius_m(db),
    )
    db.commit()
    db.refresh(report)
    return report
