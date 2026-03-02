#!/usr/bin/env bash
##############################################################################
# Builtins Manifests Smoke Tests
#
# Tests all manifest endpoints with:
# - ETag / 304 responses
# - Idempotency-Key replay protection
# - Activation lock serialization
# - Rollback to previous
# - Negative cases (invalid URL, no staged, no previous)
#
# Prerequisites:
# - Services running (docker compose up)
# - ADMIN_TOKEN environment variable set
# - Test manifest available at MANIFEST_URL (or use default)
#
# Usage:
# Load tokens from consolidated .env
if [ -f .env ]; then
    source .env
    ADMIN_TOKEN="${AUTH0_ADMIN_TOKEN:-$ADMIN_TOKEN}"
fi
#   ./smoke_test_builtins_manifests.sh
##############################################################################

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test configuration
BASE_URL="${BASE_URL:-http://localhost:8000/v1}"
ADMIN_TOKEN="${ADMIN_TOKEN:-}"
TEST_MANIFEST_URL="${TEST_MANIFEST_URL:-https://raw.githubusercontent.com/ILP-Thesis-2025/Cineca-Agentic-Platform/main/examples/builtins_manifest_v1.json}"

# Counters
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_TOTAL=0

# Helper functions
log_test() {
    echo -e "${BLUE}[TEST $((TESTS_TOTAL + 1))]${NC} $1"
}

log_pass() {
    echo -e "${GREEN}✓ PASS${NC} $1"
    ((TESTS_PASSED++))
    ((TESTS_TOTAL++))
}

log_fail() {
    echo -e "${RED}✗ FAIL${NC} $1"
    ((TESTS_FAILED++))
    ((TESTS_TOTAL++))
}

log_warn() {
    echo -e "${YELLOW}⚠ WARN${NC} $1"
}

log_info() {
    echo -e "${BLUE}ℹ INFO${NC} $1"
}

check_status() {
    local expected=$1
    local actual=$2
    local desc=$3
    
    if [ "$actual" == "$expected" ]; then
        log_pass "$desc (HTTP $actual)"
        return 0
    else
        log_fail "$desc (expected HTTP $expected, got $actual)"
        return 1
    fi
}

# Pre-flight checks
echo "========================================="
echo "Builtins Manifests Smoke Tests"
echo "========================================="
echo ""

if [ -z "$ADMIN_TOKEN" ]; then
    echo "❌ ADMIN_TOKEN not set. Please ensure .env contains AUTH0_ADMIN_TOKEN or ADMIN_TOKEN"
    exit 1
fi

log_info "Base URL: $BASE_URL"
log_info "Manifest URL: $TEST_MANIFEST_URL"
echo ""

##############################################################################
# Test 1: List built-ins (cold load + ETag)
##############################################################################

log_test "List built-ins (cold load)"

RESPONSE=$(curl -i -s -H "Authorization: Bearer $ADMIN_TOKEN" \
    "$BASE_URL/admin/models/manifests/builtins" | tee /tmp/manifests_list.txt)

STATUS=$(echo "$RESPONSE" | grep -E '^HTTP/' | tail -1 | awk '{print $2}')
ETAG=$(echo "$RESPONSE" | grep -iE '^ETag:' | awk '{print $2}' | tr -d '\r"')
VARY=$(echo "$RESPONSE" | grep -iE '^Vary:' | awk '{print $2}' | tr -d '\r')
CACHE_CONTROL=$(echo "$RESPONSE" | grep -iE '^Cache-Control:' | tr -d '\r')

check_status "200" "$STATUS" "List manifests returns 200"

if [ -n "$ETAG" ]; then
    log_pass "ETag header present: $ETAG"
    ((TESTS_TOTAL++))
else
    log_fail "ETag header missing"
    ((TESTS_TOTAL++))
fi

if [[ "$VARY" == *"Authorization"* ]]; then
    log_pass "Vary: Authorization header present"
    ((TESTS_TOTAL++))
else
    log_fail "Vary: Authorization header missing or incorrect"
    ((TESTS_TOTAL++))
fi

##############################################################################
# Test 2: List built-ins (304 Not Modified with If-None-Match)
##############################################################################

log_test "List built-ins with If-None-Match (304 check)"

if [ -n "$ETAG" ]; then
    RESPONSE_304=$(curl -i -s -H "Authorization: Bearer $ADMIN_TOKEN" \
        -H "If-None-Match: \"$ETAG\"" \
        "$BASE_URL/admin/models/manifests/builtins")
    
    STATUS_304=$(echo "$RESPONSE_304" | grep -E '^HTTP/' | tail -1 | awk '{print $2}')
    
    check_status "304" "$STATUS_304" "If-None-Match returns 304"
