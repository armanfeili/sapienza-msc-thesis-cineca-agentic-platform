#!/usr/bin/env bash
set -euo pipefail

# Developer helper to run E2E locally (requires docker and permissions)
# Usage: ./scripts/run_e2e.sh

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/.." && pwd)

echo "Bringing up docker-compose stack..."
docker compose up -d --build

# Start a simple static server container to serve the repo on port 9000
docker run --rm -d --name cineca-static -v "$ROOT":/data -w /data -p 9000:9000 python:3.11-slim sh -c "python -m http.server 9000"

# Wait for app healthy
for i in {1..30}; do
  if curl -fsS http://localhost:8000/health; then
    echo "app healthy"
    break
  fi
  sleep 2
done

# Stage manifest
curl -v -X POST -H 'Content-Type: application/json' -d '{"url":"http://host.docker.internal:9000/ops/builtins/manifest.yaml"}' http://localhost:8000/model/builtins/stage || true
# Activate
curl -v -X POST http://localhost:8000/model/builtins/activate || true
# Show history
curl -s http://localhost:8000/model/builtins/history | jq .

# Teardown
docker rm -f cineca-static || true

echo "E2E done"
