#!/usr/bin/env bash
#
# Comprehensive Health API Testing Script
#
# Tests all canonical health endpoints with various scenarios.
# Validates response formats, status codes, and headers.
#
# Usage:
#   ./test_health_api.sh [BASE_URL]
#
# Environment variables:
#   ADMIN_TOKEN  - Admin authentication token (for /health/startup/readiness)
#   BASE_URL     - API base URL (default: http://localhost:8000/v1)

set -euo pipefail

# Configuration
BASE_URL="${1:-${BASE_URL:-http://localhost:8000/v1}}"
ADMIN_TOKEN="${ADMIN_TOKEN:-}"

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

# Utility functions
log_info() {
    echo -e "${BLUE}ℹ${NC} $*"
}

log_success() {
    echo -e "${GREEN}✓${NC} $*"
    ((TESTS_PASSED++))
}

log_error() {
    echo -e "${RED}✗${NC} $*"
    ((TESTS_FAILED++))
}

log_warning() {
    echo -e "${YELLOW}⚠${NC} $*"
}

# Test helper function
test_endpoint() {
    local name="$1"
    local method="${2:-GET}"
    local path="$3"
    local expected_status="${4:-200}"
    local extra_args="${5:-}"
    
    ((TESTS_RUN++))
    
    log_info "Testing: $name"
    
    # Make request
    local response
    local http_code
    local headers
    
    if [[ "$extra_args" == *"-H"* ]]; then
        response=$(curl -s -w "\n%{http_code}" -X "$method" "${BASE_URL}${path}" $extra_args 2>/dev/null || echo -e "\n000")
    else
        response=$(curl -s -w "\n%{http_code}" -X "$method" "${BASE_URL}${path}" 2>/dev/null || echo -e "\n000")
    fi
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')
    
    # Validate status code
    if [[ "$http_code" == "$expected_status" ]]; then
        log_success "$name - HTTP $http_code (expected $expected_status)"
    else
        log_error "$name - HTTP $http_code (expected $expected_status)"
        echo "Response body: $body"
        return 1
    fi
    
    # Return body for further validation
    echo "$body"
}

# Test deprecated header
test_deprecation_header() {
    local name="$1"
    local path="$2"
    local successor="$3"
    
    ((TESTS_RUN++))
    
    log_info "Testing deprecation headers: $name"
    
    local headers
    headers=$(curl -s -I "${BASE_URL}${path}" 2>/dev/null)
    
    if echo "$headers" | grep -qi "deprecation.*true"; then
        log_success "$name - Deprecation header present"
    else
        log_error "$name - Deprecation header missing"
        return 1
    fi
    
    if echo "$headers" | grep -qi "link.*${successor}"; then
        log_success "$name - Link header points to $successor"
    else
        log_warning "$name - Link header missing or incorrect"
    fi
}

# Validate JSON response structure
validate_json() {
    local body="$1"
    local required_fields="$2"
    
    for field in $required_fields; do
        if ! echo "$body" | grep -q "\"$field\""; then
            log_error "Missing required field: $field"
            return 1
        fi
    done
    
    return 0
}

# ──────────────────────────────────────────────────────────────────────────────
# Main test suite
# ──────────────────────────────────────────────────────────────────────────────

echo ""
echo "════════════════════════════════════════════════════════════════════════════"
echo "  Health API Test Suite"
echo "════════════════════════════════════════════════════════════════════════════"
echo ""
echo "Base URL: $BASE_URL"
echo "Admin Token: ${ADMIN_TOKEN:+<set>}"
echo ""

# ──────────────────────────────────────────────────────────────────────────────
# Canonical Endpoints
# ──────────────────────────────────────────────────────────────────────────────

echo ""
echo "────────────────────────────────────────────────────────────────────────────"
echo "  Canonical Endpoints"
echo "────────────────────────────────────────────────────────────────────────────"
echo ""

# Test /health/live
body=$(test_endpoint "GET /health/live" "GET" "/health/live" "200")
if [[ "$body" == "ok" ]]; then
    log_success "/health/live - Plain text 'ok' response"
