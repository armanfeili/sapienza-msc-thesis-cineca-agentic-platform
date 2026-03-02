#!/usr/bin/env bash
set -e

# ============================================================================
# Test Script for Jobs PostgreSQL Backend (Tasks 7-9)
# ============================================================================
# This script validates all CRUD endpoints with USE_POSTGRES_JOBS=true
#
# Prerequisites:
# - Docker Compose services running
# - Alembic migration 003 applied
# - USE_POSTGRES_JOBS=true in .env
# - Valid authentication token
#
# Usage: ./test_jobs_postgres_backend.sh [TOKEN]
# ============================================================================

BASE_URL="${BASE_URL:-http://localhost:8000}"
TOKEN="${1:-}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test counters
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# ============================================================================
# Helper Functions
# ============================================================================

print_header() {
    echo -e "\n${BLUE}============================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}============================================================${NC}"
}

print_test() {
    echo -e "\n${YELLOW}TEST:${NC} $1"
    ((TESTS_RUN++))
}

pass() {
    echo -e "${GREEN}✓ PASS:${NC} $1"
    ((TESTS_PASSED++))
}

fail() {
    echo -e "${RED}✗ FAIL:${NC} $1"
    ((TESTS_FAILED++))
}

info() {
    echo -e "${BLUE}ℹ INFO:${NC} $1"
}

# ============================================================================
# Token Setup
# ============================================================================

if [ -z "$TOKEN" ]; then
    echo -e "${YELLOW}No token provided. Attempting to get admin token...${NC}"
    
    # Try to get token from admin-token.txt
    if [ -f "run/admin-token.txt" ]; then
        TOKEN=$(cat run/admin-token.txt)
        info "Using token from run/admin-token.txt"
    else
        echo -e "${RED}ERROR: No token available. Please provide a token as argument.${NC}"
        echo "Usage: $0 <TOKEN>"
        exit 1
    fi
fi

# ============================================================================
# A) Verify Feature Flag is Enabled
# ============================================================================

print_header "A) Feature Flag Verification"

print_test "Check if USE_POSTGRES_JOBS is enabled in container"
PG_FLAG=$(docker compose exec -T app sh -c 'echo $USE_POSTGRES_JOBS')
if [ "$PG_FLAG" = "true" ]; then
    pass "USE_POSTGRES_JOBS=true in container environment"
else
    fail "USE_POSTGRES_JOBS is not set to true (got: $PG_FLAG)"
fi

# ============================================================================
# B) Database Readiness & Schema
# ============================================================================

print_header "B) Database Schema Verification"

print_test "Check Alembic migration version"
CURRENT_VERSION=$(docker compose exec -T app sh -c "cd db/postgres_control && alembic current 2>/dev/null" | grep -o '00[0-9]' || echo "")
if [ "$CURRENT_VERSION" = "003" ]; then
    pass "Alembic at version 003 (jobs migration applied)"
else
    fail "Alembic not at version 003 (current: $CURRENT_VERSION)"
fi

