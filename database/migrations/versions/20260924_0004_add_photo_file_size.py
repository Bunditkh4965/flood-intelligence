"""record uploaded flood photo size

Revision ID: 20260924_0004
Revises: 20260924_0003
"""
from alembic import op
import sqlalchemy as sa

revision = "20260924_0004"
down_revision = "20260924_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("flood_report_photos", sa.Column("file_size", sa.Integer(), nullable=True))
    op.execute("UPDATE flood_report_photos SET file_size = 0 WHERE file_size IS NULL")
    op.alter_column("flood_report_photos", "file_size", nullable=False)


def downgrade() -> None:
    op.drop_column("flood_report_photos", "file_size")
