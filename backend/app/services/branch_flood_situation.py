"""Multi-source, source-separated branch flood risk assessment."""

from dataclasses import dataclass
from sqlalchemy import text
from app.schemas.branch_flood_situation import SituationCategory
from app.services.flood_impact import impact_cte
from app.services.public_flood_impact import (
    _parameters,
    public_impact_cte,
)


@dataclass(frozen=True)
class SituationPage:
    summary: dict[str, int]
    items: list[dict]


def classify_situation(
    gistda: str,
    public: str,
    gistda_available: bool,
    public_available: bool,
    hdms_detected: bool = False,
    bma_detected: bool = False,
    hdms_available: bool = False,
    bma_available: bool = False,
) -> SituationCategory:
    detected = sum(
        (
            gistda_available and gistda in ("DIRECT", "NEARBY"),
            public_available and public == "PUBLIC_NEARBY",
            hdms_available and hdms_detected,
            bma_available and bma_detected,
        )
    )
    if detected > 1:
        return SituationCategory.MULTI_SOURCE_NEARBY
    if gistda_available and gistda == "DIRECT":
        return SituationCategory.GISTDA_DIRECT
    if gistda_available and gistda == "NEARBY":
        return SituationCategory.GISTDA_NEARBY
    if hdms_available and hdms_detected:
        return SituationCategory.HDMS_NEARBY
    if bma_available and bma_detected:
        return SituationCategory.BMA_NEARBY
    if public_available and public == "PUBLIC_NEARBY":
        return SituationCategory.PUBLIC_NEARBY
    if all((gistda_available, public_available, hdms_available, bma_available)):
        return SituationCategory.NO_NEARBY_FLOOD
    return SituationCategory.SOURCE_DATA_INCOMPLETE


def _combined_query(branch_predicate: str = "lower(b.status) = 'active'") -> str:
    gistda = (
        impact_cte(branch_predicate) + " SELECT * FROM classified"
    ).replace(":proximity_km", ":gistda_proximity_km")
    public = (
        public_impact_cte(branch_predicate) + " SELECT * FROM classified"
    ).replace(":proximity_km", ":public_proximity_km")
    return f"""
WITH gistda_result AS ({gistda}), public_result AS ({public}), combined AS MATERIALIZED (
 SELECT g.*, p.public_impact_classification, p.nearest_report_code,
  p.nearest_report_distance_km, p.nearest_report_verification_status, p.nearest_report_reported_at,
  h.id nearest_hdms_incident_id, h.case_id nearest_hdms_case_id, h.distance_km nearest_hdms_distance_km,
  h.road_code hdms_road_code, h.section_name hdms_section_name, h.road_status hdms_road_status,
  bm.id nearest_bma_observation_id, bm.distance_km nearest_bma_distance_km,
  bm.station_name bma_station_name, bm.road_name bma_road_name,
  bm.water_level_cm bma_water_level_cm, bm.source_status bma_source_status,
 CASE
  WHEN ((:gistda_available AND g.impact_classification IN ('DIRECT','NEARBY'))::int +
        (:public_available AND p.public_impact_classification='PUBLIC_NEARBY')::int +
        (:hdms_available AND h.id IS NOT NULL)::int + (:bma_available AND bm.id IS NOT NULL)::int) > 1 THEN 'MULTI_SOURCE_NEARBY'
  WHEN :gistda_available AND g.impact_classification='DIRECT' THEN 'GISTDA_DIRECT'
  WHEN :gistda_available AND g.impact_classification='NEARBY' THEN 'GISTDA_NEARBY'
  WHEN :hdms_available AND h.id IS NOT NULL THEN 'HDMS_NEARBY'
  WHEN :bma_available AND bm.id IS NOT NULL THEN 'BMA_NEARBY'
  WHEN :public_available AND p.public_impact_classification='PUBLIC_NEARBY' THEN 'PUBLIC_NEARBY'
  WHEN :gistda_available AND :public_available AND :hdms_available AND :bma_available THEN 'NO_NEARBY_FLOOD'
  ELSE 'SOURCE_DATA_INCOMPLETE' END situation
 FROM gistda_result g JOIN public_result p USING (store_number)
 LEFT JOIN LATERAL (SELECT hi.id,hi.case_id,hi.road_code,hi.section_name,hi.road_status,
   ST_Distance(hi.road_geometry::geography, ST_SetSRID(ST_MakePoint(g.longitude,g.latitude),4326)::geography)/1000 distance_km
   FROM hdms_incidents hi WHERE hi.is_active IS TRUE AND hi.geometry_available IS TRUE
   AND ST_DWithin(hi.road_geometry::geography,ST_SetSRID(ST_MakePoint(g.longitude,g.latitude),4326)::geography,:hdms_proximity_km*1000)
   ORDER BY (hi.road_status='IMPASSABLE') DESC,distance_km LIMIT 1) h ON TRUE
 LEFT JOIN LATERAL (SELECT bo.id,bo.station_name,bo.road_name,bo.water_level_cm,bo.source_status,
   ST_Distance(bo.location::geography,ST_SetSRID(ST_MakePoint(g.longitude,g.latitude),4326)::geography)/1000 distance_km
   FROM bma_road_water_observations bo WHERE bo.is_active IS TRUE
   AND ST_DWithin(bo.location::geography,ST_SetSRID(ST_MakePoint(g.longitude,g.latitude),4326)::geography,:bma_proximity_km*1000)
   ORDER BY distance_km LIMIT 1) bm ON TRUE)
"""


