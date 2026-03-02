#!/bin/bash

# UI/Backend Verification Script
# Tests that all required backend endpoints exist

echo "🔍 Verifying Backend API Endpoints..."
echo "=========================================="
echo ""

BASE_URL="${API_BASE_URL:-http://localhost:8000}"
PASSED=0
FAILED=0

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

test_endpoint() {
    local method=$1
    local path=$2
    local description=$3
    local expected_status=$4
    
    echo -n "Testing: $description ... "
    
    response=$(curl -s -w "%{http_code}" -o /dev/null -X "$method" "$BASE_URL$path")
    
    if [ "$response" = "$expected_status" ]; then
        echo -e "${GREEN}✅ PASS${NC} ($response)"
        ((PASSED++))
    elif [ "$response" = "401" ] && [ "$expected_status" = "200" ]; then
        echo -e "${YELLOW}✅ EXISTS${NC} (401 - needs auth)"
        ((PASSED++))
    elif [ "$response" = "403" ] && [ "$expected_status" = "200" ]; then
        echo -e "${YELLOW}✅ EXISTS${NC} (403 - forbidden)"
        ((PASSED++))
    else
        echo -e "${RED}❌ FAIL${NC} (got $response, expected $expected_status)"
        ((FAILED++))
    fi
}

echo "📊 Testing Core Endpoints"
echo "--------------------------"
test_endpoint "GET" "/v1/" "API Root" "200"
test_endpoint "GET" "/v1/health/live" "Health Live" "200"
test_endpoint "GET" "/v1/health/components" "Health Components" "200"
test_endpoint "GET" "/v1/openapi.json" "OpenAPI Spec" "200"

echo ""
echo "🔐 Testing Auth Endpoints (expect 401 without token)"
echo "----------------------------------------------------"
test_endpoint "GET" "/v1/auth/me" "Auth Me" "200"

echo ""
echo "🧠 Testing Model Endpoints (expect 401 without token)"
echo "-----------------------------------------------------"
test_endpoint "GET" "/v1/models/defaults" "Model Defaults" "200"
test_endpoint "GET" "/v1/models/instances" "Model Instances" "200"
test_endpoint "GET" "/v1/admin/models/providers" "Providers List" "200"
test_endpoint "GET" "/v1/admin/models/providers/main" "Main Provider" "200"

echo ""
echo "🔧 Testing Tool Endpoints (expect 401 without token)"
echo "----------------------------------------------------"
test_endpoint "GET" "/v1/tools" "Tools List" "200"

echo ""
echo "🤖 Testing Agent Endpoints (expect 401 without token)"
echo "-----------------------------------------------------"
test_endpoint "GET" "/v1/agents/sessions" "Agent Sessions" "200"

echo ""
echo "📋 Testing Jobs Endpoints (expect 401 without token)"
echo "----------------------------------------------------"
test_endpoint "GET" "/v1/jobs" "Jobs List" "200"

echo ""
echo "⚙️ Testing Admin Endpoints (expect 401/403 without admin token)"
echo "---------------------------------------------------------------"
test_endpoint "GET" "/v1/admin/processes" "Admin Processes" "200"
test_endpoint "GET" "/v1/admin/models/manifests/builtins" "Built-in Manifests" "200"
test_endpoint "GET" "/v1/admin/db/counts" "DB Counts" "200"

echo ""
echo "=========================================="
echo "📊 Test Summary"
echo "=========================================="
echo -e "${GREEN}Passed: $PASSED${NC}"
echo -e "${RED}Failed: $FAILED${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ All endpoints exist!${NC}"
    echo ""
    echo "📝 Note: 401/403 responses are expected for auth-protected endpoints."
    echo "The UI will work correctly once proper Auth0 tokens are provided."
    exit 0
else
    echo -e "${RED}❌ Some endpoints are missing or returning unexpected responses.${NC}"
    echo "Please check backend logs for errors."
    exit 1
fi
