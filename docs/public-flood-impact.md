# Public flood report branch proximity API

Sprint 4B provides a source-specific proximity view between branches and recent,
active public flood observations. It is separate from, and does not modify or
combine results with, the GISTDA polygon impact engine.

## Meaning and limitations

`PUBLIC_NEARBY` means **there is a qualifying public flood observation within
the requested distance**. `PUBLIC_NONE` means there is no qualifying observation
inside that radius. A report is a point observation, not a flood-area polygon,
so there is deliberately no public `DIRECT` classification.

`PUBLIC_NEARBY` does **not** mean that the branch is flooded, a road is flooded,
or a delivery route is blocked. This API makes no risk, road, or route inference.

Qualifying reports have `source=PUBLIC`, `status=ACTIVE`, fall within the
requested time window, and have an accepted verification status. The default
accepted statuses are `VERIFIED` and `PENDING_REVIEW`; `UNVERIFIED` is excluded.
Operators may change the allow-list through the
`PUBLIC_IMPACT_VERIFICATION_STATUSES` system configuration.

## Requests

```http
GET /api/v1/public-flood-impact/branches?proximity_km=5&lookback_hours=24&limit=100&offset=0
GET /api/v1/public-flood-impact/branches?proximity_km=5&lookback_hours=24&classification=PUBLIC_NEARBY
GET /api/v1/public-flood-impact/branches/2044?proximity_km=5&lookback_hours=24
```

`proximity_km` is required, greater than zero, and at most 100 km.
`lookback_hours` defaults to 24 and must be from 1 through 168 hours. The list
classification is optionally `PUBLIC_NEARBY` or `PUBLIC_NONE`. Its summary is
calculated before filtering and pagination. `data_available=false` means there
were no qualifying public reports in the time window; in that case nearest
report fields are null and all branches classify as `PUBLIC_NONE`.

## Spatial implementation

PostGIS compares `branches.location` with the explicitly selected
`flood_reports.flood_location`; reporter GPS is never used. A lateral K-nearest
neighbor query selects one eligible report per branch using the geography GiST
index. `ST_Distance` on geography returns geodesic metres, converted to
kilometres. A partial eligibility/time index reduces the reports scanned before
the spatial nearest-neighbor operation.