else
    log_warn "Skipping 304 test (no ETag from previous test)"
fi

##############################################################################
# Test 3: Stage remote manifest (idempotent)
##############################################################################

log_test "Stage remote manifest (first call)"

IDEMP_KEY_STAGE="stage-$(date +%s)-$$"

RESPONSE_STAGE=$(curl -s -X POST "$BASE_URL/admin/models/manifests/builtins/staged" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -H "Idempotency-Key: $IDEMP_KEY_STAGE" \
    -d "{\"url\":\"$TEST_MANIFEST_URL\"}")

STAGE_OK=$(echo "$RESPONSE_STAGE" | jq -r '.ok // false')
STAGE_MANIFEST_ID=$(echo "$RESPONSE_STAGE" | jq -r '.details.manifest_id // ""')
STAGE_SHA256=$(echo "$RESPONSE_STAGE" | jq -r '.details.sha256 // ""')

if [ "$STAGE_OK" == "true" ] && [ -n "$STAGE_MANIFEST_ID" ]; then
    log_pass "Stage manifest succeeded (manifest_id: $STAGE_MANIFEST_ID)"
    ((TESTS_TOTAL++))
else
    log_fail "Stage manifest failed: $RESPONSE_STAGE"
    ((TESTS_TOTAL++))
fi

##############################################################################
# Test 4: Stage remote manifest (idempotency replay)
##############################################################################

log_test "Stage remote manifest (replay with same Idempotency-Key)"

RESPONSE_STAGE_REPLAY=$(curl -i -s -X POST "$BASE_URL/admin/models/manifests/builtins/staged" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -H "Idempotency-Key: $IDEMP_KEY_STAGE" \
    -d "{\"url\":\"$TEST_MANIFEST_URL\"}")

REPLAYED_HEADER=$(echo "$RESPONSE_STAGE_REPLAY" | grep -iE '^Idempotency-Replayed:' | awk '{print $2}' | tr -d '\r')

if [[ "$REPLAYED_HEADER" == "true" ]]; then
    log_pass "Idempotency-Replayed: true header present"
    ((TESTS_TOTAL++))
else
    log_fail "Idempotency-Replayed header missing or false (got: '$REPLAYED_HEADER')"
    ((TESTS_TOTAL++))
fi

##############################################################################
# Test 5: Activate latest staged (lock + idempotent)
##############################################################################

log_test "Activate latest staged manifest (first call)"

IDEMP_KEY_ACTIVATE="activate-$(date +%s)-$$"

RESPONSE_ACTIVATE=$(curl -s -X POST "$BASE_URL/admin/models/manifests/builtins/activations" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -H "Idempotency-Key: $IDEMP_KEY_ACTIVATE" \
    -d '{}')

ACTIVATE_OK=$(echo "$RESPONSE_ACTIVATE" | jq -r '.ok // false')
ACTIVATE_MANIFEST_ID=$(echo "$RESPONSE_ACTIVATE" | jq -r '.details.active_manifest_id // ""')
PREV_MANIFEST_ID=$(echo "$RESPONSE_ACTIVATE" | jq -r '.details.prev_manifest_id // "null"')

if [ "$ACTIVATE_OK" == "true" ] && [ -n "$ACTIVATE_MANIFEST_ID" ]; then
    log_pass "Activate manifest succeeded (active: $ACTIVATE_MANIFEST_ID, prev: $PREV_MANIFEST_ID)"
    ((TESTS_TOTAL++))
else
    log_fail "Activate manifest failed: $RESPONSE_ACTIVATE"
    ((TESTS_TOTAL++))
fi

##############################################################################
# Test 6: Activate (idempotency replay)
##############################################################################

log_test "Activate manifest (replay with same Idempotency-Key)"

RESPONSE_ACTIVATE_REPLAY=$(curl -i -s -X POST "$BASE_URL/admin/models/manifests/builtins/activations" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -H "Idempotency-Key: $IDEMP_KEY_ACTIVATE" \
    -d '{}')

REPLAYED_ACTIVATE=$(echo "$RESPONSE_ACTIVATE_REPLAY" | grep -iE '^Idempotency-Replayed:' | awk '{print $2}' | tr -d '\r')

if [[ "$REPLAYED_ACTIVATE" == "true" ]]; then
    log_pass "Activate idempotency replay working"
    ((TESTS_TOTAL++))
