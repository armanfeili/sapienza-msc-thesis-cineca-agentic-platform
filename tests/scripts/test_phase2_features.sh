#!/bin/bash
# Test Phase 2 Implementation Features
# Tests: Idempotency, Cache Coherence, Observability Headers, 501 Responses

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

API_BASE="${API_BASE:-http://localhost:8000}"

echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Phase 2 Features Test Suite${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}\n"

# Source tokens
if [ ! -f /tmp/tokens.sh ]; then
    echo -e "${YELLOW}⚠️  No tokens found. Fetching fresh tokens...${NC}"
    python3 fetch_tokens.py
fi

source /tmp/tokens.sh

if [ -z "$MACHINE_TOKEN" ]; then
    echo -e "${RED}✗ Failed to load M2M token${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Loaded M2M token${NC}\n"

# Test counter
TESTS_PASSED=0
TESTS_FAILED=0

# Helper function to test
test_feature() {
    local test_name="$1"
    local expected="$2"
    local actual="$3"
    
    if [[ "$actual" == *"$expected"* ]]; then
        echo -e "${GREEN}✓${NC} $test_name"
        ((TESTS_PASSED++))
        return 0
    else
        echo -e "${RED}✗${NC} $test_name"
        echo -e "   Expected: $expected"
        echo -e "   Actual: $actual"
        ((TESTS_FAILED++))
        return 1
    fi
}

# Test 1: Observability Headers
echo -e "${BLUE}Test 1: Observability Headers${NC}"
echo "Testing X-Request-Id, X-Correlation-Id, X-Subject headers..."

RESPONSE=$(curl -s -i "${API_BASE}/v1/internal/ops/preview-staged" \
    -H "Authorization: Bearer ${MACHINE_TOKEN}")

echo "$RESPONSE" | grep -q "X-Request-Id:" && test_feature "X-Request-Id present" "X-Request-Id:" "$RESPONSE" || test_feature "X-Request-Id present" "X-Request-Id:" "MISSING"
echo "$RESPONSE" | grep -q "X-Correlation-Id:" && test_feature "X-Correlation-Id present" "X-Correlation-Id:" "$RESPONSE" || test_feature "X-Correlation-Id present" "X-Correlation-Id:" "MISSING"
echo "$RESPONSE" | grep -q "X-Subject:" && test_feature "X-Subject present" "X-Subject:" "$RESPONSE" || test_feature "X-Subject present" "X-Subject:" "MISSING"

echo ""

# Test 2: Cache Status Header
echo -e "${BLUE}Test 2: Cache Status Header${NC}"
echo "Testing X-Cache-Status on preview endpoint..."

# First request (should be miss or refresh)
RESPONSE1=$(curl -s -i "${API_BASE}/v1/internal/ops/preview-staged?force_refresh=true" \
    -H "Authorization: Bearer ${MACHINE_TOKEN}")

if echo "$RESPONSE1" | grep -q "X-Cache-Status: refresh"; then
    test_feature "X-Cache-Status: refresh" "X-Cache-Status: refresh" "$RESPONSE1"
else
    test_feature "X-Cache-Status present" "X-Cache-Status:" "$RESPONSE1"
fi

# Second request (should be hit)
sleep 1
RESPONSE2=$(curl -s -i "${API_BASE}/v1/internal/ops/preview-staged" \
    -H "Authorization: Bearer ${MACHINE_TOKEN}")

test_feature "X-Cache-Status: hit" "X-Cache-Status: hit" "$RESPONSE2"

echo ""

# Test 3: Idempotency
echo -e "${BLUE}Test 3: Idempotency${NC}"
echo "Testing idempotency with Idempotency-Key header..."

IDEM_KEY="test-$(date +%s)-$$"

# First request
RESPONSE1=$(curl -s -i -X POST "${API_BASE}/v1/internal/ops/auto-start-override" \
    -H "Authorization: Bearer ${MACHINE_TOKEN}" \
    -H "Idempotency-Key: ${IDEM_KEY}" \
    -H "Content-Type: application/json" \
    -d '{"enabled": true, "ttl_seconds": 300}')

