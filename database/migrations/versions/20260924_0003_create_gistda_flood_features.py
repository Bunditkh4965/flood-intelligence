"""create GISTDA flood features and synchronization history"""

from alembic import op
import geoalchemy2
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260924_0003"
down_revision = "20260924_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gistda_sync_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("period", sa.String(10), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("records_received", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_unchanged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_rejected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("period IN ('1DAY','3DAYS','7DAYS','30DAYS')", name="ck_gistda_sync_period"),
        sa.CheckConstraint("status IN ('RUNNING','SUCCESS','PARTIAL','FAILED')", name="ck_gistda_sync_status"),
    )
    op.create_index("ix_gistda_sync_period_started", "gistda_sync_runs", ["period", "started_at"])
    op.create_table(
        "gistda_flood_features",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("external_feature_id", sa.String(255)),
        sa.Column("period", sa.String(10), nullable=False),
        sa.Column("geometry", geoalchemy2.Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=False),
        sa.Column("source", sa.String(20), nullable=False, server_default="GISTDA"),
        sa.Column("source_observed_at", sa.DateTime(timezone=True)),
        sa.Column("source_updated_at", sa.DateTime(timezone=True)),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_properties", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("period IN ('1DAY','3DAYS','7DAYS','30DAYS')", name="ck_gistda_features_period"),
        sa.CheckConstraint("source = 'GISTDA'", name="ck_gistda_features_source"),
        sa.UniqueConstraint("period", "source_hash", name="uq_gistda_features_period_hash"),
    )
    op.create_index("ix_gistda_features_geometry_gist", "gistda_flood_features", ["geometry"], postgresql_using="gist")
    op.create_index("ix_gistda_features_period_active", "gistda_flood_features", ["period", "is_active"])


def downgrade() -> None:
    op.drop_table("gistda_flood_features")
    op.drop_table("gistda_sync_runs")
