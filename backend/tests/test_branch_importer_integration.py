"""PostgreSQL/PostGIS integration coverage for the actual branch workbook."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import pytest
pytest.importorskip("sqlalchemy")

from alembic import command
from alembic.config import Config
from geoalchemy2 import Geometry
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.services.branch_importer import EXPECTED_ROW_COUNT, import_workbook
from app.services.branches import find_nearby_branches


WORKBOOK = Path(__file__).parents[2] / "Stores Master Sep2026.xlsx"
ALEMBIC_INI = Path(__file__).parents[2] / "database" / "alembic.ini"


def _integration_database_url() -> str:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is required for the PostGIS integration test")
    if "test" not in urlparse(database_url).path.lower():
        pytest.skip("DATABASE_URL must point to a dedicated test database")
    return database_url


def _upgrade_database(database_url: str) -> None:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


@pytest.mark.integration
def test_actual_workbook_import_persists_and_is_spatially_queryable() -> None:
    database_url = _integration_database_url()
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT PostGIS_Version()"))
    except OperationalError as error:
        pytest.skip(f"PostgreSQL/PostGIS is unavailable: {error}")

    _upgrade_database(database_url)

    with Session(engine) as session:
        session.execute(text("TRUNCATE TABLE branches RESTART IDENTITY"))
        session.commit()

        report = import_workbook(session, WORKBOOK)
        assert report.total_rows == EXPECTED_ROW_COUNT
        assert report.valid_rows == EXPECTED_ROW_COUNT
        assert report.invalid_rows == 0
        assert report.duplicate_rows == 0
        assert report.inserted_rows == EXPECTED_ROW_COUNT
        assert report.updated_rows == 0

        assert session.scalar(select(func.count()).select_from(Branch)) == EXPECTED_ROW_COUNT
        assert session.scalar(select(func.count(func.distinct(Branch.store_number)))) == EXPECTED_ROW_COUNT
        assert session.scalar(select(func.count()).select_from(Branch).where(Branch.location.is_(None))) == 0

        branch = session.scalar(select(Branch).order_by(Branch.store_number).limit(1))
        assert branch is not None
        longitude, latitude, location_longitude, location_latitude = session.execute(
            select(
                Branch.longitude,
                Branch.latitude,
                func.ST_X(Branch.location.cast(Geometry(geometry_type="POINT", srid=4326))),
                func.ST_Y(Branch.location.cast(Geometry(geometry_type="POINT", srid=4326))),
            ).where(Branch.id == branch.id)
        ).one()
        assert location_longitude == pytest.approx(longitude)
        assert location_latitude == pytest.approx(latitude)

        nearby = find_nearby_branches(session, branch.latitude, branch.longitude, radius_km=0.1)
        assert any(result.store_number == branch.store_number for result in nearby)
