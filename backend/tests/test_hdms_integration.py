"""HDMS synchronization acceptance against PostgreSQL/PostGIS with mocked HTTP."""

import os
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core import Settings
from app.integrations.hdms.client import HdmsClient
from app.models.hdms import HdmsIncident
from app.services.hdms import sync_hdms_incidents

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
def test_idempotent_sync_geometry_failure_continues_and_snapshot_retires_missing():
    engine = _engine()
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE hdms_incidents, hdms_sync_runs RESTART IDENTITY CASCADE"))
    dashboard = [
        {"case_id": "failed-geometry", "road_code": "0001", "section_code": "01",
         "km_start": "1+000", "km_end": "1+100", "lane_closure": False},
        {"case_id": "valid-geometry", "road_code": "0033", "section_code": "0602",
         "km_start": "210+015", "km_end": "210+115", "lane_closure": True},
    ]

    def handler(request: httpx.Request):
        if request.url.path.endswith("public/dashboard"):
            return httpx.Response(200, json=dashboard)
        if request.url.params["road_code"] == "0001":
            return httpx.Response(503)
        return httpx.Response(200, json={"geom": {"type": "LineString", "coordinates": [
            [101.85006578736844, 13.969482211375093], [101.85094188237831, 13.96919448296341],
        ]}})

    settings = Settings(_env_file=None, HDMS_BASE_URL="https://example.test/internal-api")
    with Session(engine) as db, HdmsClient(settings, httpx.MockTransport(handler)) as client:
        first = sync_hdms_incidents(db, date(2026, 9, 1), date(2026, 9, 29), client)
        assert (first.status, first.records_inserted, first.geometry_failures) == ("PARTIAL", 2, 1)
        rows = list(db.scalars(select(HdmsIncident).order_by(HdmsIncident.case_id)))
        assert rows[0].case_id == "failed-geometry" and rows[0].road_geometry is None
        assert rows[0].geometry_available is False
        assert rows[1].geometry_available is True

        second = sync_hdms_incidents(db, date(2026, 9, 1), date(2026, 9, 29), client)
        assert (second.records_inserted, second.records_updated, second.records_unchanged) == (0, 0, 2)

        dashboard.pop(0)
        third = sync_hdms_incidents(db, date(2026, 9, 1), date(2026, 9, 29), client)
        assert third.records_unchanged == 1
        rows = {row.case_id: row for row in db.scalars(select(HdmsIncident))}
        assert rows["failed-geometry"].is_active is False
        assert rows["valid-geometry"].is_active is True
