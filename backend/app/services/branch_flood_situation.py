"""Batch aggregation of the two source-specific branch engines."""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.branch_flood_situation import SituationCategory
from app.services.flood_impact import gistda_data_available, impact_cte
from app.services.public_flood_impact import (
    _parameters, public_data_available, public_impact_cte,
)


@dataclass(frozen=True)
class SituationPage:
    summary: dict[str, int]
    items: list[dict]


def classify_situation(gistda: str, public: str, gistda_available: bool,
                       public_available: bool) -> SituationCategory:
    """Apply factual precedence; DIRECT remains knowable despite missing public data."""
    if gistda_available and gistda == "DIRECT":
        return SituationCategory.GISTDA_DIRECT
    if not gistda_available or not public_available:
        return SituationCategory.SOURCE_DATA_INCOMPLETE
    if gistda == "NEARBY" and public == "PUBLIC_NEARBY":
        return SituationCategory.MULTI_SOURCE_NEARBY
    if gistda == "NEARBY":
        return SituationCategory.GISTDA_NEARBY
    if public == "PUBLIC_NEARBY":
        return SituationCategory.PUBLIC_NEARBY
    return SituationCategory.NO_NEARBY_FLOOD


def _combined_query() -> str:
    # Embed the exact canonical source queries, scoped to active branches. This
    # keeps spatial and eligibility rules shared with their existing APIs.
    gistda = impact_cte("lower(b.status) = 'active'") + " SELECT * FROM classified"
    public = public_impact_cte("lower(b.status) = 'active'") + " SELECT * FROM classified"
    gistda = gistda.replace(":proximity_km", ":gistda_proximity_km")
    public = public.replace(":proximity_km", ":public_proximity_km")
    return f"""
WITH gistda_result AS ({gistda}), public_result AS ({public}), combined AS (
 SELECT g.*, p.public_impact_classification, p.nearest_report_code,
        p.nearest_report_distance_km, p.nearest_report_verification_status,
        p.nearest_report_reported_at,
 CASE
  WHEN :gistda_available AND g.impact_classification = 'DIRECT' THEN 'GISTDA_DIRECT'
  WHEN NOT :gistda_available OR NOT :public_available THEN 'SOURCE_DATA_INCOMPLETE'
  WHEN g.impact_classification = 'NEARBY' AND p.public_impact_classification = 'PUBLIC_NEARBY'
    THEN 'MULTI_SOURCE_NEARBY'
  WHEN g.impact_classification = 'NEARBY' THEN 'GISTDA_NEARBY'
  WHEN p.public_impact_classification = 'PUBLIC_NEARBY' THEN 'PUBLIC_NEARBY'
  ELSE 'NO_NEARBY_FLOOD' END AS situation
 FROM gistda_result g JOIN public_result p USING (store_number)
)
"""


def _item(row, period: str, lookback: int, ga: bool, pa: bool) -> dict:
    row = dict(row)
    return {
        "store_number": row["store_number"], "store_name": row["store_name"],
        "city": row["city"], "latitude": float(row["latitude"]),
        "longitude": float(row["longitude"]), "situation": row["situation"],
        "gistda": {"data_available": ga, "period": period,
            "classification": row["impact_classification"] if ga else None,
            "inside_flood_polygon": row["inside_flood_polygon"],
            "nearest_flood_distance_km": row["nearest_flood_distance_km"],
            "nearest_flood_feature_id": row["nearest_flood_feature_id"]},
        "public": {"data_available": pa, "lookback_hours": lookback,
            "classification": row["public_impact_classification"] if pa else None,
            "nearest_report_code": row["nearest_report_code"],
            "nearest_report_distance_km": row["nearest_report_distance_km"],
            "nearest_report_verification_status": row["nearest_report_verification_status"],
            "nearest_report_reported_at": row["nearest_report_reported_at"]},
    }


def _params(db, period, gistda_km, public_km, lookback):
    params = _parameters(db, public_km, lookback)
    ga = gistda_data_available(db, period)
    pa = public_data_available(db, params)
    return {**params, "period": period, "gistda_proximity_km": gistda_km,
            "public_proximity_km": public_km, "gistda_available": ga,
            "public_available": pa}, ga, pa


def calculate_situations(db: Session, period: str, gistda_km: float, public_km: float,
                         lookback: int, situation: SituationCategory | None,
                         limit: int, offset: int) -> SituationPage:
    params, ga, pa = _params(db, period, gistda_km, public_km, lookback)
    counts = db.execute(text(_combined_query() +
        " SELECT situation, count(*) count FROM combined GROUP BY situation"), params).mappings()
    summary = {category.value.lower(): 0 for category in SituationCategory}
    for count in counts:
        summary[count["situation"].lower()] = count["count"]
    rows = db.execute(text(_combined_query() + """
        SELECT * FROM combined
        WHERE (CAST(:situation AS text) IS NULL OR situation = :situation)
        ORDER BY store_number LIMIT :limit OFFSET :offset
    """), {**params, "situation": situation.value if situation else None,
            "limit": limit, "offset": offset}).mappings()
    return SituationPage(summary, [_item(row, period, lookback, ga, pa) for row in rows])


def calculate_situation(db: Session, store_number: str, period: str, gistda_km: float,
                        public_km: float, lookback: int) -> dict | None:
    params, ga, pa = _params(db, period, gistda_km, public_km, lookback)
    row = db.execute(text(_combined_query() +
        " SELECT * FROM combined WHERE store_number = :store_number"),
        {**params, "store_number": store_number}).mappings().one_or_none()
    return _item(row, period, lookback, ga, pa) if row else None
