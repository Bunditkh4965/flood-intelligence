# Unified Branch Flood Situation

Unified Branch Flood Situation is a factual aggregation of source observations.
It is not a risk score and does not confirm road or route impact.

The API preserves two independent observations: GISTDA is official external
polygon data, while PUBLIC is a crowdsourced point report. Their geometries are
not merged, and `PUBLIC_NEARBY` is never interpreted as GISTDA `DIRECT`.

## Endpoints and parameters

* `GET /api/v1/branch-flood-situation` returns active branches, unfiltered
  summary counts, and a paginated `items` list.
* `GET /api/v1/branch-flood-situation/{store_number}` returns one active branch
  or `404`.
* `period` selects `1DAY`, `3DAYS` (default), `7DAYS`, or `30DAYS` GISTDA data.
* `gistda_proximity_km` (required, `> 0` and `<= 500`) sets polygon proximity.
* `public_proximity_km` (required, `> 0` and `<= 100`) sets report proximity.
* `public_lookback_hours` (default 24, `1..168`) limits eligible reports by age.
* `situation` optionally filters items; it does not change summary counts.
* `limit` (`1..1000`, default 100) and `offset` (default 0) paginate after the
  situation filter.

## Combined categories and priority

Categories are evaluated in this order:

1. `GISTDA_DIRECT`: the branch point intersects an active GISTDA polygon.
2. `MULTI_SOURCE_NEARBY`: both GISTDA and PUBLIC are nearby.
3. `GISTDA_NEARBY`: only GISTDA is nearby.
4. `PUBLIC_NEARBY`: only an eligible public report is nearby.
5. `NO_NEARBY_FLOOD`: both sources have data and neither is direct/nearby.
6. `SOURCE_DATA_INCOMPLETE`: one or both sources have no selected-period data.

No-data takes precedence over nearby/none combinations because the absent
source cannot be characterized. The sole exception is an established
`GISTDA_DIRECT`, which is retained even if PUBLIC has no eligible report.
Source objects still expose `data_available` so clients can display the facts.
An unavailable source has a `null` classification rather than an invented
`NONE` state.

## Limitations

Distances are straight-line PostGIS geography distances. A nearby observation
does not establish branch flooding, severity, road closure, accessibility,
delivery impact, or route impact. The endpoint performs no routing, prediction,
numeric scoring, alerting, or source-geometry fusion.
