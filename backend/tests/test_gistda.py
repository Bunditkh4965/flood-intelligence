import logging
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import gistda as api
from app.core import Settings
from app.db.session import get_db
from app.integrations.gistda.client import GistdaAPIError, GistdaClient, GistdaConfigurationError
from app.main import app
from app.services.gistda import normalize_period, parse_collection, parse_feature, source_hash
from app.models.gistda import GistdaFloodFeature, GistdaSyncRun
from app.services.gistda import sync_gistda_flood


POLYGON = {"type": "Polygon", "coordinates": [[[100, 13], [101, 13], [101, 14], [100, 13]]]}
MULTIPOLYGON = {"type": "MultiPolygon", "coordinates": [[[[100, 13], [101, 13], [101, 14], [100, 13]]]]}


def feature(geometry=POLYGON, identifier="f-1"):
    return {"type": "Feature", "id": identifier, "geometry": geometry, "properties": {"date": "2026-09-24T00:00:00Z"}}


def settings(key="secret-test-value"):
    return Settings(GISTDA_API_KEY=key, GISTDA_API_BASE_URL="https://example.test/api/")


def test_missing_api_key_is_rejected() -> None:
    with pytest.raises(GistdaConfigurationError, match="GISTDA_API_KEY"):
        GistdaClient(settings(""))


def test_official_api_key_header_and_endpoint() -> None:
    def handler(request: httpx.Request):
        assert request.headers["API-Key"] == "secret-test-value"
        assert request.url.path == "/api/features/flood/1day"
        return httpx.Response(200, json={"type": "FeatureCollection", "features": []})
    client = GistdaClient(settings(), httpx.MockTransport(handler))
    assert client.fetch_flood_features("1DAY")["type"] == "FeatureCollection"
    client.close()


def test_api_key_not_exposed_in_logs_or_errors(caplog) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(500, text="upstream failed"))
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(GistdaAPIError) as exc:
            GistdaClient(settings(), transport).fetch_flood_features("1DAY")
    assert "secret-test-value" not in caplog.text
    assert "secret-test-value" not in str(exc.value)


@pytest.mark.parametrize("geometry", [POLYGON, MULTIPOLYGON])
def test_polygon_and_multipolygon_are_normalized(geometry) -> None:
    parsed = parse_feature(feature(geometry))
    assert parsed.geometry["type"] == "MultiPolygon"


def test_valid_collection_and_malformed_individual_feature() -> None:
    valid, rejected, received = parse_collection({"type": "FeatureCollection", "features": [feature(), {"bad": True}]})
    assert (len(valid), len(rejected), received) == (1, 1, 2)
    assert rejected[0].index == 1


def test_unsupported_geometry_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported geometry"):
        parse_feature(feature({"type": "Point", "coordinates": [100, 13]}))


def test_source_hash_is_deterministic() -> None:
    first = parse_feature(feature())
    assert first.source_hash == source_hash(first.geometry, first.properties, first.external_id)
    assert first.source_hash == parse_feature(feature()).source_hash


@pytest.mark.parametrize("period", ["1day", "3days", "7days", "30days"])
def test_supported_sync_periods(period) -> None:
    assert normalize_period(period) == period.upper()


def test_invalid_period_rejected() -> None:
    with pytest.raises(ValueError):
        normalize_period("2days")


def test_geojson_read_endpoint_does_not_expose_secret(monkeypatch) -> None:
    row = SimpleNamespace(
        id=1, external_feature_id="f-1", period="1DAY", source="GISTDA",
        source_observed_at=None, source_updated_at=None,
        synced_at=datetime(2026, 9, 24, tzinfo=timezone.utc), source_properties={"depth": 2},
        source_hash="a" * 64, is_active=True,
    )
    app.dependency_overrides[get_db] = lambda: object()
    monkeypatch.setattr(api, "list_features", lambda db, period, active: [(row, MULTIPOLYGON)])
    try:
        response = TestClient(app).get("/api/v1/gistda/flood?period=1day&active=true")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["type"] == "FeatureCollection"
    assert response.json()["features"][0]["geometry"]["type"] == "MultiPolygon"
    assert "key" not in response.text.lower()


def test_read_endpoint_rejects_invalid_period() -> None:
    response = TestClient(app).get("/api/v1/gistda/flood?period=2days")
    assert response.status_code == 422


class FakeSession:
    """Minimal unit-of-work fake; PostGIS persistence is covered by migration review/integration environments."""
    def __init__(self):
        self.features = []
        self.runs = []
        self.pending = []
        self.rollbacks = 0

    def add(self, value):
        self.pending.append(value)

    def commit(self):
        for value in self.pending:
            if isinstance(value, GistdaSyncRun):
                value.id = len(self.runs) + 1
                self.runs.append(value)
            elif isinstance(value, GistdaFloodFeature):
                value.id = len(self.features) + 1
                self.features.append(value)
        self.pending.clear()

    def rollback(self):
        self.pending.clear()
        self.rollbacks += 1

    def refresh(self, value):
        pass

    def scalars(self, statement):
        return list(self.features)

    def execute(self, statement):
        return None

    def get(self, model, identifier):
        return next(item for item in self.runs if item.id == identifier)


class StubClient:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error

    def fetch_flood_features(self, period):
        if self.error:
            raise self.error
        return self.payload


@pytest.mark.parametrize("period", ["1day", "3days", "7days", "30days"])
def test_each_period_syncs_successfully_and_repeated_sync_is_idempotent(period) -> None:
    db = FakeSession()
    client = StubClient({"type": "FeatureCollection", "features": [feature()]})
    first = sync_gistda_flood(db, period, client)
    second = sync_gistda_flood(db, period, client)
    assert first.status == "SUCCESS" and first.records_inserted == 1
    assert second.status == "SUCCESS" and second.records_unchanged == 1
    assert len(db.features) == 1


def test_partial_sync_records_rejection() -> None:
    db = FakeSession()
    run = sync_gistda_flood(db, "1day", StubClient({"type": "FeatureCollection", "features": [feature(), {"bad": True}]}))
    assert run.status == "PARTIAL"
    assert run.records_received == 2 and run.records_rejected == 1


def test_failed_fetch_preserves_existing_data_and_records_failure() -> None:
    db = FakeSession()
    existing = GistdaFloodFeature(
        id=1, period="1DAY", source="GISTDA", source_hash="x" * 64,
        source_properties={}, synced_at=datetime.now(timezone.utc), is_active=True,
        geometry="MULTIPOLYGON(((100 13,101 13,101 14,100 13)))",
    )
    db.features.append(existing)
    run = sync_gistda_flood(db, "1day", StubClient(error=GistdaAPIError("temporary failure")))
    assert run.status == "FAILED"
    assert existing.is_active is True
    assert db.rollbacks == 1
