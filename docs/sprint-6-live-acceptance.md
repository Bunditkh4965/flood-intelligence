# Sprint 6 live acceptance (PowerShell)

Run from the repository root after configuring `.env` for the existing local stack. The web service uses a Docker named volume for `/app/node_modules`, so Windows host dependencies cannot leak into the Linux container; do not delete or recreate `postgres_data` or `flood_photos`.

```powershell
docker compose up -d --build
docker compose ps
$api = "http://localhost:8000"; $web = "http://localhost:3000"
(Invoke-RestMethod "$api/api/v1/branches").Count # expected 2574 in accepted dataset
$s = Invoke-RestMethod "$api/api/v1/branch-flood-situation?period=3DAYS&gistda_proximity_km=5&public_proximity_km=5&public_lookback_hours=24&limit=1000&offset=0"
$s.summary | Format-List
Invoke-RestMethod "$api/api/v1/branches/10241" | Format-List
(Invoke-RestMethod "$api/api/v1/gistda/flood?period=3days").features.Count
(Invoke-RestMethod "$api/api/v1/flood-reports?status=ACTIVE").Count
Invoke-RestMethod "$api/api/v1/distribution-centers" | Where-Object dc_code -ne "TEST-DC-01" | Format-Table
(Invoke-WebRequest "$web/operations").StatusCode
(Invoke-WebRequest "$web/report-flood").StatusCode
Start-Process "$web/operations"
```

To validate only the web service after a frontend change, the following is sufficient. It preserves all existing named volumes and does not require deleting host `node_modules`:

```powershell
docker compose up -d --build web
docker compose ps web
(Invoke-WebRequest "http://localhost:3000/operations").StatusCode
docker compose logs --tail 100 web
```

At **1440×900**, **768×1024**, and **390×844**, confirm KPI totals match `$s.summary`; toggle all layers and filters; search `10241`; select it and confirm map focus plus factual, source-separated detail. Confirm polygon/report counts match the API and `TEST-DC-01` is absent. Select a real DC, branch, and vehicle and click **คำนวณเส้นทาง**. In DevTools Network confirm the calculate POST is followed by the flood-impact GET. Confirm the map line exactly matches the response `route_geometry` (not a straight line), and distance, duration, provider, calculated time, classification, source status, and separate evidence are shown. Open **รายงานน้ำท่วม** and complete the existing flow.

```powershell
$routeId = "<route_id-from-network-response>"
Invoke-RestMethod "$api/api/v1/routes/$routeId/flood-impact" | ConvertTo-Json -Depth 10
# Both secret scans must return no matches.
Invoke-WebRequest "$web/operations" | Select-String -Pattern "GISTDA_API_KEY|API-Key"
docker compose exec frontend sh -lc 'grep -R "GISTDA_API_KEY\|API-Key" .next/static || true'
Invoke-RestMethod "$api/health"
Invoke-RestMethod "$api/api/v1/gistda/status" | Format-Table
docker compose logs --tail 100 backend frontend
```
