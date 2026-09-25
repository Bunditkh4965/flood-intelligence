# Route Flood Impact Detection (Sprint 5C)

## Architecture and semantics

`GET /api/v1/routes/{route_id}/flood-impact` evaluates current source data at
request time. It reads the already persisted Valhalla `route_geometry`; it does
not copy geometry or persist an impact snapshot. Consequently `calculated_at`
is the route calculation time, while `evaluated_at` is the flood evaluation
time. Evidence carries its own source/sync timestamps.

This differs deliberately from branch impact. Branch classification compares a
branch point with flood evidence and can say a branch is nearby. Route impact
uses every vertex of the actual road-network LineString. A nearby origin,
destination, or branch does not make a route `GISTDA_DIRECT`, and no
origin-to-destination straight line is constructed.

For active GISTDA features in `ROUTE_IMPACT_GISTDA_PERIOD` the exact predicate is:

```sql
ST_Intersects(gistda_flood_feature.geometry, transport_route.route_geometry)
```

Each match returns feature identity, period/source timestamps, `intersects:
true`, and a representative point from the actual intersection. Both geometry
columns have SRID 4326 and the polygon's existing GiST index can support the
predicate.

Eligible active `PUBLIC` observations within the configured lookback use:

```sql
ST_DWithin(
  flood_report.flood_location,
  transport_route.route_geometry::geography,
  PUBLIC_ROUTE_IMPACT_RADIUS_METERS
)
```

This inclusive predicate and `ST_Distance` operate in metres, not WGS84 degrees.
Keeping the indexed report geography first allows use of its GiST index. The
eligible verification allow-list is the existing
`PUBLIC_IMPACT_VERIFICATION_STATUSES` system configuration, defaulting to
`VERIFIED,PENDING_REVIEW`; `UNVERIFIED` is not silently included. Evidence
contains report identity/status, distance, reported water level, factual road
and selected vehicle observation, and reported time.

## Configuration

| Environment variable | Default | Meaning |
|---|---:|---|
| `PUBLIC_ROUTE_IMPACT_RADIUS_METERS` | `300` | Inclusive public-point distance from the route, in metres |
| `ROUTE_IMPACT_PUBLIC_LOOKBACK_HOURS` | `24` | Age window for public reports |
| `ROUTE_IMPACT_GISTDA_PERIOD` | `3DAYS` | Active GISTDA dataset period |

## Factual classifications

Priority is `MULTI_SOURCE_ROUTE_IMPACT` (both evidence types), `GISTDA_DIRECT`
(polygon intersection), `PUBLIC_NEARBY_ROUTE` (eligible point within radius),
`SOURCE_DATA_INCOMPLETE` (no match and at least one required source unavailable),
then `NO_DETECTED_ROUTE_IMPACT`. Existing positive evidence remains factual even
if the other source is unavailable. Source status and timestamps remain visible
in every response.

These categories mean only that evidence was or was not detected against the
route. They do **not** establish that a road is closed, passable, safe, unsafe,
or that a truck can pass. Reported road/vehicle status is returned as source
evidence, never promoted into a closure inference. This sprint performs no
rerouting, avoidance, alternate generation, optimization, risk/severity score,
depth prediction, travel penalty, or operational decision.

## Exact Docker/PostGIS live acceptance (PowerShell)

Run from the repository with the existing shared Valhalla service and existing
flood data. No flood record is fabricated. `NO_DETECTED_ROUTE_IMPACT` is valid.

