"""create distribution center and transport route foundation"""

from alembic import op
import geoalchemy2
import sqlalchemy as sa

revision = "20260925_0007"
down_revision = "20260925_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "distribution_centers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dc_code", sa.String(64), nullable=False),
        sa.Column("dc_name", sa.String(255), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("location", geoalchemy2.Geography("POINT", srid=4326, spatial_index=False), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_distribution_centers_latitude_range"),
        sa.CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_distribution_centers_longitude_range"),
        sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_distribution_centers_status"),
    )
    op.create_index("ix_distribution_centers_dc_code", "distribution_centers", ["dc_code"], unique=True)
    op.create_index("ix_distribution_centers_location_gist", "distribution_centers", ["location"], postgresql_using="gist")

    op.create_table(
        "transport_routes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("route_id", sa.String(36), nullable=False, unique=True),
        sa.Column("origin_type", sa.String(16), nullable=False),
        sa.Column("origin_code", sa.String(64), nullable=False),
        sa.Column("destination_type", sa.String(16), nullable=False),
        sa.Column("destination_code", sa.String(64), nullable=False),
        sa.Column("vehicle_profile", sa.String(16), nullable=False),
        sa.Column("distance_km", sa.Float(), nullable=False),
        sa.Column("duration_minutes", sa.Float(), nullable=False),
        sa.Column("route_geometry", geoalchemy2.Geometry("GEOMETRY", srid=4326, spatial_index=False), nullable=False),
        sa.Column("routing_provider", sa.String(100), nullable=False),
        sa.Column("provider_route_id", sa.String(255)),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("origin_type IN ('DC', 'BRANCH')", name="ck_transport_routes_origin_type"),
        sa.CheckConstraint("destination_type IN ('DC', 'BRANCH')", name="ck_transport_routes_destination_type"),
        sa.CheckConstraint("GeometryType(route_geometry) IN ('LINESTRING', 'MULTILINESTRING')", name="ck_transport_routes_linear_geometry"),
        sa.CheckConstraint("ST_SRID(route_geometry) = 4326", name="ck_transport_routes_geometry_srid"),
        sa.CheckConstraint("distance_km >= 0", name="ck_transport_routes_distance"),
        sa.CheckConstraint("duration_minutes >= 0", name="ck_transport_routes_duration"),
    )
    op.create_index("ix_transport_routes_geometry_gist", "transport_routes", ["route_geometry"], postgresql_using="gist")
    op.create_index("ix_transport_routes_lookup", "transport_routes", ["origin_type", "origin_code", "destination_type", "destination_code", "vehicle_profile"])


def downgrade() -> None:
    op.drop_table("transport_routes")
    op.drop_table("distribution_centers")
