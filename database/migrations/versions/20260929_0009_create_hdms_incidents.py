"""create HDMS road incident persistence"""

from alembic import op
import geoalchemy2
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260929_0009"
down_revision = "20260925_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hdms_incidents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_record_id", sa.String(128), nullable=False),
        sa.Column("case_id", sa.String(128)), sa.Column("gid", sa.String(128)),
        sa.Column("road_code", sa.String(32)), sa.Column("section_code", sa.String(32)),
        sa.Column("section_name", sa.String(255)), sa.Column("km_start", sa.String(32)),
        sa.Column("km_end", sa.String(32)), sa.Column("province", sa.String(128)),
        sa.Column("amphoe", sa.String(128)), sa.Column("tambon", sa.String(128)),
        sa.Column("water_depth_cm", sa.Float()),
        sa.Column("road_status", sa.String(16), nullable=False),
        sa.Column("incident_at", sa.DateTime(timezone=True)),
        sa.Column("report_at", sa.DateTime(timezone=True)),
        sa.Column("source_updated_at", sa.DateTime(timezone=True)),
        sa.Column("survey_at", sa.DateTime(timezone=True)),
        sa.Column("source_status", sa.String(64)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("road_geometry", geoalchemy2.Geometry("LINESTRING", srid=4326, spatial_index=False)),
        sa.Column("geometry_available", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("source_metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("source_record_id", name="uq_hdms_incidents_source_record_id"),
        sa.CheckConstraint("road_status IN ('PASSABLE','IMPASSABLE','UNKNOWN')", name="ck_hdms_incidents_road_status"),
        sa.CheckConstraint("road_geometry IS NULL OR GeometryType(road_geometry) = 'LINESTRING'", name="ck_hdms_incidents_linestring"),
        sa.CheckConstraint("road_geometry IS NULL OR ST_SRID(road_geometry) = 4326", name="ck_hdms_incidents_geometry_srid"),
        sa.CheckConstraint("geometry_available = (road_geometry IS NOT NULL)", name="ck_hdms_incidents_geometry_available"),
    )
    op.create_index("ix_hdms_incidents_active", "hdms_incidents", ["is_active"])
    op.create_index("ix_hdms_incidents_road_section", "hdms_incidents", ["road_code", "section_code"])
    op.create_index("ix_hdms_incidents_geometry_gist", "hdms_incidents", ["road_geometry"], postgresql_using="gist")
    op.create_table(
        "hdms_sync_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("records_received", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_unchanged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_rejected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("geometry_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('RUNNING','SUCCESS','PARTIAL','FAILED')", name="ck_hdms_sync_status"),
    )
    op.create_index("ix_hdms_sync_started", "hdms_sync_runs", ["started_at"])


def downgrade() -> None:
    op.drop_table("hdms_sync_runs")
    op.drop_table("hdms_incidents")
