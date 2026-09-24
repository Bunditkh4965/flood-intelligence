from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

PERIODS = ("1DAY", "3DAYS", "7DAYS", "30DAYS")


class GistdaFloodFeature(Base):
    __tablename__ = "gistda_flood_features"
    __table_args__ = (
        CheckConstraint("period IN ('1DAY','3DAYS','7DAYS','30DAYS')", name="ck_gistda_features_period"),
        CheckConstraint("source = 'GISTDA'", name="ck_gistda_features_source"),
        UniqueConstraint("period", "source_hash", name="uq_gistda_features_period_hash"),
        Index("ix_gistda_features_geometry_gist", "geometry", postgresql_using="gist"),
        Index("ix_gistda_features_period_active", "period", "is_active"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    external_feature_id: Mapped[str | None] = mapped_column(String(255))
    period: Mapped[str] = mapped_column(String(10), nullable=False)
    geometry: Mapped[object] = mapped_column(Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default="GISTDA")
    source_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_properties: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class GistdaSyncRun(Base):
    __tablename__ = "gistda_sync_runs"
    __table_args__ = (
        CheckConstraint("period IN ('1DAY','3DAYS','7DAYS','30DAYS')", name="ck_gistda_sync_period"),
        CheckConstraint("status IN ('RUNNING','SUCCESS','PARTIAL','FAILED')", name="ck_gistda_sync_status"),
        Index("ix_gistda_sync_period_started", "period", "started_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    period: Mapped[str] = mapped_column(String(10), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    records_received: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    records_inserted: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    records_updated: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    records_unchanged: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    records_rejected: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
