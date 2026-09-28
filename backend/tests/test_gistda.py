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
from app.scripts import sync_gistda_flood as sync_cli
from app.services.gistda import normalize_period, parse_collection, parse_feature, source_hash
from app.models.gistda import GistdaFloodFeature, GistdaSyncRun
from app.services.gistda import sync_gistda_flood


POLYGON = {"type": "Polygon", "coordinates": [[[100, 13], [101, 13], [101, 14], [100, 13]]]}
MULTIPOLYGON = {"type": "MultiPolygon", "coordinates": [[[[100, 13], [101, 13], [101, 14], [100, 13]]]]}


def feature(geometry=POLYGON, identifier="f-1"):
    return {"type": "Feature", "id": identifier, "geometry": geometry, "properties": {"date": "2026-09-24T00:00:00Z"}}


def settings(key="secret-test-value", stac_url=""):
    return Settings(
        GISTDA_API_KEY=key,
        GISTDA_API_BASE_URL="https://example.test/api/",
        GISTDA_STAC_BASE_URL=stac_url,
    )


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


def test_single_geojson_page_without_next_link() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={
        "type": "FeatureCollection", "features": [feature(identifier="only")],
    }))
    with GistdaClient(settings(), transport) as client:
        pages = list(client.iter_flood_feature_pages("7days"))
    assert [item["id"] for item in pages[0]["features"]] == ["only"]


def test_stac_discovery_and_relative_and_absolute_geojson_pagination() -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if request.url.path == "/api/features/flood/7days":
            return httpx.Response(200, json={
                "type": "Collection",
                "links": [{"rel": "items", "href": "/stac/flood7/items"}],
            })
        if request.url.path == "/stac/flood7/items":
            return httpx.Response(200, json={
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature", "id": "snapshot", "geometry": None,
                    "properties": {}, "assets": {"data": {
                        "href": "../assets/current", "type": "application/geo+json",
                        "roles": ["Features"],
                    }},
                }],
            })
        if request.url.path == "/stac/assets/current" and request.url.query == b"":
            return httpx.Response(200, json={
                "type": "FeatureCollection", "features": [feature(identifier="p1")],
                "links": [{"rel": "next", "href": "?offset=10"}],
            })
        if request.url.path == "/stac/assets/current" and request.url.params.get("offset") == "10":
            return httpx.Response(200, json={
                "type": "FeatureCollection", "features": [feature(identifier="p2")],
                "links": [{"rel": "next", "href": "https://example.test/final"}],
            })
        if request.url.path == "/final":
            return httpx.Response(200, json={"type": "FeatureCollection", "features": []})
        return httpx.Response(404)

    with GistdaClient(settings(), httpx.MockTransport(handler)) as client:
        result = client.fetch_flood_features("7days")
    assert [item["id"] for item in result["features"]] == ["p1", "p2"]
    assert requested[-2:] == [
        "https://example.test/stac/assets/current?offset=10",
        "https://example.test/final",
    ]


def test_verified_gistda_feature_collection_shape_follows_offset_next(caplog) -> None:
    requests: list[str] = []
    first_ten = [feature(identifier=f"feature-{index}") for index in range(10)]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if request.url.params.get("offset") == "10":
            return httpx.Response(200, json={
                "type": "FeatureCollection", "numberMatched": 57_953,
                "numberReturned": 1, "features": [feature(identifier="feature-10")],
                "links": [],
            })
        return httpx.Response(200, json={
            "type": "FeatureCollection", "numberMatched": 57_953,
            "numberReturned": 10, "features": first_ten,
            "links": [{
                "rel": "next",
                "href": "https://example.test/api/features/flood/7days?offset=10",
                "type": "application/geo+json",
            }],
        })

    with caplog.at_level(logging.INFO):
        with GistdaClient(settings(), httpx.MockTransport(handler)) as client:
            pages = client.iter_flood_feature_pages("7days")
            assert len(next(pages)["features"]) == 10
            assert len(next(pages)["features"]) == 1
            pages.close()
    assert requests[-1].endswith("offset=10")
    assert "page=1 numberReturned=10 next=True" in caplog.text
    assert "page=2 numberReturned=1 next=False" in caplog.text


