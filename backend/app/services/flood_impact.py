"""PostGIS-backed GISTDA-to-branch impact/proximity calculations."""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.flood_impact import ImpactClassification


@dataclass(frozen=True)
class ImpactPage:
    data_available: bool
    summary: dict[str, int]
    items: list[dict]


# The LATERAL subquery produces at most one flood row per branch.  The geography
# KNN operator uses ix_gistda_features_geography_gist, while ST_Distance returns
# an accurate spheroidal distance in metres.
_IMPACT_CTE = """
WITH active_flood AS (
    SELECT id, geometry
    FROM gistda_flood_features
    WHERE period = :period AND is_active IS TRUE
), impacts AS (
    SELECT b.store_number, b.store_name, b.city, b.latitude, b.longitude,
           b.status AS branch_status, nearest.id AS nearest_flood_feature_id,
           CASE WHEN nearest.id IS NULL THEN NULL
                WHEN ST_Intersects(b.location::geometry, nearest.geometry) THEN 0.0
                ELSE ST_Distance(b.location, nearest.geometry::geography) / 1000.0
           END AS nearest_flood_distance_km,
           COALESCE(ST_Intersects(b.location::geometry, nearest.geometry), FALSE)
               AS inside_flood_polygon
    FROM branches b
    LEFT JOIN LATERAL (
        SELECT f.id, f.geometry
        FROM active_flood f
        ORDER BY f.geometry::geography <-> b.location
        LIMIT 1
    ) nearest ON TRUE
), classified AS (
    SELECT *, CASE
        WHEN inside_flood_polygon THEN 'DIRECT'
        WHEN nearest_flood_distance_km <= :proximity_km THEN 'NEARBY'
        ELSE 'NONE'
    END AS impact_classification
    FROM impacts
)
"""


def _row(row, period: str) -> dict:
    item = dict(row)
    item["latitude"] = float(item["latitude"])
    item["longitude"] = float(item["longitude"])
    distance = item["nearest_flood_distance_km"]
    item["nearest_flood_distance_km"] = float(distance) if distance is not None else None
    item["gistda_period"] = period
    return item


def calculate_branch_impacts(
    db: Session,
    period: str,
    proximity_km: float,
    classification: ImpactClassification | None,
    limit: int,
    offset: int,
) -> ImpactPage:
    parameters = {"period": period, "proximity_km": proximity_km}
    available = bool(db.scalar(text("""
        SELECT EXISTS (
            SELECT 1 FROM gistda_flood_features
            WHERE period = :period AND is_active IS TRUE
        )
    """), {"period": period}))

    counts = db.execute(text(_IMPACT_CTE + """
        SELECT impact_classification, count(*) AS count
        FROM classified GROUP BY impact_classification
    """), parameters).mappings()
    summary = {"direct": 0, "nearby": 0, "none": 0}
    for count in counts:
        summary[count["impact_classification"].lower()] = count["count"]

    item_params = {**parameters, "classification": classification.value if classification else None,
                   "limit": limit, "offset": offset}
    rows = db.execute(text(_IMPACT_CTE + """
        SELECT * FROM classified
        WHERE (CAST(:classification AS text) IS NULL OR impact_classification = :classification)
        ORDER BY store_number
        LIMIT :limit OFFSET :offset
    """), item_params).mappings()
    return ImpactPage(available, summary, [_row(row, period) for row in rows])


def calculate_branch_impact(db: Session, store_number: str, period: str, proximity_km: float) -> tuple[bool, dict] | None:
    branch_exists = db.scalar(text("SELECT EXISTS (SELECT 1 FROM branches WHERE store_number = :store_number)"),
                              {"store_number": store_number})
    if not branch_exists:
        return None
    available = bool(db.scalar(text("""
        SELECT EXISTS (SELECT 1 FROM gistda_flood_features
                       WHERE period = :period AND is_active IS TRUE)
    """), {"period": period}))
    row = db.execute(text(_IMPACT_CTE + """
        SELECT * FROM classified WHERE store_number = :store_number
    """), {"period": period, "proximity_km": proximity_km, "store_number": store_number}).mappings().one()
    return available, _row(row, period)
