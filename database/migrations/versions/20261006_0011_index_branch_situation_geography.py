"""Index the geodesic HDMS/BMA proximity predicates used by branch situations.

EXPLAIN on 2,574 branches showed 2,574 sequential HDMS scans (~81.5 s)
and BMA scans (~1 s). Their geometry indexes cannot support ST_DWithin
on geography casts. Keep the exact geodesic predicate and index its operands.
"""

from alembic import op

revision = "20261006_0011"
down_revision = "20260929_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE INDEX ix_hdms_incidents_active_geography_gist
        ON hdms_incidents USING gist ((road_geometry::geography))
        WHERE is_active IS TRUE AND geometry_available IS TRUE
    """)
    op.execute("""
        CREATE INDEX ix_bma_road_water_active_geography_gist
        ON bma_road_water_observations USING gist ((location::geography))
        WHERE is_active IS TRUE
    """)


def downgrade() -> None:
    op.drop_index("ix_bma_road_water_active_geography_gist", table_name="bma_road_water_observations")
    op.drop_index("ix_hdms_incidents_active_geography_gist", table_name="hdms_incidents")
