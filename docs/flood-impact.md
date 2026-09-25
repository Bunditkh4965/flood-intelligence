# GISTDA branch flood impact API

Sprint 4A compares branch points with the **active** GISTDA polygons for one
requested period. It does not perform road or route analysis.

## Classifications

- **DIRECT**: the branch point intersects a flood polygon. Its distance is `0`.
- **NEARBY**: the point does not intersect a polygon, but the geodesic distance
  to the nearest active polygon is at most `proximity_km`.
- **NONE**: there is no intersection and the nearest polygon is farther than
  `proximity_km`.

`proximity_km` is a caller-selected monitoring radius greater than zero and no
more than 500 km. **NEARBY does not confirm that the branch or its delivery
route is flooded or blocked.** It only describes straight-line proximity.

The response's `data_available` field distinguishes a period with no active
GISTDA features (`false`) from available data in which a branch is not nearby
(`true` with classification `NONE`). When data is unavailable, branches remain
`NONE`, their nearest feature and distance are `null`, and no flood condition is
invented.

## Requests

```http
GET /api/v1/flood-impact/branches?period=3DAYS&proximity_km=10&limit=100&offset=0
GET /api/v1/flood-impact/branches?period=3DAYS&proximity_km=10&classification=NEARBY
GET /api/v1/flood-impact/branches/2044?period=3DAYS&proximity_km=10
```

The collection summary always covers all branches and all three classifications,
before the optional classification filter and pagination are applied. Each
branch occurs at most once and identifies its nearest active feature.

## Spatial implementation

PostGIS performs all intersection and distance work. A lateral nearest-neighbor
query returns one polygon per branch; the geography KNN operator uses the GiST
expression index, and `ST_Distance` on geography returns metres (converted to
kilometres). Geometry values are not loaded into Python. The period/active index
limits eligible source rows, and the existing branch store-number index supports
the single-branch endpoint.
