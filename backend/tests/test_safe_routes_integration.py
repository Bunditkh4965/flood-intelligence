"""PostGIS execution coverage for flood-avoidance exclusion SQL."""

import json
import os
from pathlib import Path
from urllib.parse import urlparse

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.services.safe_routes import _EXCLUSION_POLYGONS


ALEMBIC_INI = Path(__file__).parents[2] / "database" / "alembic.ini"


def _engine():
    url = os.environ.get("DATABASE_URL")
    if not url or "test" not in urlparse(url).path.lower():
        pytest.skip("DATABASE_URL must point to a dedicated test database")
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT PostGIS_Version()"))
    except OperationalError as error:
        pytest.skip(f"PostgreSQL/PostGIS is unavailable: {error}")
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    return engine


@pytest.mark.integration
def test_exclusion_polygon_query_executes_in_postgis() -> None:
    """Compile and execute the production SQL, including all CTE aliases."""
    engine = _engine()
    route = json.dumps({
        "type": "LineString",
        "coordinates": [[100.005, 12.99], [100.005, 13.01]],
    })
    with engine.connect() as connection, connection.begin() as transaction:
        connection.execute(text("""
            INSERT INTO hdms_incidents
              (source_record_id, road_status, is_active, road_geometry,
               geometry_available, source_metadata, synced_at)
            VALUES
              ('safe-route-sql-regression', 'IMPASSABLE', TRUE,
               ST_GeomFromText('LINESTRING(100 13, 100.01 13)', 4326),
               TRUE, '{}', now())
        """))
        rows = connection.execute(_EXCLUSION_POLYGONS, {"route": route}).mappings().all()
        transaction.rollback()

    assert len(rows) == 1
    assert rows[0]["window_index"] >= 0
    assert rows[0]["polygon"]["type"] == "Polygon"
