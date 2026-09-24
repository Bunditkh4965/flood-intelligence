"""create public flood reports and GPS verification configuration"""

from alembic import op
import geoalchemy2
import sqlalchemy as sa

revision = "20260924_0002"
down_revision = "20260924_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_configurations",
        sa.Column("key", sa.String(length=100), primary_key=True),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.bulk_insert(sa.table("system_configurations", sa.column("key", sa.String), sa.column("value", sa.String)), [{"key": "REPORTER_GPS_VERIFY_RADIUS_M", "value": "300"}])
    op.create_table(
        "flood_report_code_sequences",
        sa.Column("report_date", sa.Date(), primary_key=True),
        sa.Column("last_value", sa.Integer(), nullable=False),
    )
    op.create_table(
        "flood_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("report_code", sa.String(length=32), nullable=False, unique=True),
        sa.Column("reporter_id", sa.Integer()),
        sa.Column("reporter_latitude", sa.Float()), sa.Column("reporter_longitude", sa.Float()),
        sa.Column("reporter_location", geoalchemy2.Geography(geometry_type="POINT", srid=4326, spatial_index=False)),
        sa.Column("reporter_gps_accuracy_m", sa.Float()),
        sa.Column("flood_latitude", sa.Float(), nullable=False), sa.Column("flood_longitude", sa.Float(), nullable=False),
        sa.Column("flood_location", geoalchemy2.Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False),
        sa.Column("reporter_flood_distance_m", sa.Float()), sa.Column("water_level_cm", sa.Float(), nullable=False),
        sa.Column("road_status", sa.String(length=20), nullable=False, server_default="UNKNOWN"),
        sa.Column("vehicle_4w_status", sa.String(length=20), nullable=False, server_default="UNKNOWN"),
        sa.Column("vehicle_6w_status", sa.String(length=20), nullable=False, server_default="UNKNOWN"),
        sa.Column("vehicle_10w_status", sa.String(length=20), nullable=False, server_default="UNKNOWN"),
        sa.Column("description", sa.Text()), sa.Column("has_photo", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("verification_status", sa.String(length=20), nullable=False), sa.Column("verification_reason", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="PUBLIC"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("flood_latitude BETWEEN -90 AND 90", name="ck_flood_reports_flood_latitude_range"),
        sa.CheckConstraint("flood_longitude BETWEEN -180 AND 180", name="ck_flood_reports_flood_longitude_range"),
        sa.CheckConstraint("reporter_latitude IS NULL OR reporter_latitude BETWEEN -90 AND 90", name="ck_flood_reports_reporter_latitude_range"),
        sa.CheckConstraint("reporter_longitude IS NULL OR reporter_longitude BETWEEN -180 AND 180", name="ck_flood_reports_reporter_longitude_range"),
        sa.CheckConstraint("reporter_gps_accuracy_m IS NULL OR reporter_gps_accuracy_m >= 0", name="ck_flood_reports_gps_accuracy"),
        sa.CheckConstraint("water_level_cm >= 0", name="ck_flood_reports_water_level"),
        sa.CheckConstraint("road_status IN ('PASSABLE', 'PARTIAL', 'BLOCKED', 'UNKNOWN')", name="ck_flood_reports_road_status"),
        sa.CheckConstraint("vehicle_4w_status IN ('PASSABLE', 'BLOCKED', 'UNKNOWN')", name="ck_flood_reports_vehicle_4w_status"),
        sa.CheckConstraint("vehicle_6w_status IN ('PASSABLE', 'BLOCKED', 'UNKNOWN')", name="ck_flood_reports_vehicle_6w_status"),
        sa.CheckConstraint("vehicle_10w_status IN ('PASSABLE', 'BLOCKED', 'UNKNOWN')", name="ck_flood_reports_vehicle_10w_status"),
        sa.CheckConstraint("verification_status IN ('VERIFIED', 'PENDING_REVIEW', 'UNVERIFIED')", name="ck_flood_reports_verification_status"),
        sa.CheckConstraint("source IN ('PUBLIC', 'COMPANY', 'GISTDA', 'SYSTEM')", name="ck_flood_reports_source"),
        sa.CheckConstraint("status IN ('ACTIVE', 'REVIEWED', 'REJECTED', 'CLOSED')", name="ck_flood_reports_status"),
    )
    op.create_index("ix_flood_reports_flood_location_gist", "flood_reports", ["flood_location"], postgresql_using="gist")
    op.create_index("ix_flood_reports_reporter_location_gist", "flood_reports", ["reporter_location"], postgresql_using="gist")
    op.create_index("ix_flood_reports_reported_at", "flood_reports", ["reported_at"])
    op.create_index("ix_flood_reports_status_verification", "flood_reports", ["status", "verification_status"])
    op.create_table(
        "flood_report_photos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("flood_report_id", sa.Integer(), sa.ForeignKey("flood_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False, unique=True),
        sa.Column("content_type", sa.String(length=100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_flood_report_photos_flood_report_id", "flood_report_photos", ["flood_report_id"])


def downgrade() -> None:
    op.drop_table("flood_report_photos")
    op.drop_table("flood_reports")
    op.drop_table("flood_report_code_sequences")
    op.drop_table("system_configurations")
