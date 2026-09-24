"""Persistence models for public flood reports and their future photo metadata."""

from datetime import date, datetime

from geoalchemy2 import Geography
from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FloodReport(Base):
    __tablename__ = "flood_reports"
    __table_args__ = (
        CheckConstraint("flood_latitude BETWEEN -90 AND 90", name="ck_flood_reports_flood_latitude_range"),
        CheckConstraint("flood_longitude BETWEEN -180 AND 180", name="ck_flood_reports_flood_longitude_range"),
        CheckConstraint("reporter_latitude IS NULL OR reporter_latitude BETWEEN -90 AND 90", name="ck_flood_reports_reporter_latitude_range"),
        CheckConstraint("reporter_longitude IS NULL OR reporter_longitude BETWEEN -180 AND 180", name="ck_flood_reports_reporter_longitude_range"),
        CheckConstraint("reporter_gps_accuracy_m IS NULL OR reporter_gps_accuracy_m >= 0", name="ck_flood_reports_gps_accuracy"),
        CheckConstraint("water_level_cm >= 0", name="ck_flood_reports_water_level"),
        CheckConstraint("road_status IN ('PASSABLE', 'PARTIAL', 'BLOCKED', 'UNKNOWN')", name="ck_flood_reports_road_status"),
        CheckConstraint("vehicle_4w_status IN ('PASSABLE', 'BLOCKED', 'UNKNOWN')", name="ck_flood_reports_vehicle_4w_status"),
        CheckConstraint("vehicle_6w_status IN ('PASSABLE', 'BLOCKED', 'UNKNOWN')", name="ck_flood_reports_vehicle_6w_status"),
        CheckConstraint("vehicle_10w_status IN ('PASSABLE', 'BLOCKED', 'UNKNOWN')", name="ck_flood_reports_vehicle_10w_status"),
        CheckConstraint("verification_status IN ('VERIFIED', 'PENDING_REVIEW', 'UNVERIFIED')", name="ck_flood_reports_verification_status"),
        CheckConstraint("source IN ('PUBLIC', 'COMPANY', 'GISTDA', 'SYSTEM')", name="ck_flood_reports_source"),
        CheckConstraint("status IN ('ACTIVE', 'REVIEWED', 'REJECTED', 'CLOSED')", name="ck_flood_reports_status"),
        Index("ix_flood_reports_flood_location_gist", "flood_location", postgresql_using="gist"),
        Index("ix_flood_reports_reporter_location_gist", "reporter_location", postgresql_using="gist"),
        Index("ix_flood_reports_reported_at", "reported_at"),
        Index("ix_flood_reports_status_verification", "status", "verification_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    report_code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    reporter_id: Mapped[int | None] = mapped_column(nullable=True)  # Reserved for a future authenticated reporter model.
    reporter_latitude: Mapped[float | None] = mapped_column(Float)
    reporter_longitude: Mapped[float | None] = mapped_column(Float)
    reporter_location: Mapped[object | None] = mapped_column(Geography(geometry_type="POINT", srid=4326, spatial_index=False))
    reporter_gps_accuracy_m: Mapped[float | None] = mapped_column(Float)
    flood_latitude: Mapped[float] = mapped_column(Float, nullable=False)
    flood_longitude: Mapped[float] = mapped_column(Float, nullable=False)
    flood_location: Mapped[object] = mapped_column(Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False)
    reporter_flood_distance_m: Mapped[float | None] = mapped_column(Float)
    water_level_cm: Mapped[float] = mapped_column(Float, nullable=False)
    road_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="UNKNOWN")
    vehicle_4w_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="UNKNOWN")
    vehicle_6w_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="UNKNOWN")
    vehicle_10w_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="UNKNOWN")
    description: Mapped[str | None] = mapped_column(Text)
    has_photo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    verification_status: Mapped[str] = mapped_column(String(20), nullable=False)
    verification_reason: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default="PUBLIC")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="ACTIVE")
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class FloodReportPhoto(Base):
    """Metadata only; image bytes remain in external object storage when added."""

    __tablename__ = "flood_report_photos"
    id: Mapped[int] = mapped_column(primary_key=True)
    flood_report_id: Mapped[int] = mapped_column(ForeignKey("flood_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    content_type: Mapped[str | None] = mapped_column(String(100))
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class FloodReportCodeSequence(Base):
    """One atomic counter per UTC report date for human-readable report codes."""

    __tablename__ = "flood_report_code_sequences"
    report_date: Mapped[date] = mapped_column(Date, primary_key=True)
    last_value: Mapped[int] = mapped_column(Integer, nullable=False)


class SystemConfiguration(Base):
    __tablename__ = "system_configurations"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
