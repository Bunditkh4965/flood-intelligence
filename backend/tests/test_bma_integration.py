"""BMA synchronization acceptance against PostgreSQL/PostGIS with mocked HTTP."""
import os
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
from app.integrations.bma.client import BmaClient
from app.models.bma import BmaRoadWaterObservation
from app.services.bma import sync_bma_observations

ALEMBIC_INI = Path(__file__).parents[2] / "database" / "alembic.ini"

def _engine():
    url = os.environ.get("DATABASE_URL")
    if not url or "test" not in urlparse(url).path.lower(): pytest.skip("DATABASE_URL must point to a dedicated test database")
    engine = create_engine(url)
    try:
        with engine.connect() as connection: connection.execute(text("SELECT PostGIS_Version()"))
    except OperationalError as error: pytest.skip(f"PostgreSQL/PostGIS is unavailable: {error}")
    config = Config(str(ALEMBIC_INI)); config.set_main_option("sqlalchemy.url", url); command.upgrade(config, "head")
    return engine

@pytest.mark.integration
def test_idempotent_changed_and_malformed_snapshot_safe_sync():
    engine = _engine()
    with engine.begin() as c: c.execute(text("TRUNCATE bma_road_water_observations, bma_sync_runs RESTART IDENTITY CASCADE"))
    features = [{"attributes": {"MASTER_STATION_ID": "M1", "WATER_LEVEL_CM": 0}, "geometry": {"points": [[100.5, 13.8]]}}]
    settings = Settings(_env_file=None, BMA_BASE_URL="https://example.test/FeatureServer/1")
    with Session(engine) as db, BmaClient(settings, httpx.MockTransport(lambda request: httpx.Response(200, json={"features": features}))) as client:
        first = sync_bma_observations(db, client)
        assert (first.records_inserted, first.records_updated, first.records_unchanged) == (1, 0, 0)
        second = sync_bma_observations(db, client)
        assert (second.records_inserted, second.records_updated, second.records_unchanged) == (0, 0, 1)
        assert db.scalar(select(BmaRoadWaterObservation)).is_active is True
        features[0]["attributes"]["WATER_LEVEL_CM"] = 7
        assert sync_bma_observations(db, client).records_updated == 1
        features[:] = [{"attributes": {"MASTER_STATION_ID": "broken"}, "geometry": None}]
        partial = sync_bma_observations(db, client)
        assert partial.status == "PARTIAL" and partial.records_rejected == 1
        row = db.scalar(select(BmaRoadWaterObservation))
        assert row.is_active is True and row.water_level_cm == 7
