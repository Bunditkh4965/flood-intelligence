"""PostGIS-backed public flood observation proximity calculations."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.flood_report import SystemConfiguration
from app.schemas.public_flood_impact import PublicImpactClassification

ELIGIBLE_STATUSES_CONFIG_KEY = "PUBLIC_IMPACT_VERIFICATION_STATUSES"
DEFAULT_ELIGIBLE_STATUSES = ("VERIFIED", "PENDING_REVIEW")
KNOWN_VERIFICATION_STATUSES = frozenset((*DEFAULT_ELIGIBLE_STATUSES, "UNVERIFIED"))


@dataclass(frozen=True)
class PublicImpactPage:
    data_available: bool
    summary: dict[str, int]
    items: list[dict]


def get_eligible_verification_statuses(db: Session) -> tuple[str, ...]:
    """Read the configurable allow-list, safely falling back to domain defaults."""
    configured = db.scalar(select(SystemConfiguration.value).where(
        SystemConfiguration.key == ELIGIBLE_STATUSES_CONFIG_KEY
    ))
    if configured:
        statuses = tuple(dict.fromkeys(part.strip().upper() for part in configured.split(",") if part.strip()))
        if statuses and all(status in KNOWN_VERIFICATION_STATUSES for status in statuses):
            return statuses
    return DEFAULT_ELIGIBLE_STATUSES


# The lateral query yields at most one eligible observation for each branch.
# Both operands are geography points: KNN finds the nearest candidate using the
# GiST index and ST_Distance supplies spheroidal metres for the final distance.
def public_impact_cte(branch_predicate: str = "TRUE") -> str:
    """Build the canonical public-report impact query for a branch set."""
    return f"""
WITH eligible_reports AS (
    SELECT id, report_code, flood_location, verification_status, reported_at
    FROM flood_reports
    WHERE source = 'PUBLIC'
      AND status = 'ACTIVE'
      AND verification_status = ANY(CAST(:eligible_statuses AS text[]))
      AND reported_at >= :reported_from
), impacts AS (
    SELECT b.store_number, b.store_name, b.city, b.latitude, b.longitude,
           b.status AS branch_status,
           nearest.report_code AS nearest_report_code,
           CASE WHEN nearest.id IS NULL THEN NULL
                ELSE ST_Distance(b.location, nearest.flood_location) / 1000.0
           END AS nearest_report_distance_km,
           nearest.verification_status AS nearest_report_verification_status,
           nearest.reported_at AS nearest_report_reported_at
    FROM branches b
    LEFT JOIN LATERAL (
        SELECT r.id, r.report_code, r.flood_location, r.verification_status, r.reported_at
        FROM eligible_reports r
        ORDER BY r.flood_location <-> b.location, r.id
        LIMIT 1
    ) nearest ON TRUE
    WHERE {branch_predicate}
), classified AS (
    SELECT *, CASE
        WHEN nearest_report_distance_km <= :proximity_km THEN 'PUBLIC_NEARBY'
        ELSE 'PUBLIC_NONE'
    END AS public_impact_classification
    FROM impacts
)
"""


_PUBLIC_IMPACT_CTE = public_impact_cte()


def _row(row) -> dict:
    item = dict(row)
    item["latitude"] = float(item["latitude"])
    item["longitude"] = float(item["longitude"])
    distance = item["nearest_report_distance_km"]
    item["nearest_report_distance_km"] = float(distance) if distance is not None else None
    item["source"] = "PUBLIC"
    return item


def _parameters(db: Session, proximity_km: float, lookback_hours: int) -> dict:
    return {
        "eligible_statuses": list(get_eligible_verification_statuses(db)),
        "reported_from": datetime.now(timezone.utc) - timedelta(hours=lookback_hours),
        "proximity_km": proximity_km,
    }


def public_data_available(db: Session, parameters: dict) -> bool:
    return bool(db.scalar(text("""
        SELECT EXISTS (
            SELECT 1 FROM flood_reports
            WHERE source = 'PUBLIC' AND status = 'ACTIVE'
              AND verification_status = ANY(CAST(:eligible_statuses AS text[]))
              AND reported_at >= :reported_from
        )
    """), parameters))


def calculate_public_branch_impacts(
    db: Session, proximity_km: float, lookback_hours: int,
    classification: PublicImpactClassification | None, limit: int, offset: int,
) -> PublicImpactPage:
    parameters = _parameters(db, proximity_km, lookback_hours)
    available = public_data_available(db, parameters)

    counts = db.execute(text(_PUBLIC_IMPACT_CTE + """
        SELECT public_impact_classification, count(*) AS count
        FROM classified GROUP BY public_impact_classification
    """), parameters).mappings()
    summary = {"nearby": 0, "none": 0}
    for count in counts:
        summary[count["public_impact_classification"].removeprefix("PUBLIC_").lower()] = count["count"]

    item_parameters = {
        **parameters,
        "classification": classification.value if classification else None,
        "limit": limit,
        "offset": offset,
    }
    rows = db.execute(text(_PUBLIC_IMPACT_CTE + """
        SELECT * FROM classified
        WHERE (CAST(:classification AS text) IS NULL
               OR public_impact_classification = :classification)
        ORDER BY store_number
        LIMIT :limit OFFSET :offset
    """), item_parameters).mappings()
    return PublicImpactPage(available, summary, [_row(row) for row in rows])


def calculate_public_branch_impact(
    db: Session, store_number: str, proximity_km: float, lookback_hours: int,
) -> tuple[bool, dict] | None:
    branch_exists = db.scalar(text(
        "SELECT EXISTS (SELECT 1 FROM branches WHERE store_number = :store_number)"
    ), {"store_number": store_number})
    if not branch_exists:
        return None
    parameters = _parameters(db, proximity_km, lookback_hours)
    available = public_data_available(db, parameters)
    row = db.execute(text(_PUBLIC_IMPACT_CTE + """
        SELECT * FROM classified WHERE store_number = :store_number
    """), {**parameters, "store_number": store_number}).mappings().one()
    return available, _row(row)
