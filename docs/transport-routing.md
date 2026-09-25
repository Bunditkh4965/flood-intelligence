# Transport routing (Sprint 5B)

## Architecture and provider boundary

`POST /api/v1/routes/calculate` resolves an active distribution centre and
branch, calls the configured `RoutingProvider`, normalizes its result, and only
then inserts a `transport_routes` row. Provider failures therefore never create
a route record. Missing, disabled, unknown, or incomplete provider configuration
preserves the explicit `ROUTING_PROVIDER_NOT_CONFIGURED` response; there is no
straight-line fallback.

The Valhalla adapter calls the separately operated service's `/route` endpoint
over HTTP with an explicit timeout. It asks for kilometres and polyline6, decodes
the returned shape, changes Valhalla's latitude/longitude values into GeoJSON's
longitude/latitude order, and persists a non-empty
`geometry(LineString, 4326)` with at least two points. The API returns this
LineString, normalized kilometres/minutes, `VALHALLA` provenance, and calculation
time, but not Valhalla's full response.

The application profiles `4W`, `6W`, and `10W` currently all map to Valhalla
`auto` costing. This is intentional: Flood Intelligence has no authoritative
vehicle height, weight, axle, width, hazardous-cargo, company restriction, or
truck-ban data. The adapter keeps that mapping at its provider boundary so a
later sprint can add truck-specific costing without changing route persistence.

## Configuration

```dotenv
ROUTING_PROVIDER=valhalla
VALHALLA_URL=http://localhost:8002
VALHALLA_TIMEOUT_SECONDS=10
```

Use `http://localhost:8002` when the API runs on the host. For Flood Intelligence
running in Docker Desktop, set `VALHALLA_URL=http://host.docker.internal:8002`.
On a future shared server, use that environment's internal Valhalla URL. Shared
Valhalla remains independent: this repository does not run a Valhalla container,
mount its volume, read tiles, or duplicate Thailand tiles.

The endpoint accepts `id` (and the backwards-compatible `code` spelling) for
location identifiers:

```json
{
  "origin": {"type": "DC", "id": "TEST-DC-01"},
  "destination": {"type": "BRANCH", "id": "10241"},
  "vehicle_profile": "6W"
}
```

## Local live acceptance (PowerShell)

These commands assume Shared Valhalla is already running, the branch `10241`
exists and is active, and Docker Desktop is available. They intentionally keep
Valhalla outside this project's Compose stack.

```powershell
# From the flood-intelligence repository. Configure Docker-to-host access.
Copy-Item .env.example .env
$env:POSTGRES_PASSWORD = "change-me"
$env:ROUTING_PROVIDER = "valhalla"
$env:VALHALLA_URL = "http://host.docker.internal:8002"
$env:VALHALLA_TIMEOUT_SECONDS = "10"

# 1. Prove the independent service is healthy from the host.
Invoke-RestMethod http://localhost:8002/status

# Start Flood Intelligence only (no Valhalla service is defined here).
docker compose up -d --build db api

# 2. Prove the API container can reach the shared service.
docker compose exec api python -c "import httpx; r=httpx.get('http://host.docker.internal:8002/status', timeout=10); r.raise_for_status(); print(r.json())"

# Create an acceptance DC (409 means it already exists and is safe to continue).
$dc = @{dc_code='TEST-DC-01';dc_name='Acceptance DC';latitude=13.7563;longitude=100.5018;status='ACTIVE'} | ConvertTo-Json
try { Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/distribution-centers -ContentType application/json -Body $dc } catch { if ($_.Exception.Response.StatusCode.value__ -ne 409) { throw } }

# Baseline row count, then 3-6. Calculate and verify normalized result fields.
$before = docker compose exec -T db psql -U flood -d flood_intelligence -Atc "SELECT count(*) FROM transport_routes;"
$body = @{origin=@{type='DC';id='TEST-DC-01'};destination=@{type='BRANCH';id='10241'};vehicle_profile='6W'} | ConvertTo-Json -Depth 4
$route = Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/routes/calculate -ContentType application/json -Body $body
$route | ConvertTo-Json -Depth 8
if ($route.distance_km -le 0 -or $route.duration_minutes -le 0 -or $route.routing_provider -ne 'VALHALLA') { throw 'Invalid routed result' }

# 7-9. Prove persistence, type/SRID, and a road shape with more than two points.
docker compose exec -T db psql -U flood -d flood_intelligence -c "SELECT route_id, distance_km, duration_minutes, routing_provider, GeometryType(route_geometry) AS geometry_type, ST_SRID(route_geometry) AS srid, ST_NPoints(route_geometry) AS points FROM transport_routes WHERE route_id = '$($route.route_id)';"

# 10. Stop Valhalla externally (using its own project), then run this request.
# It must return 502/504. The count printed afterward must still equal $beforeFailed.
$beforeFailed = docker compose exec -T db psql -U flood -d flood_intelligence -Atc "SELECT count(*) FROM transport_routes;"
try { Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/routes/calculate -ContentType application/json -Body $body; throw 'Expected routing failure' } catch { $_.Exception.Message }
$afterFailed = docker compose exec -T db psql -U flood -d flood_intelligence -Atc "SELECT count(*) FROM transport_routes;"
if ($afterFailed -ne $beforeFailed) { throw 'Routing failure persisted a row' }

# 11. Restart Shared Valhalla externally, then run the complete automated suite.
docker compose exec api pytest -q
```

For a host-run API, set `$env:VALHALLA_URL='http://localhost:8002'`, set a host
`DATABASE_URL`, and start Uvicorn from `backend` instead of using Compose.

## Deferred scope

This sprint does not implement flood intersections, public-point distance,
impact classification, rerouting, risk scoring, closure inference, or route and
multi-stop optimization.
