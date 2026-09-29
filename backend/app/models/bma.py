from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BmaRoadWaterObservation(Base):
    __tablename__ = "bma_road_water_observations"
    __table_args__ = (
        UniqueConstraint("source_record_id", name="uq_bma_road_water_source_record_id"),
        CheckConstraint("GeometryType(location) = 'POINT' AND ST_SRID(location) = 4326", name="ck_bma_road_water_location"),
        Index("ix_bma_road_water_active", "is_active"),
        Index("ix_bma_road_water_road", "road_name"),
        Index("ix_bma_road_water_location_gist", "location", postgresql_using="gist"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    source_record_id: Mapped[str] = mapped_column(String(128), nullable=False)
    master_station_id: Mapped[str | None] = mapped_column(String(128))
    station_id: Mapped[str | None] = mapped_column(String(128))
    object_id: Mapped[str | None] = mapped_column(String(128))
    object_id_1: Mapped[str | None] = mapped_column(String(128))
    station_name: Mapped[str | None] = mapped_column(String(255))
    station_old_code: Mapped[str | None] = mapped_column(String(128))
    road_name: Mapped[str | None] = mapped_column(String(255))
    tunnel_description: Mapped[str | None] = mapped_column(String(255))
    water_level_cm: Mapped[float | None] = mapped_column(Float)
    source_status: Mapped[str | None] = mapped_column(String(128))
    # Source wall-clock values are deliberately timestamp-without-time-zone:
    # BMA does not identify a timezone for these fields.
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    flood_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    flood_stop_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    flood_max_cm: Mapped[float | None] = mapped_column(Float)
    flood_max_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    agency: Mapped[str | None] = mapped_column(String(255))
    api_source: Mapped[str | None] = mapped_column(String(64))
    province: Mapped[str | None] = mapped_column(String(128))
    amphoe: Mapped[str | None] = mapped_column(String(128))
    tambon: Mapped[str | None] = mapped_column(String(128))
    source_latitude: Mapped[float] = mapped_column(Float, nullable=False)
    source_longitude: Mapped[float] = mapped_column(Float, nullable=False)
    location: Mapped[object] = mapped_column(Geometry("POINT", srid=4326, spatial_index=False), nullable=False)
    source_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    source_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class BmaSyncRun(Base):
    __tablename__ = "bma_sync_runs"
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
    page_failures: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
