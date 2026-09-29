from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class HdmsIncident(Base):
    __tablename__ = "hdms_incidents"
    __table_args__ = (
        UniqueConstraint("source_record_id", name="uq_hdms_incidents_source_record_id"),
        CheckConstraint("road_status IN ('PASSABLE','IMPASSABLE','UNKNOWN')", name="ck_hdms_incidents_road_status"),
        CheckConstraint("road_geometry IS NULL OR GeometryType(road_geometry) = 'LINESTRING'", name="ck_hdms_incidents_linestring"),
        CheckConstraint("road_geometry IS NULL OR ST_SRID(road_geometry) = 4326", name="ck_hdms_incidents_geometry_srid"),
        CheckConstraint("geometry_available = (road_geometry IS NOT NULL)", name="ck_hdms_incidents_geometry_available"),
        Index("ix_hdms_incidents_active", "is_active"),
        Index("ix_hdms_incidents_road_section", "road_code", "section_code"),
        Index("ix_hdms_incidents_geometry_gist", "road_geometry", postgresql_using="gist"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    source_record_id: Mapped[str] = mapped_column(String(128), nullable=False)
    case_id: Mapped[str | None] = mapped_column(String(128))
    gid: Mapped[str | None] = mapped_column(String(128))
    road_code: Mapped[str | None] = mapped_column(String(32))
    section_code: Mapped[str | None] = mapped_column(String(32))
    section_name: Mapped[str | None] = mapped_column(String(255))
    km_start: Mapped[str | None] = mapped_column(String(32))
    km_end: Mapped[str | None] = mapped_column(String(32))
    province: Mapped[str | None] = mapped_column(String(128))
    amphoe: Mapped[str | None] = mapped_column(String(128))
    tambon: Mapped[str | None] = mapped_column(String(128))
    water_depth_cm: Mapped[float | None] = mapped_column(Float)
    road_status: Mapped[str] = mapped_column(String(16), nullable=False)
    incident_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    report_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    survey_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_status: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    road_geometry: Mapped[object | None] = mapped_column(Geometry("LINESTRING", srid=4326, spatial_index=False))
    geometry_available: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    source_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class HdmsSyncRun(Base):
    __tablename__ = "hdms_sync_runs"
    __table_args__ = (
        CheckConstraint("status IN ('RUNNING','SUCCESS','PARTIAL','FAILED')", name="ck_hdms_sync_status"),
        Index("ix_hdms_sync_started", "started_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    records_received: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    records_inserted: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    records_updated: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    records_unchanged: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    records_rejected: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    geometry_failures: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
