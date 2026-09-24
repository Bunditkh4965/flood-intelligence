"""create branches table with spatial index"""

from alembic import op
import geoalchemy2
import sqlalchemy as sa

revision = "20260924_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.create_table(
        "branches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("store_number", sa.String(length=64), nullable=False),
        sa.Column("store_name", sa.String(length=255), nullable=False),
        sa.Column("format", sa.String(length=100)),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("location", geoalchemy2.Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False),
        sa.Column("business_hours", sa.String(length=255)),
        sa.Column("vehicle_type", sa.String(length=100)),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_branches_latitude_range"),
        sa.CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_branches_longitude_range"),
    )
    op.create_index("ix_branches_store_number", "branches", ["store_number"], unique=True)
    op.create_index("ix_branches_location_gist", "branches", ["location"], postgresql_using="gist")


def downgrade() -> None:
    op.drop_table("branches")
