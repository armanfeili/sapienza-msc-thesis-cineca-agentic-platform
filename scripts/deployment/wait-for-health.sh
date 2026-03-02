#!/bin/bash
# wait-for-health.sh - Wait for app to be healthy after restart
#
# Usage:
#   ./scripts/wait-for-health.sh [timeout_seconds]
#
# Returns:
#   0 - app is healthy
#   1 - timeout or error

set -e

TIMEOUT="${1:-60}"
COUNTER=0
INTERVAL=3

echo "⏳ Waiting for app to be healthy (timeout: ${TIMEOUT}s)..."

while [ $COUNTER -lt $TIMEOUT ]; do
    if docker compose exec -T app curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
        echo "✅ App is healthy!"
        
        # Additional check: verify /v1/health/ready endpoint
        if docker compose exec -T app curl -fsS http://127.0.0.1:8000/v1/health/ready >/dev/null 2>&1; then
            echo "✅ App is ready (all dependencies healthy)!"
            exit 0
        else
            echo "⚠️  App basic health OK but /v1/health/ready not responding"
            echo "   Continuing to wait..."
        fi
    fi
    
    sleep $INTERVAL
    COUNTER=$((COUNTER + INTERVAL))
    echo "   ... waited ${COUNTER}s/${TIMEOUT}s"
done

echo "❌ Timeout waiting for app to become healthy"
echo ""
echo "Last 30 log lines:"
docker compose logs app --tail=30
exit 1
