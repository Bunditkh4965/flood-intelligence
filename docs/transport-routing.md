# Transport route foundation (Sprint 5A)

## Distribution Center master

`distribution_centers` stores a unique business `dc_code`, name, scalar WGS84
coordinates, an indexed PostGIS geography point, lifecycle status, and audit
timestamps. Values are maintained through the internal-style list, detail, and
create endpoints under `/api/v1/distribution-centers`. No real or placeholder
company DC records are seeded.

## Route domain and persistence

`transport_routes` records the origin and destination type/code, normalized
vehicle profile, distance, duration, provider provenance, calculation time, and
the provider's SRID 4326 LineString or MultiLineString. Its GiST index supports
future spatial operations and its composite lookup index allows a later cache
policy to reuse a DC/branch/profile result. Sprint 5A records each successful
calculation; it deliberately does not introduce cache expiry or invalidation.

**A route geometry represents a road-network route returned by a routing
provider. Straight-line geometry must never be treated as a delivery route.**
In particular, the application never uses `ST_MakeLine` as a route fallback.

## Provider boundary

`RoutingProvider.calculate_route(origin, destination, vehicle_profile)` accepts
longitude/latitude pairs and returns normalized distance in kilometres,
duration in minutes, GeoJSON linear geometry, provider name, and an optional
provider route identifier. No external provider or provider preference is
configured. The safe default raises an explicit error, surfaced by
`POST /api/v1/routes/calculate` as HTTP 503 with code
`ROUTING_PROVIDER_NOT_CONFIGURED`; it creates no route record or geometry.

The API currently supports the explicit profiles `4W`, `6W`, and `10W`.
Profiles are passed through to the provider without inferring dimensions,
weights, legal restrictions, or road eligibility from `Branch.vehicle_type`.

Route calculation currently supports typed locations, validates that both
records exist and are active, and persists only a successful provider result.
Its geometry is intentionally suitable for later `ST_Intersects` with GISTDA
polygons and `ST_DWithin` against public report geography points.

## Explicit Sprint 5A boundary

Sprint 5A does **not** calculate flood impact on routes. It does not intersect
GISTDA areas, evaluate public-report proximity, classify or score risk, infer
closures or truck bans, reroute around floods, send alerts, or add UI/AI
features.