```powershell
Copy-Item .env.example .env -Force
$env:POSTGRES_PASSWORD = "change-me"
$env:ROUTING_PROVIDER = "valhalla"
$env:VALHALLA_URL = "http://host.docker.internal:8002"
$env:PUBLIC_ROUTE_IMPACT_RADIUS_METERS = "300"
$env:ROUTE_IMPACT_PUBLIC_LOOKBACK_HOURS = "24"
$env:ROUTE_IMPACT_GISTDA_PERIOD = "3DAYS"
docker compose up -d --build db api
docker compose exec api alembic -c /database/alembic.ini upgrade head

# 1. Select an existing persisted Valhalla route; fail rather than fabricate one.
$routeId = (docker compose exec -T db psql -U flood -d flood_intelligence -Atc "SELECT route_id FROM transport_routes WHERE routing_provider='VALHALLA' ORDER BY calculated_at DESC LIMIT 1;").Trim()
if (-not $routeId) { throw "No existing VALHALLA route" }

# 2 and 7. Prove the stored object is the detailed road LineString (not a two-point chord).
docker compose exec -T db psql -U flood -d flood_intelligence -c "SELECT route_id,routing_provider,GeometryType(route_geometry),ST_SRID(route_geometry),ST_NPoints(route_geometry),calculated_at FROM transport_routes WHERE route_id='$routeId';"

# 3. Independently execute the same indexed polygon/real-route intersection.
docker compose exec -T db psql -U flood -d flood_intelligence -c "SELECT f.id,f.external_feature_id,f.period,ST_Intersects(f.geometry,r.route_geometry) AS intersects FROM transport_routes r JOIN gistda_flood_features f ON f.period='3DAYS' AND f.is_active IS TRUE AND ST_Intersects(f.geometry,r.route_geometry) WHERE r.route_id='$routeId';"

# 4. Independently prove geography ST_DWithin/ST_Distance use metres and the configured eligibility rule.
docker compose exec -T db psql -U flood -d flood_intelligence -c "SELECT p.report_code,p.verification_status,ST_Distance(p.flood_location,r.route_geometry::geography) AS distance_m FROM transport_routes r JOIN flood_reports p ON p.source='PUBLIC' AND p.status='ACTIVE' AND p.verification_status IN ('VERIFIED','PENDING_REVIEW') AND p.reported_at >= now()-interval '24 hours' AND ST_DWithin(p.flood_location,r.route_geometry::geography,300) WHERE r.route_id='$routeId' ORDER BY distance_m;"

# 5, 6, and 8. Inspect factual category, evidence arrays, and source status. The API has no closure decision field.
$impact = Invoke-RestMethod "http://localhost:8000/api/v1/routes/$routeId/flood-impact"
$impact | ConvertTo-Json -Depth 12
if ($impact.flood_situation -notin @('MULTI_SOURCE_ROUTE_IMPACT','GISTDA_DIRECT','PUBLIC_NEARBY_ROUTE','NO_DETECTED_ROUTE_IMPACT','SOURCE_DATA_INCOMPLETE')) { throw 'Unexpected classification' }
if ($null -eq $impact.gistda_evidence -or $null -eq $impact.public_report_evidence) { throw 'Evidence arrays missing' }
if ($impact.PSObject.Properties.Name -contains 'road_closed') { throw 'Closure inference must not be returned' }

# Query plans should show spatial index candidates on live data.
docker compose exec -T db psql -U flood -d flood_intelligence -c "EXPLAIN SELECT f.id FROM transport_routes r JOIN gistda_flood_features f ON ST_Intersects(f.geometry,r.route_geometry) WHERE r.route_id='$routeId' AND f.period='3DAYS' AND f.is_active IS TRUE;"
docker compose exec -T db psql -U flood -d flood_intelligence -c "EXPLAIN SELECT p.id FROM transport_routes r JOIN flood_reports p ON ST_DWithin(p.flood_location,r.route_geometry::geography,300) WHERE r.route_id='$routeId';"

# 9. Existing branch flood endpoints remain available.
Invoke-RestMethod "http://localhost:8000/api/v1/branch-flood-situation?gistda_proximity_km=10&public_proximity_km=5&limit=1"

# 10. Full suite plus dedicated live spatial suite.
docker compose exec api pytest -q
docker compose exec api pytest -q -m integration tests/test_route_flood_impact_integration.py
```
