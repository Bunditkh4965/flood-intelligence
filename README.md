# Flood Intelligence Platform

A production-oriented backend foundation for maintaining branch locations and finding branches near a supplied location. This Sprint 1 implementation intentionally excludes flood reporting, impact/risk rules, a frontend, routing, and ChatGPT integration.

## Architecture

- **FastAPI** exposes versioned HTTP APIs and the health endpoint.
- **SQLAlchemy 2** models persistence; **GeoAlchemy2/PostGIS** stores branch locations as WGS84 (`SRID 4326`) geography points.
- **PostgreSQL + PostGIS** executes spatial radius searches using `ST_DWithin` and calculates straight-line distances using `ST_Distance`.
- **Alembic** owns schema evolution. The initial migration enables PostGIS and creates spatial and store-number indexes.

See [docs/architecture.md](docs/architecture.md) for more detail.

The Sprint 5A distribution-center master, provider-neutral route contract, safe
unconfigured-provider behavior, and strict road-route geometry semantics are
documented in [docs/transport-routing.md](docs/transport-routing.md). Sprint 5A
does not yet calculate flood impact on transport routes.

The isolated local Valhalla/Thailand infrastructure proof of concept is
documented in [docs/valhalla-thailand-poc.md](docs/valhalla-thailand-poc.md).
It does not change or configure the Sprint 5A routing provider.

The source-separated unified branch view is documented in
[docs/branch-flood-situation.md](docs/branch-flood-situation.md).

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

The legacy JSON `has_photo` field is accepted for Sprint 3A request compatibility but is not trusted. Sprint 3C derives evidence only from a successfully stored upload; `flood_report_photos` stores external-storage metadata and never image bytes. Public submissions always receive `source: "PUBLIC"`; clients cannot submit another source or internal status.

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
  -d '{"flood_latitude":14.123456,"flood_longitude":100.567890,"reporter_latitude":14.124,"reporter_longitude":100.5681,"reporter_gps_accuracy_m":12.5,"water_level_cm":35,"road_status":"PARTIAL"}'
```

A response includes a collision-safe daily code such as `FR-20260924-00001`, the selected flood location, evidence state, verification outcome/reason, public source, and report status. Reporter GPS and the verification distance are deliberately omitted.

## Official GISTDA flood areas (Sprint 3B)

GISTDA integration imports the official external geospatial flood-area datasets for `1day`, `3days`, `7days`, and `30days`. It uses the documented Feature/JSON endpoints under `/features/flood/{period}` rather than scraping pages or treating map tiles as analytical data. The current official OpenAPI security definition supplies the credential in the **`API-Key` HTTP header** (it is not a bearer token or query parameter). The client sends that header only to the configured base URL and deliberately excludes request headers and upstream response bodies from errors and logs.

Configure the runtime outside source control:

```dotenv
GISTDA_API_KEY=<provided securely by GISTDA>
GISTDA_API_BASE_URL=https://api-gateway.gistda.or.th/api/2.0/resources
```

`.env` is ignored by Git; `.env.example` contains blank, non-secret placeholders. Never put a real key in a command committed to the repository. Connection and read timeouts default to 5 and 30 seconds respectively, and requests do not retry indefinitely.

Run an administrator-controlled synchronization from `backend/` (there is intentionally no HTTP trigger endpoint):

```bash
python -m app.scripts.sync_gistda_flood --period 1day
python -m app.scripts.sync_gistda_flood --period all
```

Each response must be a WGS84 GeoJSON `FeatureCollection` (GeoJSON uses longitude, latitude coordinate order). Polygon values are normalized to MultiPolygon without changing coordinate order; MultiPolygon values are preserved. Unsupported, malformed, unclosed, or out-of-range geometries are rejected individually. A response with some good features becomes `PARTIAL`; an unusable response or request failure becomes `FAILED`. A valid empty collection is a successful synchronization with zero record counts and preserves the last known good dataset. Partial and failed imports likewise do not deactivate the last known good dataset.

Features use a deterministic SHA-256 identity: the published feature ID is preferred when present; otherwise canonical geometry and properties are hashed. Repeating an unchanged import therefore does not duplicate polygons. After a usable replacement is stored transactionally, features absent from that period's latest response are made inactive; other periods are unaffected. Source properties remain JSONB provenance, and every imported row is constrained to `source = GISTDA`. Sync runs record received, inserted, updated, unchanged, and rejected counts.

Read-only endpoints for future map and operations clients are:

- `GET /api/v1/gistda/flood?period=1day&active=true` — a GeoJSON `FeatureCollection`.
- `GET /api/v1/gistda/status` — latest status, last successful/partial completion, and active feature count for every period.

These responses never include the API key or request headers. `gistda_flood_features.geometry` is an SRID 4326 MultiPolygon with a GiST index, ready for future `ST_Intersects`, `ST_DWithin`, and `ST_Distance` queries; Sprint 3B does not perform branch impact classification.

**Evidence types remain separate:** a `PUBLIC` flood report is a crowdsourced point observation submitted through the Sprint 3A API. A `GISTDA` feature is an official external flood-area polygon with its own period and provenance. GISTDA polygons are never converted into public reports, and the public report request schema offers no `source` field with which a caller could forge one.

## Public flood reporting web app (Sprint 3C)

The unauthenticated, mobile-first Thai reporting flow is available at
`http://localhost:3000/report-flood`. It captures browser geolocation when the
visitor chooses to allow it, but GPS is optional. Device position only recentres
the map: the visitor must explicitly tap the OpenStreetMap map to choose the
observed flood location. The blue circle is device position and the red pin is
the selected flood point. Tile URL and attribution are isolated in
`frontend/lib/config.ts`; automated tests mock the map and never contact tiles.

Run it independently:

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

`NEXT_PUBLIC_API_BASE_URL` selects the FastAPI origin (default
`http://localhost:8000`). `NEXT_PUBLIC_MAP_TILE_URL` can select another
OpenStreetMap-compatible tile service; it must not contain a secret browser key.
The API's comma-separated `CORS_ALLOWED_ORIGINS` defaults to the local web origin.
Docker Compose also includes the `web` service.

### Photo evidence and verification

The JSON create endpoint remains `POST /api/v1/flood-reports`, followed by
`POST /api/v1/flood-reports/{report_code}/photos` with multipart field `photo`.
Creation always ignores the legacy client `has_photo` assertion and begins with
no photo evidence. Only after an accepted image is persisted and its metadata is
committed does the service set `has_photo` and recalculate verification using the
existing backend rule. A failed upload therefore cannot create false verified
evidence.

`LocalPhotoStorage` is the development implementation of the storage boundary;
it writes generated UUID object keys beneath `PHOTO_STORAGE_DIRECTORY` (default
`./var/flood-report-photos`). `PHOTO_MAX_BYTES` defaults to 8 MiB. The server
checks image signatures for JPEG, PNG, or WebP rather than trusting filenames or
client MIME values. PostgreSQL stores only object key, detected content type,
size, and creation time. Filesystem paths and image bytes are never returned or
stored in the database. The interface can later be backed by Azure Blob or S3.

Reporter coordinates, GPS accuracy, and reporter-to-flood distance remain
private verification data and are no longer present in public report responses.
The success UI shows only the report code and verification category. `VERIFIED`
means location evidence is within the configured radius and a persisted photo
exists; it does **not** confirm that flooding actually occurred. The UI sends no
reporter location to analytics services.
