# Unified Branch Flood Situation

Unified Branch Flood Situation is a factual aggregation of source observations.
It is not a risk score and does not confirm road or route impact.

The API preserves independent GISTDA, HDMS, BMA, and Public observations. Their
geometries are not merged; source-specific evidence retains its own meaning.

## Endpoints and parameters

* `GET /api/v1/branch-flood-situation` returns active branches, unfiltered
  summary counts, and a paginated `items` list.
* `GET /api/v1/branch-flood-situation/{store_number}` returns one active branch
  or `404`.
* `period` selects `1DAY`, `3DAYS` (default), `7DAYS`, or `30DAYS` GISTDA data.
* `gistda_proximity_km` (required, `> 0` and `<= 500`) sets polygon proximity.
* `public_proximity_km` (required, `> 0` and `<= 100`) sets report proximity.
* `hdms_proximity_km` and `bma_proximity_km` (default 5, `> 0` and `<= 100`)
  set their respective geometry proximity thresholds.
* `public_lookback_hours` (default 24, `1..168`) limits eligible reports by age.
* `situation` optionally filters items; it does not change summary counts.
* `limit` (`1..1000`, default 100) and `offset` (default 0) paginate after the
  situation filter.

## Combined categories and priority

Evidence from more than one available source produces `MULTI_SOURCE_NEARBY`.
Single-source evidence then uses this precedence:

1. `GISTDA_DIRECT`: the branch point intersects an active GISTDA polygon.
2. `GISTDA_NEARBY`: GISTDA geometry is nearby.
3. `HDMS_NEARBY`: an active HDMS road incident is nearby.
4. `BMA_NEARBY`: an active BMA observation is nearby.
5. `PUBLIC_NEARBY`: an eligible public report is nearby.
6. `NO_NEARBY_FLOOD`: all four sources are available and none has evidence.
7. `SOURCE_DATA_INCOMPLETE`: at least one source cannot be assessed and no
   detected-evidence category takes precedence.

Availability is independent from evidence presence. GISTDA, HDMS, and BMA are
available when retained active data exists or a `SUCCESS`/`PARTIAL` sync run
exists; this means a successful empty sync is available. Public reports are a
database-native source with no sync-run model, so successful execution of the
assessment query makes Public available even when the lookback is empty.
Unavailable source classifications are `null` rather than invented `NONE`
states.

## Limitations

Distances are straight-line PostGIS geography distances. A nearby observation
does not establish branch flooding, severity, road closure, accessibility,
delivery impact, or route impact. The endpoint performs no routing, prediction,
numeric scoring, alerting, or source-geometry fusion.

The existing sync metadata has no authoritative freshness or expiry threshold.
Consequently, the assessment can distinguish never-successfully-synced/failed
sources from successful empty sources, but cannot label an old successful sync
as stale without inventing a new policy.
