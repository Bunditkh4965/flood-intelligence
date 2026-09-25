"""End-to-end PostGIS coverage for branch impact classification."""

import os
from pathlib import Path
from urllib.parse import urlparse

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.schemas.flood_impact import ImpactClassification
from app.services.flood_impact import calculate_branch_impact, calculate_branch_impacts

ALEMBIC_INI = Path(__file__).parents[2] / "database" / "alembic.ini"


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is required for PostGIS integration tests")
    if "test" not in urlparse(url).path.lower():
        pytest.skip("DATABASE_URL must point to a dedicated test database")
    return url


@pytest.mark.integration
def test_postgis_impact_rules_nearest_period_active_filter_and_pagination() -> None:
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

    with Session(engine) as db:
        db.execute(text("TRUNCATE branches, gistda_flood_features RESTART IDENTITY CASCADE"))
        db.execute(text("""
            INSERT INTO branches (store_number, store_name, city, latitude, longitude, location, status)
            VALUES
              ('100', 'Inside', 'Test', 0.0, 0.0, ST_SetSRID(ST_Point(0,0),4326)::geography, 'active'),
              ('200', 'Near', 'Test', 0.0, 0.02, ST_SetSRID(ST_Point(0.02,0),4326)::geography, 'active'),
              ('300', 'Far', 'Test', 0.0, 1.0, ST_SetSRID(ST_Point(1,0),4326)::geography, 'active')
        """))
        db.execute(text("""
            INSERT INTO gistda_flood_features
              (external_feature_id, period, geometry, synced_at, source_properties, source_hash, is_active)
            VALUES
              ('direct', '3DAYS', ST_Multi(ST_GeomFromText('POLYGON((-0.01 -0.01,0.01 -0.01,0.01 0.01,-0.01 0.01,-0.01 -0.01))',4326)), now(), '{}', repeat('a',64), true),
              ('nearer', '3DAYS', ST_Multi(ST_GeomFromText('POLYGON((0.014 -0.005,0.016 -0.005,0.016 0.005,0.014 0.005,0.014 -0.005))',4326)), now(), '{}', repeat('b',64), true),
              ('inactive', '3DAYS', ST_Multi(ST_GeomFromText('POLYGON((0.019 -0.001,0.021 -0.001,0.021 0.001,0.019 0.001,0.019 -0.001))',4326)), now(), '{}', repeat('c',64), false),
              ('wrong-period', '7DAYS', ST_Multi(ST_GeomFromText('POLYGON((0.019 -0.001,0.021 -0.001,0.021 0.001,0.019 0.001,0.019 -0.001))',4326)), now(), '{}', repeat('d',64), true)
        """))
        db.commit()

        page = calculate_branch_impacts(db, "3DAYS", 2, None, 100, 0)
        assert page.data_available is True
        assert page.summary == {"direct": 1, "nearby": 1, "none": 1}
        assert len(page.items) == 3
        inside, near, far = page.items
        assert inside["impact_classification"] == "DIRECT"
        assert inside["inside_flood_polygon"] is True
        assert inside["nearest_flood_distance_km"] == 0
        assert near["impact_classification"] == "NEARBY"
        assert near["nearest_flood_feature_id"] == 2
        assert 0 < near["nearest_flood_distance_km"] < 2
        assert far["impact_classification"] == "NONE"

        filtered = calculate_branch_impacts(db, "3DAYS", 2, ImpactClassification.NEARBY, 1, 0)
        assert [item["store_number"] for item in filtered.items] == ["200"]
        second_page = calculate_branch_impacts(db, "3DAYS", 2, None, 1, 1)
        assert [item["store_number"] for item in second_page.items] == ["200"]
        assert calculate_branch_impact(db, "200", "3DAYS", 2)[1]["impact_classification"] == "NEARBY"
        assert calculate_branch_impact(db, "missing", "3DAYS", 2) is None

        unavailable = calculate_branch_impacts(db, "1DAY", 2, None, 100, 0)
        assert unavailable.data_available is False
        assert unavailable.summary == {"direct": 0, "nearby": 0, "none": 3}
        assert all(item["nearest_flood_distance_km"] is None for item in unavailable.items)