def test_incomplete_number_matched_without_recognizable_next_fails() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={
        "type": "FeatureCollection", "numberMatched": 57_953,
        "numberReturned": 10, "features": [feature(identifier=str(index)) for index in range(10)],
        "links": [],
    }))
    with GistdaClient(settings(), transport) as client:
        with pytest.raises(GistdaAPIError, match="10 of 57953"):
            client.fetch_flood_features("7days")


@pytest.mark.parametrize("relation", ["NEXT", " next ", ["next"]])
def test_next_relation_is_normalized(relation) -> None:
    assert GistdaClient._link({"links": [{"rel": relation, "href": "next-page"}]}, "next") == "next-page"


def test_live_stac_entrypoint_discovers_current_collection_and_does_not_send_api_key() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        assert "API-Key" not in request.headers
        if request.url.path == "/app-api/services/stac/flood/collections":
            return httpx.Response(200, json={"collections": [{
                "id": "flood7days_r2",
                "links": [{
                    "rel": "self",
                    "href": "/app-api/services/stac/flood/collections/flood7days_r2",
                }],
            }]})
        if request.url.path.endswith("/collections/flood7days_r2"):
            return httpx.Response(200, json={
                "type": "Collection",
                "links": [{"rel": "items", "href": "../../../../proxy/resources/stac/flood/collections/flood7days_r2/items"}],
            })
        if request.url.path.endswith("/collections/flood7days_r2/items"):
            return httpx.Response(200, json={
                "type": "Feature",
                "assets": {"data": {
                    "href": "/features/changing-hash", "type": "application/geo+json",
                    "roles": ["Features"],
                }},
            })
        if request.url.path == "/features/changing-hash":
            return httpx.Response(200, json={
                "type": "FeatureCollection", "features": [feature(identifier="live")],
            })
        return httpx.Response(404)

    stac_url = "https://disaster.gistda.or.th/app-api/services/stac/flood/"
    with GistdaClient(settings(stac_url=stac_url), httpx.MockTransport(handler)) as client:
        result = client.fetch_flood_features("7days")
    assert [item["id"] for item in result["features"]] == ["live"]
    assert paths[0] == "/app-api/services/stac/flood/collections"


def test_stac_asset_is_discovered_by_semantics_without_data_key() -> None:
    responses = iter([
        {"type": "Collection", "links": [{"rel": "items", "href": "items"}]},
        {"type": "Feature", "assets": {"changing-resource-hash": {
            "href": "asset", "type": "application/geo+json", "roles": ["Features"],
        }}},
        {"type": "FeatureCollection", "features": []},
    ])
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=next(responses)))
    with GistdaClient(settings(), transport) as client:
        assert client.fetch_flood_features("1day")["features"] == []


def test_geojson_pagination_cycle_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "type": "FeatureCollection", "features": [],
            "links": [{"rel": "next", "href": str(request.url)}],
        })
    with GistdaClient(settings(), httpx.MockTransport(handler)) as client:
        with pytest.raises(GistdaAPIError, match="cycle"):
            list(client.iter_flood_feature_pages("3days"))


def test_malformed_geojson_page_is_rejected() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={
        "type": "FeatureCollection", "features": "not-an-array",
    }))
    with GistdaClient(settings(), transport) as client:
        with pytest.raises(GistdaAPIError, match="neither GeoJSON"):
            list(client.iter_flood_feature_pages("30days"))


def test_http_failure_on_later_page_is_not_silenced() -> None:
    calls = 0
    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, json={
                "type": "FeatureCollection", "features": [feature()],
                "links": [{"rel": "next", "href": "next"}],
            })
        return httpx.Response(503)
    with GistdaClient(settings(), httpx.MockTransport(handler)) as client:
        with pytest.raises(GistdaAPIError, match="request failed"):
            list(client.iter_flood_feature_pages("1day"))


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
        self.executions = 0

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
        self.executions += 1
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


class PagedStubClient:
    def __init__(self, pages):
        self.pages = pages

    def iter_flood_feature_pages(self, period):
        yield from self.pages