def _item(row, period, lookback, ga, pa, ha, ba):
    row = dict(row)
    return {
        "store_number": row["store_number"],
        "store_name": row["store_name"],
        "city": row["city"],
        "latitude": float(row["latitude"]),
        "longitude": float(row["longitude"]),
        "situation": row["situation"],
        "gistda": {
            "data_available": ga,
            "period": period,
            "classification": row["impact_classification"] if ga else None,
            "inside_flood_polygon": row["inside_flood_polygon"],
            "nearest_flood_distance_km": row["nearest_flood_distance_km"],
            "nearest_flood_feature_id": row["nearest_flood_feature_id"],
        },
        "hdms": {
            "data_available": ha,
            "evidence_detected": ha and row["nearest_hdms_incident_id"] is not None,
            "nearest_incident_id": row["nearest_hdms_incident_id"],
            "nearest_case_id": row["nearest_hdms_case_id"],
            "nearest_distance_km": row["nearest_hdms_distance_km"],
            "road_code": row["hdms_road_code"],
            "section_name": row["hdms_section_name"],
            "road_status": row["hdms_road_status"],
        },
        "bma": {
            "data_available": ba,
            "evidence_detected": ba and row["nearest_bma_observation_id"] is not None,
            "nearest_observation_id": row["nearest_bma_observation_id"],
            "nearest_distance_km": row["nearest_bma_distance_km"],
            "station_name": row["bma_station_name"],
            "road_name": row["bma_road_name"],
            "water_level_cm": row["bma_water_level_cm"],
            "source_status": row["bma_source_status"],
        },
        "public": {
            "data_available": pa,
            "lookback_hours": lookback,
            "classification": row["public_impact_classification"] if pa else None,
            "nearest_report_code": row["nearest_report_code"],
            "nearest_report_distance_km": row["nearest_report_distance_km"],
            "nearest_report_verification_status": row[
                "nearest_report_verification_status"
            ],
            "nearest_report_reported_at": row["nearest_report_reported_at"],
        },
    }


_SOURCE_AVAILABILITY = text("""
SELECT
 (EXISTS(SELECT 1 FROM gistda_flood_features
          WHERE period=:period AND is_active IS TRUE)
  OR EXISTS(SELECT 1 FROM gistda_sync_runs
            WHERE period=:period AND status IN ('SUCCESS','PARTIAL'))) gistda,
 (EXISTS(SELECT 1 FROM hdms_incidents WHERE is_active IS TRUE)
  OR EXISTS(SELECT 1 FROM hdms_sync_runs
            WHERE status IN ('SUCCESS','PARTIAL'))) hdms,
 (EXISTS(SELECT 1 FROM bma_road_water_observations WHERE is_active IS TRUE)
  OR EXISTS(SELECT 1 FROM bma_sync_runs
            WHERE status IN ('SUCCESS','PARTIAL'))) bma,
 TRUE public
""")


def source_availability(db, period: str) -> tuple[bool, bool, bool, bool]:
    """Return GISTDA, Public, HDMS and BMA assessability, not evidence presence.

    Public reports are an internal, directly queried data source, so a successful
    database query assesses it even when the selected window contains no rows.
    Synced sources require retained data or a successful/partial sync run; an
    empty successful run therefore remains available.
    """
    status = db.execute(_SOURCE_AVAILABILITY, {"period": period}).mappings().one()
    return tuple(bool(status[key]) for key in ("gistda", "public", "hdms", "bma"))


def _params(db, period, gkm, pkm, hkm, bkm, lookback):
    params = _parameters(db, pkm, lookback)
    ga, pa, ha, ba = source_availability(db, period)
    return (
        {
            **params,
            "period": period,
            "gistda_proximity_km": gkm,
            "public_proximity_km": pkm,
            "hdms_proximity_km": hkm,
            "bma_proximity_km": bkm,
            "gistda_available": ga,
            "public_available": pa,
            "hdms_available": ha,
            "bma_available": ba,
        },
        ga,
        pa,
        ha,
        ba,
    )


def calculate_situations(
    db, period, gkm, pkm, hkm, bkm, lookback, situation, limit, offset
):
    params, ga, pa, ha, ba = _params(db, period, gkm, pkm, hkm, bkm, lookback)
    # Both consumers share one spatial assessment. Aggregate before filtering or
    # pagination, and keep a summary row even when the requested page is empty.
    rows = db.execute(
        text(
            _combined_query()
            + """, summary AS (
 SELECT jsonb_object_agg(lower(situation), count) AS counts
 FROM (SELECT situation, count(*) AS count FROM combined GROUP BY situation) counts
)
SELECT summary.counts AS summary_counts, page.*
FROM summary LEFT JOIN LATERAL (
 SELECT * FROM combined
 WHERE (CAST(:situation AS text) IS NULL OR situation=:situation)
 ORDER BY store_number LIMIT :limit OFFSET :offset
) page ON TRUE
ORDER BY page.store_number
"""
        ),
        {
            **params,
            "situation": situation.value if situation else None,
            "limit": limit,
            "offset": offset,
        },
    ).mappings()
    summary = {c.value.lower(): 0 for c in SituationCategory}
    items = []
    for row in rows:
        summary.update(row["summary_counts"] or {})
        if row["store_number"] is not None:
            items.append(_item(row, period, lookback, ga, pa, ha, ba))
    return SituationPage(summary, items)


def calculate_situation(db, store_number, period, gkm, pkm, hkm, bkm, lookback):
    params, ga, pa, ha, ba = _params(db, period, gkm, pkm, hkm, bkm, lookback)
    row = (
        db.execute(
            text(
                _combined_query(
                    "lower(b.status) = 'active' AND b.store_number = :store_number"
                )
                + " SELECT * FROM combined"
            ),
            {**params, "store_number": store_number},
        )
        .mappings()
        .one_or_none()
    )
    return _item(row, period, lookback, ga, pa, ha, ba) if row else None
