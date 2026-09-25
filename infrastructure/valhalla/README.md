# Shared Valhalla Thailand routing infrastructure

## Architecture and scope

This directory is an independently managed Compose project providing a generic
Thailand road-routing HTTP API:

```text
OpenStreetMap Thailand -> Shared Valhalla Routing Infrastructure
                           |-- Flood Intelligence
                           |-- Route Planning / Optimization
                           |-- SMART TPE
                           `-- future transport applications
```

**Valhalla is infrastructure, not part of the Flood Intelligence application
lifecycle.** Starting, stopping, or removing the application Compose project
does not operate on this stack. Consumers use HTTP only; they never mount or
read its volume. No application-specific logic, PostgreSQL credentials, GISTDA
key, Flood Intelligence `.env`, or other application secret enters these
containers.

Valhalla is a self-hosted road-network engine. **Valhalla route geometry is
derived from the OpenStreetMap road network and must never be replaced with a
straight-line approximation.** This POC does not implement a Flood Intelligence
provider, persist routes, analyze floods, or invent dimensions/weights for
`4W`, `6W`, or `10W`. The smoke test uses generic `auto` costing.

## Data, bootstrap, and independent storage

The explicit bootstrap downloads Geofabrik's daily
[Thailand OpenStreetMap extract](https://download.geofabrik.de/asia/thailand.html)
and builds it with pinned image
`ghcr.io/gis-ops/docker-valhalla/valhalla:3.5.1`. The PBF, intermediates, and
tiles persist in the explicitly named Docker volume
`shared_valhalla_thailand_data`. It is owned by this shared infrastructure,
not the Flood Intelligence Compose project, and survives container restarts.
The profile-gated builder cannot run during a normal `docker compose up`.

From this directory, copy `.env.example` to `.env` if overriding defaults, then
bootstrap on Windows PowerShell:

```powershell
.\bootstrap_thailand.ps1
docker compose up -d valhalla
docker compose ps valhalla
python .\smoke_test_thailand.py
```

Or on Linux/macOS/WSL:

```bash
./bootstrap_thailand.sh
docker compose up -d valhalla
docker compose ps valhalla
python3 ./smoke_test_thailand.py
```

Bootstrap requires neither Flood Intelligence nor PostgreSQL. Normal starts
reuse the built tiles. The health check calls `/status`; the standalone smoke
test independently validates `/status`, then POSTs `/route` using two test-only
Bangkok locations (Victory Monument and Wat Arun). It requires a successful
trip, positive distance/time, and encoded polyline6 road shape—not merely HTTP
200. These coordinates are not company DC or branch data. Polyline6 will be
decoded to an SRID 4326 PostGIS LineString only in a future consumer adapter;
this infrastructure does not decode or persist routes.

## HTTP consumer boundary

One instance can serve multiple authorized local consumers over HTTP:

1. Developer process on the host: `http://localhost:8002`.
2. Docker Desktop application calling the host service:
   `http://host.docker.internal:8002`.
3. Future shared server: an environment-specific internal routing-service URL.

Do not hard-code a production host. On Linux/server deployments,
`host.docker.internal` may be absent; use an explicit host-gateway mapping, a
shared network/DNS design, or the internal service hostname appropriate to that
deployment. Consumers must not depend on the Valhalla filesystem. Flood
Intelligence retains only a non-active future `VALHALLA_URL` placeholder; its
`RoutingProvider` is unchanged and does not call this service yet.

## Refresh, resources, and safe operation

Geofabrik updates `thailand-latest.osm.pbf` regularly. Explicitly refresh only
this infrastructure:

```powershell
docker compose stop valhalla
.\bootstrap_thailand.ps1 -Rebuild
docker compose up -d valhalla
python .\smoke_test_thailand.py
```

Use `./bootstrap_thailand.sh --rebuild` in a shell. Review builder logs to
confirm the desired extract was downloaded. Allow several GB of free Docker VM
disk: the compressed PBF is typically hundreds of MB and build intermediates
and tiles require multiples of that. Sizes grow over time. Two build threads
are a conservative default for a 16 GB laptop; building may take many minutes.
The maintained binary image avoids compiling Valhalla C++ locally.

Manage this stack only from this directory:

```bash
docker compose stop              # preserve containers and shared tiles
docker compose down              # remove containers/network; preserve volume
docker compose logs valhalla
```

Do not use `docker compose down -v` or manually remove
`shared_valhalla_thailand_data` unless intentionally discarding routing data.
Never run volume-removal commands in the Flood Intelligence application stack:
its PostgreSQL volume contains branches, GISTDA data, public reports, and DC
test data. This infrastructure has no access to that volume.

For Docker Desktop/Windows, use Linux containers with WSL2. If port 8002 is
occupied, set `VALHALLA_PORT` in this directory's `.env` and pass the matching
`--url` to the smoke test. Increase Docker disk/memory limits if the builder is
killed or reports insufficient space. Corporate proxies must allow GHCR and
Geofabrik; configure credentials in Docker Desktop, never in repository files.