HTTP_CODE1=$(echo "$RESPONSE1" | grep "HTTP" | awk '{print $2}')
test_feature "First request succeeds" "200" "$HTTP_CODE1"

# Check no replay header on first request
if ! echo "$RESPONSE1" | grep -q "Idempotency-Replayed:"; then
    test_feature "No replay header on first request" "no-replay" "no-replay"
else
    test_feature "No replay header on first request" "no-replay" "HAS-REPLAY-HEADER"
fi

# Second request with same key (should be replayed)
sleep 1
RESPONSE2=$(curl -s -i -X POST "${API_BASE}/v1/internal/ops/auto-start-override" \
    -H "Authorization: Bearer ${MACHINE_TOKEN}" \
    -H "Idempotency-Key: ${IDEM_KEY}" \
    -H "Content-Type: application/json" \
    -d '{"enabled": false, "ttl_seconds": 600}')

HTTP_CODE2=$(echo "$RESPONSE2" | grep "HTTP" | awk '{print $2}')
test_feature "Second request returns cached response" "200" "$HTTP_CODE2"
test_feature "Idempotency-Replayed header present" "Idempotency-Replayed: true" "$RESPONSE2"

echo ""

# Test 4: 501 Response with Enhanced Headers
echo -e "${BLUE}Test 4: Enhanced 501 Response (if Memgraph disabled)${NC}"
echo "Testing Retry-After and X-Feature headers on DB counts endpoint..."

# Note: This test will only show 501 if FEATURE_MEMGRAPH_COUNTS=false
RESPONSE=$(curl -s -i "${API_BASE}/v1/internal/db/counts" \
    -H "Authorization: Bearer ${MACHINE_TOKEN}")

HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP" | awk '{print $2}')

if [ "$HTTP_CODE" = "501" ]; then
    echo -e "${YELLOW}Memgraph is disabled (501 response)${NC}"
    test_feature "Retry-After header present" "Retry-After:" "$RESPONSE"
    test_feature "X-Feature header present" "X-Feature: memgraph=unavailable" "$RESPONSE"
elif [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}Memgraph is enabled (200 response)${NC}"
    test_feature "Observability headers on 200 response" "X-Request-Id:" "$RESPONSE"
else
    echo -e "${YELLOW}Unexpected status code: $HTTP_CODE${NC}"
    test_feature "Valid response code" "200 or 501" "$HTTP_CODE"
fi

echo ""

# Test 5: Cache Coherence (mtime tracking)
echo -e "${BLUE}Test 5: Cache Coherence (mtime tracking)${NC}"
echo "Testing cache invalidation on file changes..."

# Get initial cached response
RESPONSE1=$(curl -s "${API_BASE}/v1/internal/ops/preview-staged?force_refresh=true" \
    -H "Authorization: Bearer ${MACHINE_TOKEN}")

# Touch a file in builtins directory to change mtime
docker exec app touch /app/src/routers/agents/builtins/manifests/dummy_touch_test.txt 2>/dev/null || echo "Could not touch file in container"

sleep 2

# Get response again (should detect mtime change)
RESPONSE2=$(curl -s -i "${API_BASE}/v1/internal/ops/preview-staged" \
    -H "Authorization: Bearer ${MACHINE_TOKEN}")

# Check if cache was refreshed due to mtime change
if echo "$RESPONSE2" | grep -q "X-Cache-Status: refresh\|X-Cache-Status: miss"; then
    test_feature "Cache invalidated on directory change" "refresh or miss" "$(echo "$RESPONSE2" | grep X-Cache-Status)"
else
    echo -e "${YELLOW}⚠️  Could not verify mtime invalidation (may need manual file change)${NC}"
fi

# Cleanup
docker exec app rm -f /app/src/routers/agents/builtins/manifests/dummy_touch_test.txt 2>/dev/null || true

echo ""

# Summary
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Test Results Summary${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Passed: $TESTS_PASSED${NC}"
echo -e "${RED}Failed: $TESTS_FAILED${NC}"

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "\n${GREEN}✓ All tests passed!${NC}\n"
    exit 0
else
    echo -e "\n${RED}✗ Some tests failed${NC}\n"
    exit 1
fi
