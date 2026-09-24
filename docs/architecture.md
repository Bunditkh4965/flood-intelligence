# Current architecture

## Scope boundary

The current system is a branch-location foundation only. It does not accept flood reports, determine flood impacts, apply risk rules, calculate road routes, or integrate with ChatGPT. Future Flood Report, Flood Incident, and Flood Impact modules can be added as separate models, services, and API routers without coupling them to the branch API.

## Components

```text
Client
  │ HTTP
  ▼
FastAPI (`backend/app/main.py`)
  ├─ health router
  └─ branch router → branch service → SQLAlchemy 2 → PostgreSQL/PostGIS
                                               └─ Alembic migrations
```

Configuration is read from environment variables through `app.core.Settings`. Database sessions are injected per request and are closed after the request completes.

## Data model and spatial design

`branches.location` is a PostGIS `geography(POINT, 4326)` column. Latitude and longitude are retained as scalar columns for transparent API responses and operational data import. The migration creates:

- a unique B-tree index on `store_number` for direct branch lookup;
- a GiST index on `location` for spatial filtering.

The nearby service creates a WGS84 query point and uses `ST_DWithin` with a runtime `radius_km` argument. PostGIS geography functions use meters, so the service converts kilometers to meters. `ST_Distance` supplies the returned straight-line distance. No business impact radius is stored or inferred.

## Extensibility

New domains should follow the same layers: a SQLAlchemy model, Pydantic contracts, a service for business/data access logic, and a focused API router. Routing providers and future AI integrations should depend on explicit service interfaces rather than embedding their logic in endpoint handlers.
