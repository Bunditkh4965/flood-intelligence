"""End-to-end PostGIS coverage for public observation proximity."""

import os
from pathlib import Path
from urllib.parse import urlparse

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.schemas.public_flood_impact import PublicImpactClassification
from app.services.public_flood_impact import calculate_public_branch_impact, calculate_public_branch_impacts

ALEMBIC_INI = Path(__file__).parents[2] / "database" / "alembic.ini"


def _engine():
    url = os.environ.get("DATABASE_URL")
    if not url or "test" not in urlparse(url).path.lower():
        pytest.skip("DATABASE_URL must point to a dedicated PostGIS test database")
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
def test_public_report_eligibility_nearest_classification_and_lookup() -> None:
    engine = _engine()
    with Session(engine) as db:
        db.execute(text("TRUNCATE branches, flood_reports RESTART IDENTITY CASCADE"))
        db.execute(text("""
            INSERT INTO branches (store_number, store_name, city, latitude, longitude, location, status)
            VALUES
              ('100', 'Near', 'Test', 0, 0, ST_Point(0,0)::geography, 'active'),
              ('200', 'Pending', 'Test', 0, 1, ST_Point(1,0)::geography, 'active'),
              ('300', 'None', 'Test', 0, 2, ST_Point(2,0)::geography, 'active')
        """))
        # Reporter GPS is deliberately at branches; selected flood points control every result.
        db.execute(text("""
            INSERT INTO flood_reports
              (report_code, flood_latitude, flood_longitude, flood_location,
               reporter_latitude, reporter_longitude, reporter_location, water_level_cm,
               verification_status, verification_reason, source, status, reported_at)
            VALUES
              ('verified-nearest', 0, .005, ST_Point(.005,0)::geography, 0, 2, ST_Point(2,0)::geography, 1, 'VERIFIED', 'TEST', 'PUBLIC', 'ACTIVE', now()),
              ('verified-farther', 0, .01, ST_Point(.01,0)::geography, NULL, NULL, NULL, 1, 'VERIFIED', 'TEST', 'PUBLIC', 'ACTIVE', now()),
              ('pending', 0, 1.005, ST_Point(1.005,0)::geography, NULL, NULL, NULL, 1, 'PENDING_REVIEW', 'TEST', 'PUBLIC', 'ACTIVE', now()),
              ('unverified', 0, 2, ST_Point(2,0)::geography, NULL, NULL, NULL, 1, 'UNVERIFIED', 'TEST', 'PUBLIC', 'ACTIVE', now()),
              ('inactive', 0, 2, ST_Point(2,0)::geography, NULL, NULL, NULL, 1, 'VERIFIED', 'TEST', 'PUBLIC', 'CLOSED', now()),
              ('old', 0, 2, ST_Point(2,0)::geography, NULL, NULL, NULL, 1, 'VERIFIED', 'TEST', 'PUBLIC', 'ACTIVE', now() - interval '25 hours'),
              ('company', 0, 2, ST_Point(2,0)::geography, NULL, NULL, NULL, 1, 'VERIFIED', 'TEST', 'COMPANY', 'ACTIVE', now())
        """))
        db.commit()

        page = calculate_public_branch_impacts(db, 2, 24, None, 100, 0)
        assert page.data_available is True
        assert page.summary == {"nearby": 2, "none": 1}
        assert len(page.items) == 3  # each branch appears exactly once
        near, pending, none = page.items
        assert near["public_impact_classification"] == "PUBLIC_NEARBY"
        assert near["nearest_report_code"] == "verified-nearest"
        assert pending["public_impact_classification"] == "PUBLIC_NEARBY"
        assert pending["nearest_report_verification_status"] == "PENDING_REVIEW"
        assert none["public_impact_classification"] == "PUBLIC_NONE"
        assert none["nearest_report_code"] == "pending"  # nearest eligible, even outside radius

        filtered = calculate_public_branch_impacts(
            db, 2, 24, PublicImpactClassification.PUBLIC_NONE, 100, 0)
        assert [item["store_number"] for item in filtered.items] == ["300"]
        assert calculate_public_branch_impact(db, "100", 2, 24)[1]["nearest_report_code"] == "verified-nearest"
        assert calculate_public_branch_impact(db, "missing", 2, 24) is None

        db.execute(text("UPDATE flood_reports SET status = 'CLOSED' WHERE status = 'ACTIVE'"))
        db.commit()
        unavailable = calculate_public_branch_impacts(db, 2, 24, None, 100, 0)
        assert unavailable.data_available is False
        assert unavailable.summary == {"nearby": 0, "none": 3}
        assert all(item["nearest_report_code"] is None for item in unavailable.items)