@pytest.mark.parametrize("period", ["1day", "3days", "7days", "30days"])
def test_each_period_syncs_successfully_and_repeated_sync_is_idempotent(period) -> None:
    db = FakeSession()
    client = StubClient({"type": "FeatureCollection", "features": [feature()]})
    first = sync_gistda_flood(db, period, client)
    second = sync_gistda_flood(db, period, client)
    assert first.status == "SUCCESS" and first.records_inserted == 1
    assert second.status == "SUCCESS" and second.records_unchanged == 1
    assert len(db.features) == 1


def test_empty_collection_is_success_and_preserves_last_known_good_data() -> None:
    db = FakeSession()
    existing = GistdaFloodFeature(
        id=1, period="1DAY", source="GISTDA", source_hash="x" * 64,
        source_properties={}, synced_at=datetime.now(timezone.utc), is_active=True,
        geometry="MULTIPOLYGON(((100 13,101 13,101 14,100 13)))",
    )
    db.features.append(existing)

    run = sync_gistda_flood(db, "1day", StubClient({
        "type": "FeatureCollection",
        "features": [],
        "numberMatched": 0,
        "numberReturned": 0,
    }))

    assert run.status == "SUCCESS"
    assert (
        run.records_received,
        run.records_inserted,
        run.records_updated,
        run.records_unchanged,
        run.records_rejected,
    ) == (0, 0, 0, 0, 0)
    assert run.error_message is None
    assert existing.is_active is True
    assert db.executions == 0


@pytest.mark.parametrize("payload", [
    {"type": "FeatureCollection", "features": {}},
    {"type": "Feature", "features": []},
    {},
])
def test_malformed_collection_sync_still_fails(payload) -> None:
    run = sync_gistda_flood(FakeSession(), "1day", StubClient(payload))
    assert run.status == "FAILED"
    assert run.error_message == "ValueError: response is not a GeoJSON FeatureCollection"


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
    assert run.error_message == "GistdaAPIError: temporary failure"


def test_failed_sync_always_records_a_nonempty_sanitized_reason() -> None:
    run = sync_gistda_flood(FakeSession(), "7days", StubClient(error=GistdaAPIError("")))
    assert run.status == "FAILED"
    assert run.error_message == "GistdaAPIError: no details supplied"


def test_cli_prints_failed_sync_reason(monkeypatch, capsys) -> None:
    class SessionContext:
        def __enter__(self):
            return object()
        def __exit__(self, *args):
            return None

    monkeypatch.setattr(sync_cli, "SessionLocal", SessionContext)
    monkeypatch.setattr(sync_cli, "sync_gistda_flood", lambda db, period: SimpleNamespace(
        period="7DAYS", status="FAILED", records_received=0, records_inserted=0,
        records_updated=0, records_unchanged=0, records_rejected=0,
        error_message="GistdaAPIError: STAC discovery failed",
    ))
    monkeypatch.setattr("sys.argv", ["sync_gistda_flood", "--period", "7days"])
    assert sync_cli.main() == 1
    assert "reason: GistdaAPIError: STAC discovery failed" in capsys.readouterr().out


def test_sync_counts_every_feature_across_pages() -> None:
    db = FakeSession()
    run = sync_gistda_flood(db, "7days", PagedStubClient([
        {"type": "FeatureCollection", "features": [feature(identifier="one")]},
        {"type": "FeatureCollection", "features": [feature(identifier="two")]},
        {"type": "FeatureCollection", "features": []},
    ]))
    assert run.status == "SUCCESS"
    assert run.records_received == 2
    assert run.records_inserted == 2
    assert len(db.features) == 2


def test_later_page_failure_marks_run_failed_without_reconciliation() -> None:
    class FailingPagedClient:
        def iter_flood_feature_pages(self, period):
            yield {"type": "FeatureCollection", "features": [feature()]}
            raise GistdaAPIError("later page failed")

    db = FakeSession()
    existing = GistdaFloodFeature(
        id=1, period="7DAYS", source="GISTDA", source_hash="x" * 64,
        source_properties={}, synced_at=datetime.now(timezone.utc), is_active=True,
        geometry="MULTIPOLYGON(((100 13,101 13,101 14,100 13)))",
    )
    db.features.append(existing)
    run = sync_gistda_flood(db, "7days", FailingPagedClient())
    assert run.status == "FAILED"
    assert existing.is_active is True
    assert db.executions == 0
    assert len(db.features) == 1
