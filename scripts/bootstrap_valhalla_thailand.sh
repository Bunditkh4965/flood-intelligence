#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [[ "${1:-}" == "--rebuild" ]]; then
  export VALHALLA_FORCE_REBUILD=True
elif [[ $# -gt 0 ]]; then
  echo "Usage: $0 [--rebuild]" >&2
  exit 2
fi

echo "Bootstrapping Thailand OSM data in the dedicated valhalla_data volume..."
docker compose --profile tools run --rm valhalla-bootstrap
echo "Tile build finished. Start the engine with: docker compose up -d valhalla"
