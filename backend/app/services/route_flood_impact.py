"""PostGIS-only route flood detection; this module makes no routing decision."""

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.route_flood_impact import RouteFloodSituation
from app.services.public_flood_impact import get_eligible_verification_statuses


class InvalidRouteGeometry(ValueError):
    pass


def classify_route_flood_impact(gistda_matches: bool, public_matches: bool,
                                gistda_available: bool, public_available: bool) -> RouteFloodSituation:
    # Detected evidence takes precedence over an unavailable second source.
    if gistda_matches and public_matches:
        return RouteFloodSituation.MULTI_SOURCE_ROUTE_IMPACT
    if gistda_matches:
        return RouteFloodSituation.GISTDA_DIRECT
    if public_matches:
        return RouteFloodSituation.PUBLIC_NEARBY_ROUTE
    if not gistda_available or not public_available:
        return RouteFloodSituation.SOURCE_DATA_INCOMPLETE
    return RouteFloodSituation.NO_DETECTED_ROUTE_IMPACT


_ROUTE_SQL = """
SELECT route_id, origin_type, origin_code, destination_type, destination_code,
       vehicle_profile, routing_provider, distance_km, duration_minutes, calculated_at,
       GeometryType(route_geometry) = 'LINESTRING' AND ST_SRID(route_geometry) = 4326
         AND NOT ST_IsEmpty(route_geometry) AND ST_NPoints(route_geometry) >= 2 AS valid_geometry
FROM transport_routes WHERE route_id = :route_id
"""

# The indexed polygon is the first ST_Intersects argument. Intersection output is
# represented by one lon/lat point rather than duplicating potentially large geometry.
_GISTDA_SQL = """
SELECT f.id AS feature_id, f.external_feature_id, f.period, f.source,
       f.source_observed_at, f.source_updated_at, f.synced_at, TRUE AS intersects,
       ST_AsGeoJSON(ST_PointOnSurface(ST_Intersection(f.geometry, r.route_geometry)))::json
         AS representative_intersection
FROM transport_routes r
JOIN gistda_flood_features f
  ON f.period = :period AND f.is_active IS TRUE
 AND ST_Intersects(f.geometry, r.route_geometry)
WHERE r.route_id = :route_id ORDER BY f.id
"""

# flood_location is geography and is kept on the indexed side. Casting the real
# persisted LineString to geography gives an inclusive, metre-based threshold.
_PUBLIC_SQL = """
SELECT p.id AS report_id, p.report_code, p.verification_status,
       ST_Distance(p.flood_location, r.route_geometry::geography) AS distance_to_route_meters,
       p.water_level_cm, p.road_status,
       CASE :vehicle_profile WHEN '4W' THEN p.vehicle_4w_status
            WHEN '6W' THEN p.vehicle_6w_status ELSE p.vehicle_10w_status END AS vehicle_status,
       p.reported_at
FROM transport_routes r
JOIN flood_reports p ON p.source = 'PUBLIC' AND p.status = 'ACTIVE'
 AND p.verification_status = ANY(CAST(:eligible_statuses AS text[]))
 AND p.reported_at >= :reported_from
 AND ST_DWithin(p.flood_location, r.route_geometry::geography, :radius_meters)
WHERE r.route_id = :route_id
ORDER BY distance_to_route_meters, p.id
"""


def evaluate_route_flood_impact(db: Session, route_id: str, period: str,
                                radius_meters: float, lookback_hours: int) -> dict | None:
    route = db.execute(text(_ROUTE_SQL), {"route_id": route_id}).mappings().one_or_none()
    if route is None:
        return None
    if not route["valid_geometry"]:
        raise InvalidRouteGeometry("Persisted route geometry is not a valid SRID 4326 LineString")

    reported_from = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    common = {"route_id": route_id, "period": period, "radius_meters": radius_meters,
              "reported_from": reported_from,
              "eligible_statuses": list(get_eligible_verification_statuses(db)),
              "vehicle_profile": route["vehicle_profile"]}
    gistda = [dict(row) for row in db.execute(text(_GISTDA_SQL), common).mappings()]
    public = [dict(row) for row in db.execute(text(_PUBLIC_SQL), common).mappings()]
    for item in gistda:
        if isinstance(item["representative_intersection"], str):
            item["representative_intersection"] = json.loads(item["representative_intersection"])
    for item in public:
        item["distance_to_route_meters"] = float(item["distance_to_route_meters"])

    status = db.execute(text("""
      SELECT
       (EXISTS (SELECT 1 FROM gistda_flood_features WHERE period=:period AND is_active IS TRUE)
        OR EXISTS (SELECT 1 FROM gistda_sync_runs WHERE period=:period AND status IN ('SUCCESS','PARTIAL'))) gistda_available,
       COALESCE(
         (SELECT max(COALESCE(source_updated_at, source_observed_at, synced_at))
            FROM gistda_flood_features WHERE period=:period AND is_active IS TRUE),
         (SELECT max(finished_at) FROM gistda_sync_runs
            WHERE period=:period AND status IN ('SUCCESS','PARTIAL'))
       ) gistda_latest,
       EXISTS (SELECT 1 FROM flood_reports WHERE source='PUBLIC' AND status='ACTIVE'
          AND verification_status=ANY(CAST(:eligible_statuses AS text[])) AND reported_at>=:reported_from) public_available,
       (SELECT max(reported_at) FROM flood_reports WHERE source='PUBLIC' AND status='ACTIVE'
          AND verification_status=ANY(CAST(:eligible_statuses AS text[])) AND reported_at>=:reported_from) public_latest
    """), common).mappings().one()
    ga, pa = bool(status["gistda_available"]), bool(status["public_available"])
    situation = classify_route_flood_impact(bool(gistda), bool(public), ga, pa)
    return {"route_id": route_id,
        "origin": {"type": route["origin_type"], "code": route["origin_code"]},
        "destination": {"type": route["destination_type"], "code": route["destination_code"]},
        "vehicle_profile": route["vehicle_profile"], "routing_provider": route["routing_provider"],
        "distance_km": float(route["distance_km"]), "duration_minutes": float(route["duration_minutes"]),
        "calculated_at": route["calculated_at"], "flood_situation": situation,
        "gistda_evidence": gistda, "public_report_evidence": public,
        "public_route_impact_radius_meters": radius_meters,
        "source_data_status": {"complete": ga and pa,
          "gistda": {"data_available": ga, "evaluated_period_or_window": period,
                     "latest_source_at": status["gistda_latest"]},
          "public": {"data_available": pa, "evaluated_period_or_window": f"{lookback_hours} hours",
                     "latest_source_at": status["public_latest"]}},
        "evaluated_at": datetime.now(timezone.utc)}
