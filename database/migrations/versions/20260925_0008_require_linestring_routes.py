"""require transport routes to be LineString geometry"""

from alembic import op

revision = "20260925_0008"
down_revision = "20260925_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_transport_routes_linear_geometry", "transport_routes", type_="check")
    op.execute("""
        ALTER TABLE transport_routes
        ALTER COLUMN route_geometry TYPE geometry(LineString, 4326)
        USING ST_LineMerge(route_geometry)
    """)
    op.create_check_constraint(
        "ck_transport_routes_linear_geometry", "transport_routes",
        "GeometryType(route_geometry) = 'LINESTRING'",
    )


def downgrade() -> None:
    op.drop_constraint("ck_transport_routes_linear_geometry", "transport_routes", type_="check")
    op.execute("""
        ALTER TABLE transport_routes
        ALTER COLUMN route_geometry TYPE geometry(Geometry, 4326)
        USING route_geometry
    """)
    op.create_check_constraint(
        "ck_transport_routes_linear_geometry", "transport_routes",
        "GeometryType(route_geometry) IN ('LINESTRING', 'MULTILINESTRING')",
    )
