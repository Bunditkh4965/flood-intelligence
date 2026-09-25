"""add geography index for geodesic nearest-feature searches"""

from alembic import op

revision = "20260925_0005"
down_revision = "20260924_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE INDEX ix_gistda_features_geography_gist
        ON gistda_flood_features USING gist ((geometry::geography))
    """)


def downgrade() -> None:
    op.drop_index("ix_gistda_features_geography_gist", table_name="gistda_flood_features")