else
    log_error "/health/live - Expected plain text 'ok', got: $body"
fi

# Test /health/ready
body=$(test_endpoint "GET /health/ready" "GET" "/health/ready" "200")
if validate_json "$body" "service version status time checks"; then
    log_success "/health/ready - Valid JSON structure"
fi

# Test /health/startup
body=$(test_endpoint "GET /health/startup" "GET" "/health/startup" "200")
if validate_json "$body" "service version status time checks environment limits migrations"; then
    log_success "/health/startup - Valid JSON structure with extras"
fi

# Test /health/components
body=$(test_endpoint "GET /health/components" "GET" "/health/components" "200")
if validate_json "$body" "service version status time checks"; then
    log_success "/health/components - Valid JSON structure"
fi

# Test individual components
for component in postgres redis memgraph providers workers app; do
    body=$(test_endpoint "GET /health/components/$component" "GET" "/health/components/$component" "200")
    if validate_json "$body" "ok status"; then
        log_success "/health/components/$component - Valid JSON structure"
    fi
done

# Test unknown component (should still return 200 with error status)
body=$(test_endpoint "GET /health/components/unknown" "GET" "/health/components/unknown" "200")
if echo "$body" | grep -q "\"ok\".*false"; then
    log_success "/health/components/unknown - Returns error for unknown component"
fi

# ──────────────────────────────────────────────────────────────────────────────
# HEAD Request Support
# ──────────────────────────────────────────────────────────────────────────────

echo ""
echo "────────────────────────────────────────────────────────────────────────────"
echo "  HEAD Request Support"
echo "────────────────────────────────────────────────────────────────────────────"
echo ""

test_endpoint "HEAD /health/live" "HEAD" "/health/live" "204"
test_endpoint "HEAD /health/ready" "HEAD" "/health/ready" "204"
test_endpoint "HEAD /health/startup" "HEAD" "/health/startup" "204"

# ──────────────────────────────────────────────────────────────────────────────
# Admin Endpoints
# ──────────────────────────────────────────────────────────────────────────────

if [[ -n "$ADMIN_TOKEN" ]]; then
    echo ""
    echo "────────────────────────────────────────────────────────────────────────────"
    echo "  Admin Endpoints (readiness toggle)"
    echo "────────────────────────────────────────────────────────────────────────────"
    echo ""
    
    # Test setting readiness to not-ready
    test_endpoint "POST /health/startup/readiness?state=not-ready" \
        "POST" \
        "/health/startup/readiness?state=not-ready" \
        "200" \
        "-H 'X-Admin-Token: $ADMIN_TOKEN'"
    
    # Verify /health/ready returns 503
    test_endpoint "GET /health/ready (after admin disable)" "GET" "/health/ready" "503"
    
    # Test setting readiness back to ready
    test_endpoint "POST /health/startup/readiness?state=ready" \
        "POST" \
        "/health/startup/readiness?state=ready" \
        "200" \
        "-H 'X-Admin-Token: $ADMIN_TOKEN'"
    
    # Verify /health/ready returns 200
    test_endpoint "GET /health/ready (after admin enable)" "GET" "/health/ready" "200"
else
    log_warning "Skipping admin endpoint tests (ADMIN_TOKEN not set)"
fi

# ──────────────────────────────────────────────────────────────────────────────
# Summary
# ──────────────────────────────────────────────────────────────────────────────

echo ""
echo "════════════════════════════════════════════════════════════════════════════"
echo "  Test Summary"
echo "════════════════════════════════════════════════════════════════════════════"
echo ""
echo "Total tests run:    $TESTS_RUN"
echo -e "${GREEN}Passed:${NC}            $TESTS_PASSED"
echo -e "${RED}Failed:${NC}            $TESTS_FAILED"
echo ""

if [[ $TESTS_FAILED -eq 0 ]]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}✗ Some tests failed${NC}"
    exit 1
fi
