"""Execute the performance fix and its query plans in an isolated PostGIS DB."""

import os
from itertools import product
from pathlib import Path
from urllib.parse import urlparse

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.schemas.branch_flood_situation import SituationCategory
from app.services import branch_flood_situation as service

pytestmark = pytest.mark.integration


@pytest.fixture
def db():
    url = os.environ.get("DATABASE_URL", "")
    if "test" not in urlparse(url).path.lower():
        pytest.skip("DATABASE_URL must point to a dedicated test database")
    engine = create_engine(url)
    config = Config(str(Path(__file__).parents[2] / "database" / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    with Session(engine) as session:
        session.execute(text("""TRUNCATE branches, gistda_flood_features,
            flood_reports, hdms_incidents, bma_road_water_observations,
            gistda_sync_runs, hdms_sync_runs, bma_sync_runs,
            system_configurations RESTART IDENTITY CASCADE"""))
        session.execute(text("""
            INSERT INTO branches(store_number,store_name,city,latitude,longitude,location,status)
            SELECT i::text,'Test '||i,'Test',0,i,ST_Point(i,0)::geography,
                   CASE WHEN i=6 THEN 'inactive' ELSE 'ACTIVE' END
            FROM generate_series(0,7) i
        """))
        session.execute(text("""
            INSERT INTO gistda_flood_features(period,geometry,synced_at,source_properties,source_hash,is_active)
            SELECT '3DAYS',ST_Multi(ST_Buffer(ST_Point(lon,0),0.001)),now(),'{}',lon::text,true
            FROM (VALUES (0.0),(1.02),(7.0)) p(lon)
        """))
        session.execute(text("""
            INSERT INTO hdms_incidents(source_record_id,road_status,is_active,road_geometry,
                                       geometry_available,source_metadata,synced_at)
            VALUES ('near','IMPASSABLE',true,ST_GeomFromText('LINESTRING(2 0,2.001 0)',4326),true,'{}',now()),
                   ('multi','IMPASSABLE',true,ST_GeomFromText('LINESTRING(7 0,7.001 0)',4326),true,'{}',now())
        """))
        session.execute(text("""
            INSERT INTO bma_road_water_observations(source_record_id,station_id,source_latitude,
                source_longitude,location,fingerprint,is_active,synced_at)
            VALUES ('near','near',0,3,ST_Point(3,0),'near',true,now()),
                   ('multi','multi',0,7,ST_Point(7,0),'multi',true,now())
        """))
        session.execute(text("""
            INSERT INTO flood_reports(report_code,flood_latitude,flood_longitude,flood_location,
                water_level_cm,verification_status,verification_reason,source,status,reported_at)
            SELECT 'public-'||i,0,i,ST_Point(i,0)::geography,10,'VERIFIED','TEST','PUBLIC','ACTIVE',now()
            FROM (VALUES (4),(7)) p(i)
        """))
        yield session
        session.rollback()
    engine.dispose()


def _page(db, situation=None, limit=100, offset=0):
    return service.calculate_situations(db, "3DAYS", 5, 5, 5, 5, 24, situation, limit, offset)


def test_full_population_summary_filters_pagination_and_empty_pages(db):
    full = _page(db)
    assert [i["store_number"] for i in full.items] == ["0", "1", "2", "3", "4", "5", "7"]
    assert full.summary == {c.value.lower(): int(c != SituationCategory.SOURCE_DATA_INCOMPLETE)
                            for c in SituationCategory}
    for offset, number in enumerate(["0", "1", "2", "3", "4", "5", "7"]):
        page = _page(db, limit=1, offset=offset)
        assert [i["store_number"] for i in page.items] == [number]
        assert page.summary == full.summary
    for category in SituationCategory:
        page = _page(db, situation=category, limit=1)
        assert all(i["situation"] == category for i in page.items)
        assert page.summary == full.summary
        assert _page(db, situation=category, offset=999).items == []
        assert _page(db, situation=category, offset=999).summary == full.summary
    for item in full.items:
        assert service.calculate_situation(db, item["store_number"], "3DAYS", 5, 5, 5, 5, 24) == item
    for number in ("6", "missing"):
        assert service.calculate_situation(db, number, "3DAYS", 5, 5, 5, 5, 24) is None
    db.execute(text("DELETE FROM branches"))
    assert _page(db).items == []
    assert all(count == 0 for count in _page(db).summary.values())


def _nodes(plan):
    yield plan
    for child in plan.get("Plans", []):
        yield from _nodes(child)


def test_query_plans_assess_only_requested_branch_and_materialize_list_once(db):
    calls = []

    class RecordingDb:
        def scalar(self, *args, **kwargs):
            return db.scalar(*args, **kwargs)

        def execute(self, statement, parameters):
            calls.append((str(statement), parameters))
            return db.execute(statement, parameters)

    recording = RecordingDb()
    service.calculate_situation(recording, "0", "3DAYS", 5, 5, 5, 5, 24)
    sql, params = calls[-1]
    plan = db.execute(text("EXPLAIN (ANALYZE, FORMAT JSON) " + sql), params).scalar()[0]["Plan"]
    branch_scans = [n for n in _nodes(plan) if n.get("Relation Name") == "branches"]
    assert len(branch_scans) == 2
    assert all(n["Actual Rows"] == 1 and n["Actual Loops"] == 1 for n in branch_scans)
    limits = [n for n in _nodes(plan) if n["Node Type"] == "Limit"]
    assert all(n["Actual Loops"] == 1 for n in limits)
    calls.clear()
    _page(recording, limit=1)
    assert len(calls) == 2  # Source availability plus one assessment, not two.
    sql, params = calls[-1]
    plan = db.execute(text("EXPLAIN (ANALYZE, FORMAT JSON) " + sql), params).scalar()[0]["Plan"]
    combined = [n for n in _nodes(plan) if n.get("Subplan Name") == "CTE combined"]
    assert len(combined) == 1
    assert (combined[0]["Actual Rows"], combined[0]["Actual Loops"]) == (7, 1)


def test_empty_successful_sources_and_genuinely_unavailable_sources(db):
    for table in ("gistda_flood_features", "hdms_incidents", "bma_road_water_observations", "flood_reports"):
        db.execute(text(f"DELETE FROM {table}"))
    assert service.source_availability(db, "3DAYS") == (False, True, False, False)
    assert _page(db).summary["source_data_incomplete"] == 7
    for table in ("gistda_sync_runs", "hdms_sync_runs", "bma_sync_runs"):
        period = ",period" if table == "gistda_sync_runs" else ""
        value = ",'3DAYS'" if period else ""
        db.execute(text(f"INSERT INTO {table}(status,started_at{period}) VALUES ('SUCCESS',now(){value})"))
    assert service.source_availability(db, "3DAYS") == (True, True, True, True)
    page = _page(db)
    assert page.summary["no_nearby_flood"] == 7
    assert all(i["public"]["classification"] == "PUBLIC_NONE" for i in page.items)
    db.execute(text("UPDATE hdms_sync_runs SET status='FAILED'"))
    assert _page(db).summary["source_data_incomplete"] == 7


@pytest.mark.parametrize("availability", list(product((False, True), repeat=4)))
def test_sql_classification_matches_precedence_and_availability(db, availability):
    params, *_ = service._params(db, "3DAYS", 5, 5, 5, 5, 24)
    ga, pa, ha, ba = availability
    params.update(gistda_available=ga, public_available=pa, hdms_available=ha, bma_available=ba)
    rows = db.execute(text(service._combined_query() + " SELECT * FROM combined"), params).mappings()
    for row in rows:
        expected = service.classify_situation(
            row["impact_classification"], row["public_impact_classification"], ga, pa,
            row["nearest_hdms_incident_id"] is not None, row["nearest_bma_observation_id"] is not None, ha, ba,
        )
        assert row["situation"] == expected
        item = service._item(row, "3DAYS", 24, ga, pa, ha, ba)
        assert item["gistda"]["data_available"] == ga
        assert item["public"]["data_available"] == pa
        assert item["hdms"]["evidence_detected"] == (ha and row["nearest_hdms_incident_id"] is not None)
        assert item["bma"]["evidence_detected"] == (ba and row["nearest_bma_observation_id"] is not None)


def test_public_window_verification_and_inactive_evidence_regression(db):
    db.execute(text("UPDATE flood_reports SET reported_at=now()-interval '25 hours'"))
    assert service.calculate_situation(db, "4", "3DAYS", 5, 5, 5, 5, 24)["situation"] == "NO_NEARBY_FLOOD"
    db.execute(text("UPDATE flood_reports SET reported_at=now(),verification_status='UNVERIFIED'"))
    assert service.calculate_situation(db, "4", "3DAYS", 5, 5, 5, 5, 24)["situation"] == "NO_NEARBY_FLOOD"
    db.execute(text("UPDATE flood_reports SET verification_status='PENDING_REVIEW'"))
    assert service.calculate_situation(db, "4", "3DAYS", 5, 5, 5, 5, 24)["situation"] == "PUBLIC_NEARBY"
    db.execute(text("UPDATE flood_reports SET status='CLOSED'"))
    assert service.calculate_situation(db, "4", "3DAYS", 5, 5, 5, 5, 24)["situation"] == "NO_NEARBY_FLOOD"
