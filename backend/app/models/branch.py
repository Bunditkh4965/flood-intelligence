from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import CheckConstraint, DateTime, Float, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Branch(Base):
    """A company branch with a geographic point for proximity searches."""

    __tablename__ = "branches"
    __table_args__ = (
        CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_branches_latitude_range"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_branches_longitude_range"),
        Index("ix_branches_location_gist", "location", postgresql_using="gist"),
        Index("ix_branches_store_number", "store_number", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    store_number: Mapped[str] = mapped_column(String(64), nullable=False)
    store_name: Mapped[str] = mapped_column(String(255), nullable=False)
    format: Mapped[str | None] = mapped_column(String(100))
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    location: Mapped[object] = mapped_column(Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False)
    business_hours: Mapped[str | None] = mapped_column(String(255))
    vehicle_type: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
