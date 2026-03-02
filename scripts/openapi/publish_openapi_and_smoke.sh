#!/usr/bin/env bash
# Fetch /v1/openapi.json and save as artifact, then run a small smoke test against /v1/health/live
set -euo pipefail
BASE_URL=${1:-http://localhost:8000}
OUT=${2:-/tmp/openapi.json}

echo "Fetching openapi from ${BASE_URL}/v1/openapi.json"
curl -sSf "${BASE_URL%/}/v1/openapi.json" -o "${OUT}"

echo "Saved OpenAPI to ${OUT}"

echo "Running smoke: GET /v1/health/live"
status=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL%/}/v1/health/live")
if [ "$status" -ne 200 ]; then
  echo "Health live returned $status"
  exit 2
fi

echo "Smoke tests passed"
