"""PostGIS schema and route-geometry coverage for Sprint 5A."""

import os
from pathlib import Path
from urllib.parse import urlparse

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

ALEMBIC_INI = Path(__file__).parents[2] / "database" / "alembic.ini"


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is required for PostGIS integration tests")
    if "test" not in urlparse(url).path.lower():
        pytest.skip("DATABASE_URL must point to a dedicated test database")
    return url


@pytest.mark.integration
def test_transport_migration_spatial_types_indexes_and_provenance() -> None:
    url = _database_url()
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT PostGIS_Version()"))
    except OperationalError as error:
        pytest.skip(f"PostgreSQL/PostGIS is unavailable: {error}")
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")

    with engine.begin() as connection:
        connection.execute(text("TRUNCATE transport_routes, distribution_centers RESTART IDENTITY"))
        connection.execute(text("""
            INSERT INTO distribution_centers (dc_code, dc_name, latitude, longitude, location, status)
            VALUES ('DC-T', 'Test DC', 13.75, 100.5,
                    ST_SetSRID(ST_Point(100.5, 13.75), 4326)::geography, 'ACTIVE')
        """))
        connection.execute(text("""
            INSERT INTO transport_routes
              (route_id, origin_type, origin_code, destination_type, destination_code,
               vehicle_profile, distance_km, duration_minutes, route_geometry,
               routing_provider, provider_route_id, calculated_at)
            VALUES
              ('route-test', 'DC', 'DC-T', 'BRANCH', '1001', '6W', 12.5, 30,
               ST_GeomFromText('LINESTRING(100.5 13.75,100.6 13.8)', 4326),
               'integration-test-provider', 'external-1', now())
        """))
        row = connection.execute(text("""
            SELECT GeometryType(route_geometry), ST_SRID(route_geometry), routing_provider,
                   provider_route_id, ST_NPoints(route_geometry)
            FROM transport_routes WHERE route_id = 'route-test'
        """)).one()
        assert row == ("LINESTRING", 4326, "integration-test-provider", "external-1", 2)

        indexes = {row[0] for row in connection.execute(text("""
            SELECT indexname FROM pg_indexes
            WHERE tablename IN ('distribution_centers', 'transport_routes')
        """))}
        assert "ix_distribution_centers_location_gist" in indexes
        assert "ix_transport_routes_geometry_gist" in indexes
