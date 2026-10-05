"""Flood-aware, transient route calculation and post-route validation."""
import json
from dataclasses import replace
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.routing.provider import RoutingProvider
from app.schemas.transport import (LocationType, RouteSafetyState,
                                   SafeRouteCalculateRequest, SafeRouteRead)
from app.services.branches import get_branch_by_store_number
from app.services.distribution_centers import get_distribution_center
from app.services.routes import RouteLocationError, _normalize_result


_BLOCKERS = text("""
SELECT h.id, h.source_record_id, h.case_id, h.section_name, h.road_status
FROM hdms_incidents h
WHERE h.is_active IS TRUE AND h.geometry_available IS TRUE
 AND h.road_status='IMPASSABLE'
 AND ST_Intersects(h.road_geometry,
   ST_SetSRID(ST_GeomFromGeoJSON(:route),4326)) ORDER BY h.id
""")

# Locate crossings on a metric copy of each road, group crossings into 1 km
# windows, and buffer only the +/- 500 m road substring.  Besides avoiding an
# enormous polygon for a long HDMS road, grouping prevents coincident and
# nearby crossings from producing redundant exclusion polygons.  Every output
# is at most about 2 km long (a group can span its 1 km bucket plus the two
# 500 m margins), keeping its buffered perimeter comfortably below Valhalla's
# 10 km limit.  The final safety query above deliberately still uses the full
# authoritative road geometry.
_EXCLUSION_POLYGONS = text("""
WITH route AS (
  SELECT ST_SetSRID(ST_GeomFromGeoJSON(:route), 4326) AS geom
), roads AS (
  SELECT h.id, ST_Transform(ST_LineMerge(h.road_geometry), 3857) AS road
  FROM hdms_incidents h, route r
  WHERE h.is_active IS TRUE AND h.geometry_available IS TRUE
    AND h.road_status = 'IMPASSABLE'
    AND ST_Intersects(h.road_geometry, r.geom)
), crossings AS (
  SELECT roads.id, roads.road,
    ST_LineLocatePoint(roads.road, ST_Transform((dp).geom, 3857))
      * ST_Length(roads.road) AS measure_m
  FROM roads, route r
  CROSS JOIN LATERAL ST_DumpPoints(
    ST_Intersection(ST_Transform(r.geom, 3857), roads.road)
  ) AS dp
), crossing_groups AS (
  SELECT id, road, floor(measure_m / 1000.0) AS window,
    min(measure_m) AS first_m, max(measure_m) AS last_m
  FROM crossings
  GROUP BY id, road, floor(measure_m / 1000.0)
), local_segments AS (
  SELECT id, window, ST_LineSubstring(
    road,
    greatest(0.0, first_m - 500.0) / nullif(ST_Length(road), 0),
    least(ST_Length(road), last_m + 500.0) / nullif(ST_Length(road), 0)
  ) AS segment
  FROM crossing_groups
)
SELECT id, window,
  ST_AsGeoJSON(ST_Transform(ST_Buffer(segment, 20), 4326))::json AS polygon
FROM local_segments
WHERE segment IS NOT NULL AND NOT ST_IsEmpty(segment)
ORDER BY id, window
""")

_EVIDENCE = text("""
WITH route AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(:route),4326) geom)
SELECT 'GISTDA' source, f.id::text evidence_id, 'WARNING' severity
 FROM gistda_flood_features f, route r WHERE f.period=:period AND f.is_active IS TRUE AND ST_Intersects(f.geometry,r.geom)
UNION ALL SELECT 'HDMS',h.id::text,CASE WHEN h.road_status='IMPASSABLE' THEN 'BLOCKING' ELSE 'WARNING' END
 FROM hdms_incidents h, route r WHERE h.is_active IS TRUE AND h.geometry_available IS TRUE AND ST_Intersects(h.road_geometry,r.geom)
UNION ALL SELECT 'BMA',b.id::text,'WARNING' FROM bma_road_water_observations b, route r
 WHERE b.is_active IS TRUE AND ST_DWithin(b.location::geography,r.geom::geography,:bma_radius)
UNION ALL SELECT 'PUBLIC',p.id::text,'WARNING' FROM flood_reports p, route r
 WHERE p.source='PUBLIC' AND p.status='ACTIVE' AND ST_DWithin(p.flood_location,r.geom::geography,:public_radius)
""")

_AVAILABILITY = text("""
SELECT (EXISTS(SELECT 1 FROM hdms_incidents WHERE is_active IS TRUE)
 OR EXISTS(SELECT 1 FROM hdms_sync_runs WHERE status IN ('SUCCESS','PARTIAL'))) hdms,
 (EXISTS(SELECT 1 FROM gistda_flood_features WHERE period=:period AND is_active IS TRUE)
  OR EXISTS(SELECT 1 FROM gistda_sync_runs WHERE period=:period AND status IN ('SUCCESS','PARTIAL'))) gistda,
 (EXISTS(SELECT 1 FROM bma_road_water_observations WHERE is_active IS TRUE)
  OR EXISTS(SELECT 1 FROM bma_sync_runs WHERE status IN ('SUCCESS','PARTIAL'))) bma,
 EXISTS(SELECT 1 FROM flood_reports WHERE source='PUBLIC' AND status='ACTIVE') public
""")


