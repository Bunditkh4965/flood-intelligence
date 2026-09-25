#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

if [[ "${1:-}" == "--rebuild" ]]; then
  export VALHALLA_FORCE_REBUILD=True
elif [[ $# -gt 0 ]]; then
  echo "Usage: $0 [--rebuild]" >&2
  exit 2
fi

echo "Bootstrapping Thailand OSM data in shared_valhalla_thailand_data..."
docker compose --profile tools run --rm valhalla-bootstrap
echo "Tile build finished. Start the shared service with: docker compose up -d valhalla"
