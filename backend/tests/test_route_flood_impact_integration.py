"""PostGIS acceptance of real-LineString intersection and metre proximity."""

import os
from pathlib import Path
from urllib.parse import urlparse

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.services.route_flood_impact import _BMA_SQL, _GISTDA_SQL, _HDMS_SQL, _PUBLIC_SQL, evaluate_route_flood_impact

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
        c.execute(text("TRUNCATE transport_routes, gistda_flood_features, flood_reports, hdms_incidents, bma_road_water_observations RESTART IDENTITY CASCADE"))
        # 1,001 coordinates exercise the persisted road shape, not an endpoint chord.
        c.execute(text("""
          INSERT INTO transport_routes(route_id,origin_type,origin_code,destination_type,destination_code,
            vehicle_profile,distance_km,duration_minutes,route_geometry,routing_provider,calculated_at)
          SELECT 'r','DC','d','BRANCH','b','6W',1,1,
            ST_MakeLine(ARRAY(SELECT ST_SetSRID(ST_Point(100+i/100000.0,13),4326) FROM generate_series(0,1000)i)),
            'VALHALLA',now()
        """))
        c.execute(text("""
          INSERT INTO hdms_incidents(source_record_id,case_id,road_status,is_active,road_geometry,
            geometry_available,source_metadata,synced_at)
          VALUES
            ('case:closed','closed','IMPASSABLE',true,
             ST_GeomFromText('LINESTRING(100.004 13,100.006 13)',4326),true,'{}',now()),
            ('case:passable','passable','PASSABLE',true,
             ST_GeomFromText('LINESTRING(100.007 13,100.008 13)',4326),true,'{}',now()),
            ('case:away','away','IMPASSABLE',true,
             ST_GeomFromText('LINESTRING(101 14,101.1 14.1)',4326),true,'{}',now()),
            ('case:no-geometry','no-geometry','IMPASSABLE',true,NULL,false,'{}',now())
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
        incidents=c.execute(text(_HDMS_SQL),params).mappings().all()
        c.execute(text("""INSERT INTO bma_road_water_observations(source_record_id,station_id,source_latitude,
          source_longitude,location,fingerprint,is_active,synced_at) VALUES
          ('master:near','near',13,100.005,ST_GeomFromText('POINT(100.005 13)',4326),'near',true,now()),
          ('master:away','away',14,101,ST_GeomFromText('POINT(101 14)',4326),'away',true,now())"""))
        points=c.execute(text(_BMA_SQL),{**params,"bma_radius_meters":50}).mappings().all()
        assert [p["feature_id"] for p in polygons] == [1]
        assert [r["report_code"] for r in reports] == ["inside", "boundary"]
        assert float(reports[1]["distance_to_route_meters"]) == pytest.approx(300, abs=.01)
        assert [item["case_id"] for item in incidents] == ["closed", "passable"]
        assert [item["station_id"] for item in points] == ["near"]

    with Session(engine) as session:
        impact = evaluate_route_flood_impact(session, "r", "3DAYS", 300, 24)
        assert impact["official_road_closure"] is True
        assert {item["case_id"] for item in impact["hdms_evidence"]} == {"closed", "passable"}
        assert impact["gistda_evidence"] and impact["public_report_evidence"]
        assert [item["station_id"] for item in impact["bma_evidence"]] == ["near"]
        session.execute(text("UPDATE hdms_incidents SET is_active=false WHERE case_id='closed'"))
        session.commit()
        impact = evaluate_route_flood_impact(session, "r", "3DAYS", 300, 24)
        assert impact["official_road_closure"] is False
        assert impact["bma_evidence"]
        assert [item["case_id"] for item in impact["hdms_evidence"]] == ["passable"]