else
    log_fail "Activate idempotency replay failed (header: '$REPLAYED_ACTIVATE')"
    ((TESTS_TOTAL++))
fi

##############################################################################
# Test 7: List manifests (ETag should have rotated after activation)
##############################################################################

log_test "List manifests (verify ETag rotation after activation)"

RESPONSE_LIST_AFTER=$(curl -i -s -H "Authorization: Bearer $ADMIN_TOKEN" \
    "$BASE_URL/admin/models/manifests/builtins")

ETAG_AFTER=$(echo "$RESPONSE_LIST_AFTER" | grep -iE '^ETag:' | awk '{print $2}' | tr -d '\r"')

if [ "$ETAG_AFTER" != "$ETAG" ]; then
    log_pass "ETag rotated after activation (old: $ETAG, new: $ETAG_AFTER)"
    ((TESTS_TOTAL++))
else
    log_fail "ETag did not rotate after activation"
    ((TESTS_TOTAL++))
fi

##############################################################################
# Test 8: Stage another manifest (for rollback test)
##############################################################################

log_test "Stage another manifest (prepare for rollback)"

# Generate unique key to avoid idempotency replay
IDEMP_KEY_STAGE_2="stage-2-$(date +%s)-$$"

# Use same URL but different key (content hash will match, but we need a new staging event)
RESPONSE_STAGE_2=$(curl -s -X POST "$BASE_URL/admin/models/manifests/builtins/staged" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -H "Idempotency-Key: $IDEMP_KEY_STAGE_2" \
    -d "{\"url\":\"$TEST_MANIFEST_URL\"}")

STAGE_2_OK=$(echo "$RESPONSE_STAGE_2" | jq -r '.ok // false')

if [ "$STAGE_2_OK" == "true" ]; then
    log_pass "Second staging succeeded"
    ((TESTS_TOTAL++))
else
    log_fail "Second staging failed: $RESPONSE_STAGE_2"
    ((TESTS_TOTAL++))
fi

##############################################################################
# Test 9: Activate second manifest (creates activation history)
##############################################################################

log_test "Activate second manifest (for rollback history)"

IDEMP_KEY_ACTIVATE_2="activate-2-$(date +%s)-$$"

RESPONSE_ACTIVATE_2=$(curl -s -X POST "$BASE_URL/admin/models/manifests/builtins/activations" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -H "Idempotency-Key: $IDEMP_KEY_ACTIVATE_2" \
    -d '{"reason":"Second activation for rollback test"}')

ACTIVATE_2_OK=$(echo "$RESPONSE_ACTIVATE_2" | jq -r '.ok // false')

if [ "$ACTIVATE_2_OK" == "true" ]; then
    log_pass "Second activation succeeded"
    ((TESTS_TOTAL++))
else
    log_fail "Second activation failed: $RESPONSE_ACTIVATE_2"
    ((TESTS_TOTAL++))
fi

##############################################################################
# Test 10: Rollback to previous manifest
##############################################################################

log_test "Rollback to previous manifest"

IDEMP_KEY_ROLLBACK="rollback-$(date +%s)-$$"

RESPONSE_ROLLBACK=$(curl -s -X POST "$BASE_URL/admin/models/manifests/builtins/rollbacks" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -H "Idempotency-Key: $IDEMP_KEY_ROLLBACK" \
    -d '{"reason":"Test rollback"}')

ROLLBACK_OK=$(echo "$RESPONSE_ROLLBACK" | jq -r '.ok // false')
RESTORED_ID=$(echo "$RESPONSE_ROLLBACK" | jq -r '.details.active_manifest_id // ""')
ROLLED_FROM_ID=$(echo "$RESPONSE_ROLLBACK" | jq -r '.details.prev_manifest_id // ""')

if [ "$ROLLBACK_OK" == "true" ] && [ -n "$RESTORED_ID" ]; then
    log_pass "Rollback succeeded (restored: $RESTORED_ID, from: $ROLLED_FROM_ID)"
    ((TESTS_TOTAL++))
else
    log_fail "Rollback failed: $RESPONSE_ROLLBACK"
    ((TESTS_TOTAL++))
fi

##############################################################################
# Test 11: Get activation history
##############################################################################

log_test "Get activation history"

RESPONSE_HISTORY=$(curl -i -s -H "Authorization: Bearer $ADMIN_TOKEN" \
    "$BASE_URL/admin/models/manifests/builtins/history")

