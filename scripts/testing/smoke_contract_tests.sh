#!/usr/bin/env bash
# Simple smoke contract tests against a running service at $BASE
set -euo pipefail
BASE=${1:-http://localhost:8000}

echo "Checking /v1/health/live"
if [ "$(curl -s -o /dev/null -w '%{http_code}' ${BASE%/}/v1/health/live)" -ne 200 ]; then
  echo "live failed"; exit 2
fi

echo "Checking /v1/health/ready"
rc=$(curl -s -o /dev/null -w '%{http_code}' ${BASE%/}/v1/health/ready)
if [ "$rc" = "200" ] || [ "$rc" = "503" ]; then
  echo "ready OK (status $rc)"
else
  echo "ready returned unexpected status $rc"; exit 3
fi

# Check a simple auth happy path (if auth is enabled)
if curl -sSf ${BASE%/}/v1/openapi.json > /dev/null 2>&1; then
  echo "OpenAPI available"
else
  echo "OpenAPI missing"; exit 4
fi

echo "Smoke contract tests passed"
