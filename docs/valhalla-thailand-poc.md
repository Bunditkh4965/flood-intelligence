# Local Valhalla Thailand routing POC (Sprint 5B-POC)

## Purpose and boundaries

[Valhalla](https://github.com/valhalla/valhalla) is a self-hosted road-network
routing engine. This POC runs the pinned `gis-ops/docker-valhalla` image locally
and prepares Thailand routing tiles. It is infrastructure only: FastAPI's
Sprint 5A `RoutingProvider` remains unconfigured, and no route is written to
`transport_routes`. There is no flood intersection, risk analysis, rerouting,
dashboard, or truck-specific configuration.

**Valhalla route geometry is derived from the OpenStreetMap road network. It is
not a straight line between origin and destination.**

The smoke test uses Valhalla's basic `auto` costing only. `4W`, `6W`, and `10W`
are not mapped to invented height, width, length, weight, or axle-load values.
Real business vehicle constraints belong in a later sprint.

## Data source and storage

The bootstrap downloads Geofabrik's daily
[Thailand OpenStreetMap extract](https://download.geofabrik.de/asia/thailand.html)
(`thailand-latest.osm.pbf`). OpenStreetMap data is © OpenStreetMap contributors
and available under the ODbL. The PBF, build database/configuration, and routing
tiles live in the Docker named volume `valhalla_data`, outside Git. Both
`*.osm.pbf` and the optional `data/valhalla/` local directory are ignored.

The image is pinned to `ghcr.io/gis-ops/docker-valhalla/valhalla:3.5.1` rather
than `latest`. The bootstrap service is behind the `tools` Compose profile, so
normal `docker compose up` **does not download data or build tiles**.

## Bootstrap and start

Prerequisites are Docker Desktop with the WSL2 backend and Compose v2. From the
repository root on Windows PowerShell:

```powershell
Copy-Item .env.example .env # then set POSTGRES_PASSWORD
.\scripts\bootstrap_valhalla_thailand.ps1
docker compose up -d valhalla
docker compose ps valhalla
Invoke-RestMethod http://localhost:8002/status
python .\scripts\smoke_test_valhalla_thailand.py
```

On Linux, macOS, or WSL:

```bash
cp .env.example .env # then set POSTGRES_PASSWORD
./scripts/bootstrap_valhalla_thailand.sh
docker compose up -d valhalla
curl --fail http://localhost:8002/status
python3 scripts/smoke_test_valhalla_thailand.py
```

The status-based Docker health check must succeed before the container becomes
healthy; an existing container process alone is not treated as success. The
smoke test is stronger: it POSTs `/route` for two **test-only** Bangkok
coordinates (Victory Monument `13.7649, 100.5383` and Wat Arun `13.7437,
100.4889`). They are not company DC or branch data. It fails unless the response
contains legs, positive distance, positive time, and a non-empty route shape;
HTTP 200 alone is insufficient.

Valhalla returns each leg's shape as an **encoded polyline6** string. A future
Sprint 5B application integration will decode longitude/latitude road-shape
coordinates and create a PostGIS `LineString` with SRID 4326. This POC neither
decodes nor persists that geometry.

## Refresh or rebuild tiles

Geofabrik updates the `-latest` extract regularly. Stop only Valhalla, then run
the explicit rebuild and restart it:

```powershell
docker compose stop valhalla
.\scripts\bootstrap_valhalla_thailand.ps1 -Rebuild
docker compose up -d valhalla
python .\scripts\smoke_test_valhalla_thailand.py
```

The shell equivalent is
`./scripts/bootstrap_valhalla_thailand.sh --rebuild`. This replaces/rebuilds
only assets in the dedicated Valhalla volume; it does not operate on PostgreSQL.
Review the builder log to confirm the desired dated extract was downloaded.

## Resource and data safety

Allow several gigabytes of free disk: the compressed Thailand PBF is typically
hundreds of MB, while unpacked build intermediates and routing tiles can require
multiple times its size. Exact sizes change as OpenStreetMap grows. Two build
threads are the conservative default for a roughly 16 GB laptop; set
`VALHALLA_BUILD_THREADS` deliberately if needed. Docker Desktop's VM disk must
have enough free space, and building may take many minutes.

Stop Valhalla without removing any data:

```bash
docker compose stop valhalla
```

Or stop the whole stack with `docker compose down` (without `-v`). **Never use
`docker compose down -v` as normal cleanup**: it deletes the existing named
PostgreSQL volume as well as Valhalla data. The bootstrap services mount only
`valhalla_data`; they cannot reset branch, GISTDA, report, DC, or PostgreSQL
data.

## Troubleshooting Docker Desktop / Windows

- Ensure Docker Desktop uses Linux containers and WSL2, and run `docker compose
  version` to confirm Compose v2.
- If port 8002 is occupied, set `VALHALLA_PORT=8003` in `.env`, then use
  `--url http://localhost:8003` with the smoke test. Container-to-container URL
  remains the inactive configuration placeholder `http://valhalla:8002`.
- If the builder is killed or Docker reports no space, increase Docker Desktop
  memory/disk limits and rerun the bootstrap. The operation is isolated from
  `postgres_data`.
- Inspect progress/errors with `docker compose logs valhalla`; an unhealthy
  runtime commonly means bootstrap did not finish or the volume has no usable
  tiles.
- Corporate proxies must allow Geofabrik and GHCR. Configure the proxy in
  Docker Desktop; do not put credentials in `.env` or source control.
- File sharing is not required for the named volume. Running scripts from a WSL
  checkout generally avoids slow Windows bind-mount I/O.
