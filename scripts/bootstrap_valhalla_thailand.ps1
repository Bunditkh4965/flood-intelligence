[CmdletBinding()]
param(
    [switch]$Rebuild
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repositoryRoot
try {
    if ($Rebuild) {
        $env:VALHALLA_FORCE_REBUILD = "True"
    }

    Write-Host "Bootstrapping Thailand OSM data in the dedicated valhalla_data volume..."
    docker compose --profile tools run --rm valhalla-bootstrap
    if ($LASTEXITCODE -ne 0) {
        throw "Valhalla bootstrap failed with exit code $LASTEXITCODE."
    }
    Write-Host "Tile build finished. Start the engine with: docker compose up -d valhalla"
}
finally {
    if ($Rebuild) {
        Remove-Item Env:VALHALLA_FORCE_REBUILD -ErrorAction SilentlyContinue
    }
    Pop-Location
}