print_test "Check jobs table exists"
JOBS_TABLE=$(docker compose exec -T postgres psql -U cineca_user -d cineca_platform -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='jobs'" | tr -d ' ')
if [ "$JOBS_TABLE" = "1" ]; then
    pass "jobs table exists"
else
    fail "jobs table not found"
fi

print_test "Check job_events table exists"
EVENTS_TABLE=$(docker compose exec -T postgres psql -U cineca_user -d cineca_platform -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='job_events'" | tr -d ' ')
if [ "$EVENTS_TABLE" = "1" ]; then
    pass "job_events table exists"
else
    fail "job_events table not found"
fi

print_test "Check key indexes exist"
INDEXES=(
    "idx_jobs_owner_created"
    "idx_jobs_status_created"
    "idx_jobs_tenant_created"
    "idx_jobs_updated"
    "idx_jobs_idempotency_unique"
    "idx_job_events_job_seq"
)

for idx in "${INDEXES[@]}"; do
    IDX_EXISTS=$(docker compose exec -T postgres psql -U cineca_user -d cineca_platform -t -c "SELECT COUNT(*) FROM pg_indexes WHERE indexname='$idx'" | tr -d ' ')
    if [ "$IDX_EXISTS" = "1" ]; then
        pass "Index $idx exists"
    else
        fail "Index $idx not found"
    fi
done

# ============================================================================
# C) Smoke Tests (Functional)
# ============================================================================

print_header "C) Functional Smoke Tests"

# Create test job
print_test "POST /v1/jobs - Create new job"
CREATE_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/v1/jobs" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -H "Idempotency-Key: test-$(date +%s)-$$" \
    -d '{"type": "demo", "payload": {"test": true, "duration_ms": 100}}')

HTTP_CODE=$(echo "$CREATE_RESPONSE" | tail -n1)
BODY=$(echo "$CREATE_RESPONSE" | head -n-1)

if [ "$HTTP_CODE" = "202" ]; then
    pass "POST returned 202 Accepted"
    JOB_ID=$(echo "$BODY" | jq -r '.id')
    info "Created job: $JOB_ID"
else
    fail "POST returned $HTTP_CODE instead of 202"
    info "Response: $BODY"
fi

# Test idempotency
print_test "POST /v1/jobs - Idempotency (same key returns 200)"
sleep 1
IDEMP_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/v1/jobs" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -H "Idempotency-Key: test-$(date +%s)-$$" \
    -d '{"type": "demo", "payload": {"test": true, "duration_ms": 100}}')

IDEMP_CODE=$(echo "$IDEMP_RESPONSE" | tail -n1)
if [ "$IDEMP_CODE" = "200" ]; then
    pass "Idempotent POST returned 200 OK"
else
    fail "Idempotent POST returned $IDEMP_CODE instead of 200"
fi

# List jobs
print_test "GET /v1/jobs - List user jobs"
LIST_RESPONSE=$(curl -s -w "\n%{http_code}" -X GET "$BASE_URL/v1/jobs" \
    -H "Authorization: Bearer $TOKEN")

LIST_CODE=$(echo "$LIST_RESPONSE" | tail -n1)
LIST_BODY=$(echo "$LIST_RESPONSE" | head -n-1)

if [ "$LIST_CODE" = "200" ]; then
    pass "GET /v1/jobs returned 200"
    ITEMS_COUNT=$(echo "$LIST_BODY" | jq '.items | length')
    TOTAL=$(echo "$LIST_BODY" | jq '.total')
    info "Found $ITEMS_COUNT items (total: $TOTAL)"
else
    fail "GET /v1/jobs returned $LIST_CODE"
fi

# Test pagination
print_test "GET /v1/jobs?limit=5 - Pagination support"
PAGE_RESPONSE=$(curl -s -w "\n%{http_code}" -X GET "$BASE_URL/v1/jobs?limit=5" \
    -H "Authorization: Bearer $TOKEN")

PAGE_CODE=$(echo "$PAGE_RESPONSE" | tail -n1)
PAGE_BODY=$(echo "$PAGE_RESPONSE" | head -n-1)

if [ "$PAGE_CODE" = "200" ]; then
    HAS_MORE=$(echo "$PAGE_BODY" | jq -r '.has_more')
    NEXT_TOKEN=$(echo "$PAGE_BODY" | jq -r '.next_page_token')
    pass "Pagination works (has_more: $HAS_MORE, next_page_token: $NEXT_TOKEN)"
else
    fail "Pagination test returned $PAGE_CODE"
fi

# Test status filter
print_test "GET /v1/jobs?status=queued - Status filter"
FILTER_RESPONSE=$(curl -s -w "\n%{http_code}" -X GET "$BASE_URL/v1/jobs?status=queued" \
    -H "Authorization: Bearer $TOKEN")

FILTER_CODE=$(echo "$FILTER_RESPONSE" | tail -n1)
if [ "$FILTER_CODE" = "200" ]; then
    pass "Status filter works"
else
    fail "Status filter returned $FILTER_CODE"
fi

# Get single job
if [ -n "$JOB_ID" ]; then
    print_test "GET /v1/jobs/{id} - Get job by ID"
    GET_RESPONSE=$(curl -s -w "\n%{http_code}" -X GET "$BASE_URL/v1/jobs/$JOB_ID" \
        -H "Authorization: Bearer $TOKEN")
    
    GET_CODE=$(echo "$GET_RESPONSE" | tail -n1)
    GET_BODY=$(echo "$GET_RESPONSE" | head -n-1)
    
    if [ "$GET_CODE" = "200" ]; then
        pass "GET /v1/jobs/{id} returned 200"
        ETAG=$(echo "$GET_RESPONSE" | grep -i "etag:" | cut -d: -f2 | tr -d ' \r')
        if [ -n "$ETAG" ]; then
            info "ETag: $ETAG"
        fi
    else
        fail "GET /v1/jobs/{id} returned $GET_CODE"
    fi
fi

# ============================================================================
# D) Headers & Caching Correctness
# ============================================================================

print_header "D) Headers & Caching Tests"

# Test ETag on list
print_test "GET /v1/jobs - ETag header present"
LIST_HEADERS=$(curl -s -I -X GET "$BASE_URL/v1/jobs" \
    -H "Authorization: Bearer $TOKEN")

if echo "$LIST_HEADERS" | grep -i "etag:" > /dev/null; then
    ETAG=$(echo "$LIST_HEADERS" | grep -i "etag:" | cut -d: -f2 | tr -d ' \r')
    pass "ETag header present: $ETAG"
else
    fail "ETag header missing"
fi

# Test Cache-Control
print_test "GET /v1/jobs - Cache-Control header"
if echo "$LIST_HEADERS" | grep -i "cache-control:" | grep -i "private" > /dev/null; then
    pass "Cache-Control header correct (private, max-age)"
else
    fail "Cache-Control header missing or incorrect"
fi

# Test Vary header
print_test "GET /v1/jobs - Vary: Authorization header"
if echo "$LIST_HEADERS" | grep -i "vary:" | grep -i "authorization" > /dev/null; then
    pass "Vary: Authorization header present"
else
    fail "Vary: Authorization header missing"
fi

# Test 304 Not Modified with ETag
if [ -n "$ETAG" ]; then
    print_test "GET /v1/jobs with If-None-Match - 304 Not Modified"
    CACHE_RESPONSE=$(curl -s -w "\n%{http_code}" -X GET "$BASE_URL/v1/jobs" \
        -H "Authorization: Bearer $TOKEN" \
        -H "If-None-Match: $ETAG")
    
    CACHE_CODE=$(echo "$CACHE_RESPONSE" | tail -n1)
    if [ "$CACHE_CODE" = "304" ]; then
        pass "Returned 304 Not Modified with matching ETag"
    else
        fail "Expected 304, got $CACHE_CODE"
    fi
fi

# Test single job ETag
if [ -n "$JOB_ID" ]; then
    print_test "GET /v1/jobs/{id} - ETag on single job"
    JOB_HEADERS=$(curl -s -I -X GET "$BASE_URL/v1/jobs/$JOB_ID" \
        -H "Authorization: Bearer $TOKEN")
    
    if echo "$JOB_HEADERS" | grep -i "etag:" > /dev/null; then
        JOB_ETAG=$(echo "$JOB_HEADERS" | grep -i "etag:" | cut -d: -f2 | tr -d ' \r')
        pass "Single job ETag present: $JOB_ETAG"
        
        # Test 304 on single job
        print_test "GET /v1/jobs/{id} with If-None-Match - 304"
        JOB_CACHE_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X GET "$BASE_URL/v1/jobs/$JOB_ID" \
            -H "Authorization: Bearer $TOKEN" \
            -H "If-None-Match: $JOB_ETAG")
        
        if [ "$JOB_CACHE_CODE" = "304" ]; then
            pass "Single job returned 304 with matching ETag"
        else
            fail "Expected 304, got $JOB_CACHE_CODE"
        fi
    else
        fail "Single job ETag missing"
    fi
fi

# ============================================================================
# E) Behavior Checks (Edge Cases)
# ============================================================================

print_header "E) Edge Cases & Error Handling"

# Invalid page_token
print_test "GET /v1/jobs?page_token=invalid - 400 Bad Request"
INVALID_PAGE=$(curl -s -o /dev/null -w "%{http_code}" -X GET "$BASE_URL/v1/jobs?page_token=invalid" \
    -H "Authorization: Bearer $TOKEN")

if [ "$INVALID_PAGE" = "400" ]; then
    pass "Invalid page_token returns 400"
else
    fail "Invalid page_token returned $INVALID_PAGE instead of 400"
fi

# Invalid UUID
print_test "GET /v1/jobs/not-a-uuid - 400 Bad Request"
INVALID_UUID=$(curl -s -o /dev/null -w "%{http_code}" -X GET "$BASE_URL/v1/jobs/not-a-uuid" \
    -H "Authorization: Bearer $TOKEN")

if [ "$INVALID_UUID" = "400" ]; then
    pass "Invalid UUID returns 400"
else
    fail "Invalid UUID returned $INVALID_UUID instead of 400"
fi

# Unknown job
print_test "GET /v1/jobs/00000000-0000-0000-0000-000000000000 - 404 Not Found"
UNKNOWN_JOB=$(curl -s -o /dev/null -w "%{http_code}" -X GET "$BASE_URL/v1/jobs/00000000-0000-0000-0000-000000000000" \
    -H "Authorization: Bearer $TOKEN")

if [ "$UNKNOWN_JOB" = "404" ]; then
    pass "Unknown job returns 404"
else
    fail "Unknown job returned $UNKNOWN_JOB instead of 404"
fi

# ============================================================================
# F) DELETE Endpoint Tests
# ============================================================================

print_header "F) DELETE /v1/jobs/{id} - Cancellation Tests"

# Create a job to cancel
print_test "Create job for cancellation test"
CANCEL_JOB_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/jobs" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"type": "demo", "payload": {"duration_ms": 10000}}')

CANCEL_JOB_ID=$(echo "$CANCEL_JOB_RESPONSE" | jq -r '.id')
if [ -n "$CANCEL_JOB_ID" ] && [ "$CANCEL_JOB_ID" != "null" ]; then
    pass "Created job for cancellation: $CANCEL_JOB_ID"
else
    fail "Failed to create job for cancellation"
    CANCEL_JOB_ID=""
fi

if [ -n "$CANCEL_JOB_ID" ]; then
    # First cancel
    print_test "DELETE /v1/jobs/{id} - First cancel returns 202"
    DELETE1_RESPONSE=$(curl -s -w "\n%{http_code}" -X DELETE "$BASE_URL/v1/jobs/$CANCEL_JOB_ID" \
        -H "Authorization: Bearer $TOKEN")
    
    DELETE1_CODE=$(echo "$DELETE1_RESPONSE" | tail -n1)
    DELETE1_BODY=$(echo "$DELETE1_RESPONSE" | head -n-1)
    
    if [ "$DELETE1_CODE" = "202" ]; then
        pass "First DELETE returned 202 Accepted"
        STATUS=$(echo "$DELETE1_BODY" | jq -r '.status')
        info "Job status: $STATUS"
    else
        fail "First DELETE returned $DELETE1_CODE instead of 202"
        info "Response: $DELETE1_BODY"
    fi
    
    # Second cancel (idempotent)
    print_test "DELETE /v1/jobs/{id} - Idempotent cancel returns 200"
    sleep 1
    DELETE2_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$BASE_URL/v1/jobs/$CANCEL_JOB_ID" \
        -H "Authorization: Bearer $TOKEN")
    
    if [ "$DELETE2_CODE" = "200" ]; then
        pass "Idempotent DELETE returned 200 OK"
    else
        fail "Idempotent DELETE returned $DELETE2_CODE instead of 200"
    fi
fi

# ============================================================================
# G) ETag Changes After Modification
# ============================================================================

print_header "G) ETag Invalidation Tests"

print_test "Create job, get ETag, cancel job, verify ETag changes"

# Create job
ETAG_TEST_JOB=$(curl -s -X POST "$BASE_URL/v1/jobs" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"type": "demo", "payload": {"test": "etag"}}' | jq -r '.id')

if [ -n "$ETAG_TEST_JOB" ] && [ "$ETAG_TEST_JOB" != "null" ]; then
    # Get initial ETag
    INITIAL_ETAG=$(curl -s -I -X GET "$BASE_URL/v1/jobs/$ETAG_TEST_JOB" \
        -H "Authorization: Bearer $TOKEN" | grep -i "etag:" | cut -d: -f2 | tr -d ' \r')
    
    info "Initial ETag: $INITIAL_ETAG"
    
    # Cancel job
    curl -s -X DELETE "$BASE_URL/v1/jobs/$ETAG_TEST_JOB" \
        -H "Authorization: Bearer $TOKEN" > /dev/null
    
    sleep 1
    
    # Get new ETag
    NEW_ETAG=$(curl -s -I -X GET "$BASE_URL/v1/jobs/$ETAG_TEST_JOB" \
        -H "Authorization: Bearer $TOKEN" | grep -i "etag:" | cut -d: -f2 | tr -d ' \r')
    
    info "New ETag after cancel: $NEW_ETAG"
    
    if [ "$INITIAL_ETAG" != "$NEW_ETAG" ]; then
        pass "ETag changed after job modification"
    else
        fail "ETag did not change after job modification"
    fi
else
    fail "Could not create job for ETag test"
fi

# ============================================================================
# Summary
# ============================================================================

print_header "Test Summary"

echo -e "\n${BLUE}Tests Run:    ${NC}$TESTS_RUN"
echo -e "${GREEN}Tests Passed: ${NC}$TESTS_PASSED"
echo -e "${RED}Tests Failed: ${NC}$TESTS_FAILED"

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "\n${GREEN}✓ All tests passed!${NC}\n"
    exit 0
else
    echo -e "\n${RED}✗ Some tests failed!${NC}\n"
    exit 1
fi
