# Flood Intelligence Platform

A production-oriented backend foundation for maintaining branch locations and finding branches near a supplied location. This Sprint 1 implementation intentionally excludes flood reporting, impact/risk rules, a frontend, routing, and ChatGPT integration.

## Architecture

- **FastAPI** exposes versioned HTTP APIs and the health endpoint.
- **SQLAlchemy 2** models persistence; **GeoAlchemy2/PostGIS** stores branch locations as WGS84 (`SRID 4326`) geography points.
- **PostgreSQL + PostGIS** executes spatial radius searches using `ST_DWithin` and calculates straight-line distances using `ST_Distance`.
- **Alembic** owns schema evolution. The initial migration enables PostGIS and creates spatial and store-number indexes.

See [docs/architecture.md](docs/architecture.md) for more detail.

## Prerequisites

- Docker Engine with Docker Compose v2 (recommended), or Python 3.12+ and PostgreSQL with PostGIS.
- For local Python development: `pip` and a PostgreSQL/PostGIS database.

## Docker setup

1. Create local configuration: `cp .env.example .env`.
2. Set a strong unique `POSTGRES_PASSWORD` in `.env`.
3. Start the stack: `docker compose up --build`.
4. Visit `http://localhost:8000/health`.

The API service applies pending migrations before starting. Stop services with `docker compose down`; add `-v` only when intentionally discarding local database data.

## Database and migrations

When using Docker, migration commands run inside the API container:

```bash
docker compose exec api alembic -c /database/alembic.ini upgrade head
docker compose exec api alembic -c /database/alembic.ini revision --autogenerate -m "describe change"
```

For a local backend process, set `DATABASE_URL`, then run from `backend/`:

```bash
export DATABASE_URL='postgresql+psycopg://USER:PASSWORD@localhost:5432/flood_intelligence'
alembic -c ../database/alembic.ini upgrade head
```

## Run the API locally

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL='postgresql+psycopg://USER:PASSWORD@localhost:5432/flood_intelligence'
uvicorn app.main:app --reload
```

## Run tests

```bash
cd backend
pytest
```

The unit test suite does not require a running database. Spatial behavior is implemented in PostGIS and should be exercised against the Docker database in deployment/integration pipelines.

## Branch master import

The committed `Stores Master Sep2026.xlsx` source is imported without modifying
the workbook. Validate it first (this validates every row and produces a JSON
report):

```bash
cd backend
python scripts/import_branches.py ../'Stores Master Sep2026.xlsx' --validate-only
```

To import into PostgreSQL/PostGIS after migrations are applied, omit
`--validate-only`. The importer rejects the entire persistence operation when
the source has validation errors, detects duplicate store numbers, upserts by
`StoreNumber`, and writes locations with `POINT(longitude latitude)`.

### Reproducible PostGIS integration environment

The existing Compose stack supplies PostgreSQL with PostGIS and mounts the
committed workbook read-only at `/data/Stores Master Sep2026.xlsx` in the API
container. The API startup command runs Alembic migrations before it starts.

```bash
docker compose -p flood-intelligence-sprint2-test --env-file .env.sprint2test.example up --build -d db api
docker compose -p flood-intelligence-sprint2-test --env-file .env.sprint2test.example exec api alembic -c /database/alembic.ini upgrade head
docker compose -p flood-intelligence-sprint2-test --env-file .env.sprint2test.example exec api python scripts/import_branches.py /data/'Stores Master Sep2026.xlsx'
docker compose -p flood-intelligence-sprint2-test --env-file .env.sprint2test.example exec api pytest -m integration -q tests/test_branch_importer_integration.py
```

The integration test runs the existing Alembic migrations, clears the `branches` table, imports the actual workbook,
then verifies the expected row count, unique store numbers, scalar coordinates,
non-null geography points, longitude/latitude point ordering, and a spatial
nearby query. It requires `DATABASE_URL` and a migrated PostGIS database.

## API examples

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/branches
curl http://localhost:8000/api/v1/branches/1001
curl 'http://localhost:8000/api/v1/branches/nearby?lat=30.2672&lng=-97.7431&radius_km=10'
```

`/api/v1/branches/nearby` returns only branches inside the caller-provided radius, ordered by straight-line distance. Coordinates are validated to latitude `[-90, 90]` and longitude `[-180, 180]`.

## Public flood reporting (Sprint 3A)

`POST /api/v1/flood-reports` accepts an unauthenticated public report. The future client must supply the **flood** coordinates from its map selection and, when permission/device support is available, **reporter** coordinates from browser/device GPS. These are separate fields; no reverse geocoding or manual coordinate entry is implemented. GPS accuracy is accepted in metres when the device supplies it.

Photo evidence is currently represented by `has_photo`; `flood_report_photos` is reserved for external-object-storage metadata and never stores image bytes in PostgreSQL. Public submissions always receive `source: "PUBLIC"`; clients cannot submit another source or internal status.

The `REPORTER_GPS_VERIFY_RADIUS_M` row in `system_configurations` controls the radius and is seeded at **300 metres** (an environment default is available as a fallback). PostGIS calculates and persists the reporter-to-flood geography distance in metres. The rules are:

| Situation | Status | Reason |
| --- | --- | --- |
| GPS + photo + distance within radius | `VERIFIED` | `GPS_WITHIN_RADIUS_AND_PHOTO` |
| GPS + photo + distance outside radius | `PENDING_REVIEW` | `GPS_OUTSIDE_RADIUS_WITH_PHOTO` |
| GPS + no photo | `PENDING_REVIEW` | `GPS_WITHOUT_PHOTO` |
| No GPS + photo | `PENDING_REVIEW` | `NO_REPORTER_GPS_WITH_PHOTO` |
| No GPS + no photo | `UNVERIFIED` | `NO_REPORTER_GPS_NO_PHOTO` |

**`VERIFIED` means only that location evidence met this system rule. It does not mean the flood event has been independently or scientifically confirmed.**

Endpoints: `POST /api/v1/flood-reports`, `GET /api/v1/flood-reports`, and `GET /api/v1/flood-reports/{report_code}`. The list endpoint supports `status`, `verification_status`, `reported_from`, `reported_to`, and optional `min_latitude`, `max_latitude`, `min_longitude`, and `max_longitude` bounding-box filters.

```bash
curl -X POST http://localhost:8000/api/v1/flood-reports \
  -H 'content-type: application/json' \
  -d '{"flood_latitude":14.123456,"flood_longitude":100.567890,"reporter_latitude":14.124,"reporter_longitude":100.5681,"reporter_gps_accuracy_m":12.5,"water_level_cm":35,"road_status":"PARTIAL","has_photo":true}'
```

A response includes a collision-safe daily code such as `FR-20260924-00001`, the two location objects, distance, evidence state, verification outcome/reason, public source, and report status. Do not treat a response as reporter identity information.