def _points(geometry: dict, count: int = 3) -> list[list[float]]:
    coordinates = geometry["coordinates"]
    if len(coordinates) < 3:
        return []
    indexes = sorted({round((len(coordinates)-1)*i/(count+1)) for i in range(1, count+1)})
    return [coordinates[i] for i in indexes if 0 < i < len(coordinates)-1]


def _anchor(result, origin: tuple[float, float], destination: tuple[float, float]):
    geometry = {**result.route_geometry, "coordinates": [list(p) for p in result.route_geometry["coordinates"]]}
    if geometry["coordinates"][0] != list(origin):
        geometry["coordinates"].insert(0, list(origin))
    if geometry["coordinates"][-1] != list(destination):
        geometry["coordinates"].append(list(destination))
    return replace(result, route_geometry=geometry)


def _origin(db: Session, request: SafeRouteCalculateRequest):
    if request.origin.type == LocationType.CURRENT_LOCATION:
        if request.origin_coordinates is None:
            raise RouteLocationError("CURRENT_LOCATION_REQUIRED", "Current coordinates are required", 422)
        return tuple(request.origin_coordinates)
    if request.origin.type != LocationType.DC:
        raise RouteLocationError("UNSUPPORTED_ORIGIN", "Origin must be DC or CURRENT_LOCATION", 422)
    dc = get_distribution_center(db, request.origin.code)
    if dc is None or dc.status.upper() != "ACTIVE":
        raise RouteLocationError("DC_NOT_AVAILABLE", "Distribution center is not active", 404)
    return dc.longitude, dc.latitude


def calculate_safe_route(db: Session, request: SafeRouteCalculateRequest, provider: RoutingProvider,
                         period: str, public_radius: float, bma_radius: float) -> SafeRouteRead:
    if request.destination.type != LocationType.BRANCH:
        raise RouteLocationError("UNSUPPORTED_DESTINATION", "Destination must be BRANCH", 422)
    branch = get_branch_by_store_number(db, request.destination.code)
    if branch is None or branch.status.upper() != "ACTIVE":
        raise RouteLocationError("BRANCH_NOT_AVAILABLE", "Branch is not active", 404)
    origin = _origin(db, request)
    destination = (branch.longitude, branch.latitude)
    candidate = _anchor(_normalize_result(provider.calculate_route(
        origin, destination, request.vehicle_profile.value)), origin, destination)
    route_json = json.dumps(candidate.route_geometry)
    exclusions = [dict(row) for row in db.execute(
        _EXCLUSION_POLYGONS, {"route": route_json}
    ).mappings()]
    result, attempted = candidate, False
    if exclusions:
        # ST_Buffer(LineString) produces Polygon GeoJSON. PostGIS and Valhalla
        # both use GeoJSON's [longitude, latitude] coordinate order here.
        polygons = [row["polygon"]["coordinates"][0] for row in exclusions]
        attempted = True
        result = _anchor(_normalize_result(provider.calculate_route_avoiding(
            origin, destination, request.vehicle_profile.value, polygons)), origin, destination)
        route_json = json.dumps(result.route_geometry)
    # Mandatory second evaluation uses fresh queries, including after rerouting.
    final_blockers = [dict(row) for row in db.execute(_BLOCKERS, {"route": route_json}).mappings()]
    evidence_rows = [dict(row) for row in db.execute(_EVIDENCE, {"route": route_json,
        "period": period, "public_radius": public_radius, "bma_radius": bma_radius}).mappings()]
    availability = dict(db.execute(_AVAILABILITY, {"period": period}).mappings().one())
    warnings = [row for row in evidence_rows if row["severity"] == "WARNING"]
    if final_blockers:
        state = RouteSafetyState.BLOCKED
    elif not all(availability.values()):
        state = RouteSafetyState.UNVERIFIED
    elif warnings:
        state = RouteSafetyState.WARNING
    else:
        state = RouteSafetyState.SAFE
    return SafeRouteRead(origin_type=request.origin.type, origin_code=request.origin.code,
        destination_type=request.destination.type, destination_code=request.destination.code,
        vehicle_profile=request.vehicle_profile, distance_km=result.distance_km,
        duration_minutes=result.duration_minutes, route_geometry=result.route_geometry,
        routing_provider=result.provider_name, calculated_at=datetime.now(timezone.utc),
        safety_state=state, avoidance_attempted=attempted, blocking_hazards=final_blockers,
        warning_hazards=warnings, evidence={source:[r for r in evidence_rows if r["source"] == source]
          for source in ("HDMS","GISTDA","BMA","PUBLIC")},
        navigation_waypoints=_points(result.route_geometry))
