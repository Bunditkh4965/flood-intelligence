[CmdletBinding()]
param([switch]$Rebuild)

$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot
try {
    if ($Rebuild) {
        $env:VALHALLA_FORCE_REBUILD = "True"
    }
    Write-Host "Bootstrapping Thailand OSM data in shared_valhalla_thailand_data..."
    docker compose --profile tools run --rm valhalla-bootstrap
    if ($LASTEXITCODE -ne 0) {
        throw "Valhalla bootstrap failed with exit code $LASTEXITCODE."
    }
    Write-Host "Tile build finished. Start the shared service with: docker compose up -d valhalla"
}
finally {
    if ($Rebuild) {
        Remove-Item Env:VALHALLA_FORCE_REBUILD -ErrorAction SilentlyContinue
    }
    Pop-Location
}
