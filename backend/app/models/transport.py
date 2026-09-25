from datetime import datetime

from geoalchemy2 import Geography, Geometry
from sqlalchemy import CheckConstraint, DateTime, Float, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DistributionCenter(Base):
    __tablename__ = "distribution_centers"
    __table_args__ = (
        CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_distribution_centers_latitude_range"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_distribution_centers_longitude_range"),
        CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_distribution_centers_status"),
        Index("ix_distribution_centers_dc_code", "dc_code", unique=True),
        Index("ix_distribution_centers_location_gist", "location", postgresql_using="gist"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    dc_code: Mapped[str] = mapped_column(String(64), nullable=False)
    dc_name: Mapped[str] = mapped_column(String(255), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    location: Mapped[object] = mapped_column(Geography("POINT", srid=4326, spatial_index=False), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class TransportRoute(Base):
    __tablename__ = "transport_routes"
    __table_args__ = (
        CheckConstraint("origin_type IN ('DC', 'BRANCH')", name="ck_transport_routes_origin_type"),
        CheckConstraint("destination_type IN ('DC', 'BRANCH')", name="ck_transport_routes_destination_type"),
        CheckConstraint("GeometryType(route_geometry) = 'LINESTRING'", name="ck_transport_routes_linear_geometry"),
        CheckConstraint("ST_SRID(route_geometry) = 4326", name="ck_transport_routes_geometry_srid"),
        CheckConstraint("distance_km >= 0", name="ck_transport_routes_distance"),
        CheckConstraint("duration_minutes >= 0", name="ck_transport_routes_duration"),
        Index("ix_transport_routes_geometry_gist", "route_geometry", postgresql_using="gist"),
        Index("ix_transport_routes_lookup", "origin_type", "origin_code", "destination_type", "destination_code", "vehicle_profile"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    route_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    origin_type: Mapped[str] = mapped_column(String(16), nullable=False)
    origin_code: Mapped[str] = mapped_column(String(64), nullable=False)
    destination_type: Mapped[str] = mapped_column(String(16), nullable=False)
    destination_code: Mapped[str] = mapped_column(String(64), nullable=False)
    vehicle_profile: Mapped[str] = mapped_column(String(16), nullable=False)
    distance_km: Mapped[float] = mapped_column(Float, nullable=False)
    duration_minutes: Mapped[float] = mapped_column(Float, nullable=False)
    route_geometry: Mapped[object] = mapped_column(Geometry("LINESTRING", srid=4326, spatial_index=False), nullable=False)
    routing_provider: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_route_id: Mapped[str | None] = mapped_column(String(255))
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
