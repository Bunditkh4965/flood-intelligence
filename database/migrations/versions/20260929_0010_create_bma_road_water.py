"""create BMA road-water persistence"""

from alembic import op
import geoalchemy2
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260929_0010"
down_revision = "20260929_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("bma_road_water_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_record_id", sa.String(128), nullable=False),
        sa.Column("master_station_id", sa.String(128)), sa.Column("station_id", sa.String(128)),
        sa.Column("object_id", sa.String(128)), sa.Column("object_id_1", sa.String(128)),
        sa.Column("station_name", sa.String(255)), sa.Column("station_old_code", sa.String(128)),
        sa.Column("road_name", sa.String(255)), sa.Column("tunnel_description", sa.String(255)),
        sa.Column("water_level_cm", sa.Float()), sa.Column("source_status", sa.String(128)),
        sa.Column("observed_at", sa.DateTime(timezone=False)), sa.Column("flood_start_at", sa.DateTime(timezone=False)),
        sa.Column("flood_stop_at", sa.DateTime(timezone=False)), sa.Column("flood_max_cm", sa.Float()),
        sa.Column("flood_max_at", sa.DateTime(timezone=False)), sa.Column("agency", sa.String(255)),
        sa.Column("api_source", sa.String(64)), sa.Column("province", sa.String(128)),
        sa.Column("amphoe", sa.String(128)), sa.Column("tambon", sa.String(128)),
        sa.Column("source_latitude", sa.Float(), nullable=False), sa.Column("source_longitude", sa.Float(), nullable=False),
        sa.Column("location", geoalchemy2.Geometry("POINT", srid=4326, spatial_index=False), nullable=False),
        sa.Column("source_created_at", sa.DateTime(timezone=False)), sa.Column("source_updated_at", sa.DateTime(timezone=False)),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("source_metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("source_record_id", name="uq_bma_road_water_source_record_id"),
        sa.CheckConstraint("GeometryType(location) = 'POINT' AND ST_SRID(location) = 4326", name="ck_bma_road_water_location"))
    op.create_index("ix_bma_road_water_active", "bma_road_water_observations", ["is_active"])
    op.create_index("ix_bma_road_water_road", "bma_road_water_observations", ["road_name"])
    op.create_index("ix_bma_road_water_location_gist", "bma_road_water_observations", ["location"], postgresql_using="gist")
    op.create_table("bma_sync_runs",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)), sa.Column("status", sa.String(10), nullable=False),
        sa.Column("records_received", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_unchanged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_rejected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("geometry_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("page_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('RUNNING','SUCCESS','PARTIAL','FAILED')", name="ck_bma_sync_status"))


def downgrade() -> None:
    op.drop_table("bma_sync_runs")
    op.drop_table("bma_road_water_observations")
