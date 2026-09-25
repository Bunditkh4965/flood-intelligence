"""PostGIS acceptance of real-LineString intersection and metre proximity."""

import os
from pathlib import Path
from urllib.parse import urlparse

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.services.route_flood_impact import _GISTDA_SQL, _PUBLIC_SQL

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
    config = Config(str(ALEMBIC_INI)); config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    return engine


@pytest.mark.integration
def test_route_polygon_and_public_point_boundaries_many_coordinates():
    engine = _engine()
    with engine.begin() as c:
        c.execute(text("TRUNCATE transport_routes, gistda_flood_features, flood_reports RESTART IDENTITY CASCADE"))
        # 1,001 coordinates exercise the persisted road shape, not an endpoint chord.
        c.execute(text("""
          INSERT INTO transport_routes(route_id,origin_type,origin_code,destination_type,destination_code,
            vehicle_profile,distance_km,duration_minutes,route_geometry,routing_provider,calculated_at)
          SELECT 'r','DC','d','BRANCH','b','6W',1,1,
            ST_MakeLine(ARRAY(SELECT ST_SetSRID(ST_Point(100+i/100000.0,13),4326) FROM generate_series(0,1000)i)),
            'VALHALLA',now()
        """))
        c.execute(text("""
          INSERT INTO gistda_flood_features(period,geometry,source,synced_at,source_properties,source_hash,is_active)
          VALUES ('3DAYS',ST_Multi(ST_GeomFromText('POLYGON((100.004 12.999,100.006 12.999,100.006 13.001,100.004 13.001,100.004 12.999))',4326)),'GISTDA',now(),'{}','hit',true),
          ('3DAYS',ST_Multi(ST_GeomFromText('POLYGON((101 14,101.1 14,101.1 14.1,101 14.1,101 14))',4326)),'GISTDA',now(),'{}','miss',true)
        """))
        # Equatorward-enough test geometry: construct points at exactly/just beyond
        # 300 metres from the route with geography ST_Project.
        c.execute(text("""
          INSERT INTO flood_reports(report_code,flood_latitude,flood_longitude,flood_location,water_level_cm,
            verification_status,verification_reason,source,status,reported_at)
          SELECT code, ST_Y(pt::geometry), ST_X(pt::geometry), pt, 10, verification, 'TEST','PUBLIC','ACTIVE',now()
          FROM (VALUES
            ('inside', ST_Project('SRID=4326;POINT(100.005 13)'::geography,299,0.0), 'VERIFIED'),
            ('boundary', ST_Project('SRID=4326;POINT(100.005 13)'::geography,300,0.0), 'PENDING_REVIEW'),
            ('outside', ST_Project('SRID=4326;POINT(100.005 13)'::geography,301,0.0), 'VERIFIED'),
            ('unverified', ST_Project('SRID=4326;POINT(100.005 13)'::geography,1,0.0), 'UNVERIFIED')) v(code,pt,verification)
        """))
        params={"route_id":"r","period":"3DAYS","radius_meters":300,
                "eligible_statuses":["VERIFIED","PENDING_REVIEW"],"reported_from":"2026-01-01",
                "vehicle_profile":"6W"}
        polygons=c.execute(text(_GISTDA_SQL),params).mappings().all()
        reports=c.execute(text(_PUBLIC_SQL),params).mappings().all()
        assert [p["feature_id"] for p in polygons] == [1]
        assert [r["report_code"] for r in reports] == ["inside", "boundary"]
        assert float(reports[1]["distance_to_route_meters"]) == pytest.approx(300, abs=.01)
