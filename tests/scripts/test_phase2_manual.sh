#!/usr/bin/env bash
#
# Phase 2 Feature Testing - Manual Version
#

set -euo pipefail

# Import tokens
ADMIN_TOKEN="${ADMIN_TOKEN:-}"
USER_TOKEN="${USER_TOKEN:-}"
MACHINE_TOKEN="${MACHINE_TOKEN:-}"

if [ -z "$MACHINE_TOKEN" ]; then
    echo "❌ ERROR: MACHINE_TOKEN not set!"
    echo "Please run: export MACHINE_TOKEN=<token>"
    exit 1
fi

echo "=========================================="
echo "Phase 2 Feature Testing"
echo "=========================================="
echo ""

# Test 1: Observability Headers
echo "✓ Test 1: Observability Headers (Preview Endpoint)"
curl -i "http://localhost:8000/v1/internal/ops/preview-staged" \
  -H "Authorization: Bearer $MACHINE_TOKEN" 2>&1 | grep -iE "(^HTTP|^x-request-id|^x-correlation-id|^x-subject|^x-cache-status)" | head -5
echo ""

# Test 2: Cache Coherence - Initial (should be miss)
echo "✓ Test 2: Cache Status - First Request (expect: miss)"
curl -s -i "http://localhost:8000/v1/internal/ops/preview-staged" \
  -H "Authorization: Bearer $MACHINE_TOKEN" 2>&1 | grep -i "x-cache-status"
echo ""

# Test 3: Cache Hit
echo "✓ Test 3: Cache Status - Second Request (expect: hit)"
sleep 1
curl -s -i "http://localhost:8000/v1/internal/ops/preview-staged" \
  -H "Authorization: Bearer $MACHINE_TOKEN" 2>&1 | grep -i "x-cache-status"
echo ""

# Test 4: Force Refresh
echo "✓ Test 4: Cache Status - Force Refresh (expect: refresh)"
curl -s -i "http://localhost:8000/v1/internal/ops/preview-staged?force_refresh=true" \
  -H "Authorization: Bearer $MACHINE_TOKEN" 2>&1 | grep -i "x-cache-status"
echo ""

# Test 5: Idempotency - First Request
echo "✓ Test 5: Idempotency - First Request (no Idempotency-Replayed header)"
IDEM_KEY="test-$(date +%s)"
curl -s -i -X POST "http://localhost:8000/v1/internal/ops/auto-start-override" \
  -H "Authorization: Bearer $MACHINE_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $IDEM_KEY" \
  -d '{"enabled": true, "ttl_seconds": 300}' 2>&1 | grep -iE "(^HTTP|^idempotency-replayed|^x-request-id)" | head -3
echo ""

# Test 6: Idempotency - Duplicate Request
echo "✓ Test 6: Idempotency - Duplicate Request (expect: Idempotency-Replayed: true)"
sleep 1
curl -s -i -X POST "http://localhost:8000/v1/internal/ops/auto-start-override" \
  -H "Authorization: Bearer $MACHINE_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $IDEM_KEY" \
  -d '{"enabled": true, "ttl_seconds": 300}' 2>&1 | grep -i "idempotency-replayed"
echo ""

# Test 7: DB Counts Observability
echo "✓ Test 7: DB Counts - Observability Headers"
curl -s -i "http://localhost:8000/v1/internal/db/counts" \
  -H "Authorization: Bearer $MACHINE_TOKEN" 2>&1 | grep -iE "(^HTTP|^x-request-id|^x-correlation-id|^retry-after|^x-feature)" | head -6
echo ""

echo "=========================================="
echo "✅ All Phase 2 Tests Complete!"
echo "=========================================="
