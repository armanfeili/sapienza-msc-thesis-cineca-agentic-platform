#!/bin/bash
# PostgreSQL Migration Validation Script
# Tests all admin-tenants endpoints with PostgreSQL backend

set -e

BASE_URL="${BASE_URL:-http://localhost:8000}"
ADMIN_TOKEN="${ADMIN_TOKEN:-test-admin-token}"

echo "🔍 PostgreSQL Migration Validation"
echo "====================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counter
PASSED=0
FAILED=0

test_endpoint() {
    local name="$1"
    local method="$2"
    local endpoint="$3"
    local expected_status="$4"
    local data="$5"
    
    echo -n "Testing: $name... "
    
    if [ "$method" = "GET" ]; then
        response=$(curl -s -w "\n%{http_code}" -X GET "$BASE_URL$endpoint" \
            -H "Authorization: Bearer $ADMIN_TOKEN" \
            -H "Content-Type: application/json")
    elif [ "$method" = "POST" ]; then
        response=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL$endpoint" \
            -H "Authorization: Bearer $ADMIN_TOKEN" \
            -H "Content-Type: application/json" \
            -d "$data")
    elif [ "$method" = "PATCH" ]; then
        response=$(curl -s -w "\n%{http_code}" -X PATCH "$BASE_URL$endpoint" \
            -H "Authorization: Bearer $ADMIN_TOKEN" \
            -H "Content-Type: application/json" \
            -d "$data")
    elif [ "$method" = "DELETE" ]; then
        response=$(curl -s -w "\n%{http_code}" -X DELETE "$BASE_URL$endpoint" \
            -H "Authorization: Bearer $ADMIN_TOKEN")
    fi
    
    # Extract HTTP code (last line) and body (all but last line)
    http_code=$(echo "$response" | tail -1)
    body=$(echo "$response" | sed '$d')
    
    if [ "$http_code" = "$expected_status" ]; then
        echo -e "${GREEN}✓ PASS${NC} (HTTP $http_code)"
        ((PASSED++))
        return 0
    else
        echo -e "${RED}✗ FAIL${NC} (Expected $expected_status, got $http_code)"
        echo "  Response: $body"
        ((FAILED++))
        return 1
    fi
}

echo "1. Health Checks"
echo "----------------"
test_endpoint "Liveness probe" "GET" "/v1/health/live" "200"
test_endpoint "Database health" "GET" "/v1/health/db" "200"
test_endpoint "Readiness probe" "GET" "/v1/health/ready" "200"
echo ""

echo "2. List Tenants (Empty or Seeded)"
echo "----------------------------------"
test_endpoint "List all tenants" "GET" "/v1/admin/tenants" "200"
echo ""

echo "3. Create Tenant (Idempotency Test)"
echo "------------------------------------"
# Use timestamp for unique tenant name
TIMESTAMP=$(date +%s)
TENANT_DATA="{\"name\":\"Test Corp $TIMESTAMP\",\"admin_email\":\"test@example.com\",\"metadata\":{\"industry\":\"testing\"}}"
test_endpoint "Create tenant (first time)" "POST" "/v1/admin/tenants" "201" "$TENANT_DATA"
test_endpoint "Create tenant (idempotent)" "POST" "/v1/admin/tenants" "200" "$TENANT_DATA"
echo ""

echo "4. Get Specific Tenant"
echo "----------------------"
# Extract tenant ID from previous response (if available)
TENANT_ID=$(curl -s -X GET "$BASE_URL/v1/admin/tenants" \
    -H "Authorization: Bearer $ADMIN_TOKEN" | jq -r '.items[0].id // empty')

if [ -n "$TENANT_ID" ]; then
    test_endpoint "Get tenant by ID" "GET" "/v1/admin/tenants/$TENANT_ID" "200"
    
    echo ""
    echo "5. Update Tenant (JSONB Merge)"
    echo "-------------------------------"
    UPDATE_DATA='{"metadata":{"updated":true,"timestamp":"2025-01-01"}}'
    test_endpoint "Partial update tenant" "PATCH" "/v1/admin/tenants/$TENANT_ID" "200" "$UPDATE_DATA"
    
    echo ""
    echo "6. Conflict Detection"
    echo "---------------------"
    # Test conflict BEFORE deleting the tenant
    CONFLICT_DATA="{\"name\":\"Test Corp $TIMESTAMP\",\"admin_email\":\"different@example.com\",\"metadata\":{}}"
    test_endpoint "Create with conflicting email" "POST" "/v1/admin/tenants" "409" "$CONFLICT_DATA"
    
    echo ""
    echo "7. Delete Tenant"
    echo "----------------"
    test_endpoint "Delete tenant" "DELETE" "/v1/admin/tenants/$TENANT_ID" "204"
    test_endpoint "Delete non-existent tenant" "DELETE" "/v1/admin/tenants/$TENANT_ID" "404"
else
    echo -e "${YELLOW}⚠ Skipping get/update/delete tests (no tenants found)${NC}"
fi

echo ""
echo "8. Pagination Test"
echo "------------------"
test_endpoint "List with page_size=2" "GET" "/v1/admin/tenants?page_size=2" "200"
echo ""

echo "====================================="
echo "Test Summary"
echo "====================================="
echo -e "Passed: ${GREEN}$PASSED${NC}"
echo -e "Failed: ${RED}$FAILED${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ All tests passed! PostgreSQL migration successful.${NC}"
    exit 0
else
    echo -e "${RED}❌ Some tests failed. Check logs above.${NC}"
    exit 1
fi