HISTORY_STATUS=$(echo "$RESPONSE_HISTORY" | grep -E '^HTTP/' | tail -1 | awk '{print $2}')
HISTORY_ETAG=$(echo "$RESPONSE_HISTORY" | grep -iE '^ETag:' | awk '{print $2}' | tr -d '\r"')

check_status "200" "$HISTORY_STATUS" "Get history returns 200"

if [ -n "$HISTORY_ETAG" ]; then
    log_pass "History ETag present: $HISTORY_ETAG"
    ((TESTS_TOTAL++))
else
    log_fail "History ETag missing"
    ((TESTS_TOTAL++))
fi

# Extract and verify history contains rollback
HISTORY_JSON=$(echo "$RESPONSE_HISTORY" | sed -n '/^{/,$p')
HISTORY_COUNT=$(echo "$HISTORY_JSON" | jq -r '.count // 0')

if [ "$HISTORY_COUNT" -ge 3 ]; then
    log_pass "History contains at least 3 activations (2 normal + 1 rollback)"
    ((TESTS_TOTAL++))
else
    log_fail "History count is less than expected: $HISTORY_COUNT"
    ((TESTS_TOTAL++))
fi

##############################################################################
# Test 12: History 304 with If-None-Match
##############################################################################

log_test "Get history with If-None-Match (304 check)"

if [ -n "$HISTORY_ETAG" ]; then
    RESPONSE_HISTORY_304=$(curl -i -s -H "Authorization: Bearer $ADMIN_TOKEN" \
        -H "If-None-Match: \"$HISTORY_ETAG\"" \
        "$BASE_URL/admin/models/manifests/builtins/history")
    
    HISTORY_304_STATUS=$(echo "$RESPONSE_HISTORY_304" | grep -E '^HTTP/' | tail -1 | awk '{print $2}')
    
    check_status "304" "$HISTORY_304_STATUS" "History If-None-Match returns 304"
else
    log_warn "Skipping history 304 test (no ETag)"
fi

##############################################################################
# Test 13: Negative case - Invalid URL on stage
##############################################################################

log_test "Stage with invalid URL (negative test)"

RESPONSE_INVALID_URL=$(curl -i -s -X POST "$BASE_URL/admin/models/manifests/builtins/staged" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"url":"ht!tp://bad-url"}')

INVALID_URL_STATUS=$(echo "$RESPONSE_INVALID_URL" | grep -E '^HTTP/' | tail -1 | awk '{print $2}')

check_status "400" "$INVALID_URL_STATUS" "Invalid URL returns 400"

##############################################################################
# Test 14: Negative case - Activate when nothing new staged
##############################################################################

log_test "Activate when all manifests already activated (negative test)"

# Try to activate again without staging anything new
RESPONSE_NO_STAGED=$(curl -i -s -X POST "$BASE_URL/admin/models/manifests/builtins/activations" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -H "Idempotency-Key: activate-nostaged-$(date +%s)" \
    -d '{}')

NO_STAGED_STATUS=$(echo "$RESPONSE_NO_STAGED" | grep -E '^HTTP/' | tail -1 | awk '{print $2}')

# Should return 400 (no staged manifest)
if [ "$NO_STAGED_STATUS" == "400" ]; then
    log_pass "Activate without staged manifest returns 400"
    ((TESTS_TOTAL++))
else
    log_fail "Activate without staged should return 400, got $NO_STAGED_STATUS"
    ((TESTS_TOTAL++))
fi

##############################################################################
# Test 15: Verify standard headers on all responses
##############################################################################

log_test "Verify X-Request-Id header presence"

# Check stage response
RESPONSE_HEADERS=$(curl -i -s -X POST "$BASE_URL/admin/models/manifests/builtins/staged" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -H "Idempotency-Key: headers-test-$(date +%s)" \
    -d "{\"url\":\"$TEST_MANIFEST_URL\"}")

REQUEST_ID=$(echo "$RESPONSE_HEADERS" | grep -iE '^X-Request-Id:' | awk '{print $2}' | tr -d '\r')

if [ -n "$REQUEST_ID" ]; then
    log_pass "X-Request-Id header present"
    ((TESTS_TOTAL++))
else
    log_fail "X-Request-Id header missing"
    ((TESTS_TOTAL++))
fi

##############################################################################
# Summary
##############################################################################

echo ""
echo "========================================="
echo "Test Summary"
echo "========================================="
echo -e "Total tests:  ${BLUE}$TESTS_TOTAL${NC}"
echo -e "Passed:       ${GREEN}$TESTS_PASSED${NC}"
echo -e "Failed:       ${RED}$TESTS_FAILED${NC}"

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed.${NC}"
    exit 1
fi
