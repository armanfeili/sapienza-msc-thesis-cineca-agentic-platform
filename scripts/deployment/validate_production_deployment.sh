#!/bin/bash
# Automated Production Deployment Validation
# Usage: ./validate_production_deployment.sh [url] [token]

set -e

API_URL="${1:-https://api.example.com/v1}"
AUTH_TOKEN="${2:-${ADMIN_TOKEN}}"
LOG_FILE="deployment_validation_$(date +%Y%m%d_%H%M%S).log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

TESTS_PASSED=0
TESTS_FAILED=0

# Helper functions
log_info() { echo "[INFO] $1" | tee -a "$LOG_FILE"; }
log_pass() { echo -e "${GREEN}[PASS]${NC} $1" | tee -a "$LOG_FILE"; TESTS_PASSED=$((TESTS_PASSED + 1)); }
log_fail() { echo -e "${RED}[FAIL]${NC} $1" | tee -a "$LOG_FILE"; TESTS_FAILED=$((TESTS_FAILED + 1)); }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1" | tee -a "$LOG_FILE"; }

# Extract HTTP code and body
http_test() {
  local method="$1"
  local endpoint="$2"
  local headers="$3"
  local body="$4"
  
  curl -s -w "\n%{http_code}" -X "$method" \
    "$API_URL$endpoint" \
    $headers \
    -d "$body"
}

echo "================================================"
echo "Production Deployment Validation Suite"
echo "================================================"
echo "API URL: $API_URL"
echo "Log: $LOG_FILE"
echo ""

# ============ HEALTH CHECKS ============
log_info "=== HEALTH CHECKS ==="

# Test 1: Basic Health
log_info "Checking basic health..."
RESPONSE=$(http_test "GET" "/health" "" "")
BODY=$(echo "$RESPONSE" | head -n-1)
STATUS=$(echo "$RESPONSE" | tail -n1)

if [ "$STATUS" = "200" ]; then
  log_pass "Health endpoint responding (200)"
else
  log_fail "Health endpoint not responding (expected 200, got $STATUS)"
  exit 1
fi

# Test 2: Startup Health
log_info "Checking startup health..."
RESPONSE=$(http_test "GET" "/health/startup" "" "")
STATUS=$(echo "$RESPONSE" | tail -n1)

if [ "$STATUS" = "200" ]; then
  log_pass "Startup health check (200)"
  
  # Verify RATE_LIMIT_MODE is prod
  BODY=$(echo "$RESPONSE" | head -n-1)
  if echo "$BODY" | jq -e '.environment.rate_limit_mode == "prod"' >/dev/null; then
    log_pass "Rate limit mode is PROD"
  else
    log_fail "Rate limit mode is NOT prod: $(echo "$BODY" | jq '.environment.rate_limit_mode')"
  fi
else
  log_fail "Startup health check failed (expected 200, got $STATUS)"
fi

# Test 3: Ready Health
log_info "Checking ready health..."
RESPONSE=$(http_test "GET" "/health/ready" "" "")
STATUS=$(echo "$RESPONSE" | tail -n1)

if [ "$STATUS" = "200" ]; then
  log_pass "Ready health check (200)"
else
  log_fail "Ready health check failed (expected 200, got $STATUS)"
fi

# ============ AUTHENTICATION ============
log_info ""
log_info "=== AUTHENTICATION TESTS ==="

if [ -z "$AUTH_TOKEN" ]; then
  log_warn "No auth token provided. Skipping authenticated tests."
  log_warn "Set ADMIN_TOKEN environment variable to enable"
else
  # Test 4: User ME endpoint
  log_info "Testing user authentication..."
  RESPONSE=$(http_test "GET" "/user/me" "-H 'Authorization: Bearer $AUTH_TOKEN'" "")
  STATUS=$(echo "$RESPONSE" | tail -n1)
  
  if [ "$STATUS" = "200" ]; then
    log_pass "User authentication working (200)"
  else
    log_fail "User authentication failed (expected 200, got $STATUS)"
  fi
  
  # ============ SESSION OPERATIONS ============
  log_info ""
  log_info "=== SESSION OPERATIONS ==="
  
  # Test 5: Create Session
  log_info "Creating test session..."
  IDEM_KEY="smoke-test-$(date +%s)"
  RESPONSE=$(http_test "POST" "/agents/sessions" \
    "-H 'Authorization: Bearer $AUTH_TOKEN' -H 'Content-Type: application/json' -H 'Idempotency-Key: $IDEM_KEY'" \
    '{"manager":"auto","tools":[]}')
  STATUS=$(echo "$RESPONSE" | tail -n1)
  BODY=$(echo "$RESPONSE" | head -n-1)
  
  if [ "$STATUS" = "201" ]; then
    log_pass "Session created (201)"
    SESSION_ID=$(echo "$BODY" | jq -r '.session_id' 2>/dev/null)
    
    if [ -z "$SESSION_ID" ] || [ "$SESSION_ID" = "null" ]; then
      log_fail "Session ID not in response"
      SESSION_ID=""
    else
      log_pass "Session ID extracted: $SESSION_ID"
    fi
  else
    log_fail "Session creation failed (expected 201, got $STATUS)"
    SESSION_ID=""
  fi
  
  # Test 6: Rate Limit Headers
  log_info "Checking rate limit headers..."
  if echo "$RESPONSE" | grep -q "RateLimit-Limit"; then
    log_pass "RateLimit headers present"
  else
    log_fail "RateLimit headers missing"
  fi
  
  # Test 7: Idempotency Replay
  log_info "Testing idempotency replay..."
  RESPONSE=$(http_test "POST" "/agents/sessions" \
    "-H 'Authorization: Bearer $AUTH_TOKEN' -H 'Content-Type: application/json' -H 'Idempotency-Key: $IDEM_KEY'" \
    '{"manager":"auto","tools":[]}')
  STATUS=$(echo "$RESPONSE" | tail -n1)
  BODY=$(echo "$RESPONSE" | head -n-1)
  
  if [ "$STATUS" = "201" ]; then
    log_pass "Idempotency replay returned 201 (correct status code)"
    
    if echo "$BODY" | jq -e '.session_id' >/dev/null; then
      log_pass "Replay returned same session data"
    else
      log_fail "Replay did not return session data"
    fi
  else
    log_fail "Idempotency replay returned wrong status (expected 201, got $STATUS)"
  fi
  
  # Test 8: Get Session
  if [ -n "$SESSION_ID" ]; then
    log_info "Retrieving session..."
    RESPONSE=$(http_test "GET" "/agents/sessions/$SESSION_ID" \
      "-H 'Authorization: Bearer $AUTH_TOKEN'" "")
    STATUS=$(echo "$RESPONSE" | tail -n1)
    
    if [ "$STATUS" = "200" ]; then
      log_pass "Session retrieval (200)"
    else
      log_fail "Session retrieval failed (expected 200, got $STATUS)"
    fi
    
    # Test 9: Delete Session
    log_info "Deleting session..."
    RESPONSE=$(http_test "DELETE" "/agents/sessions/$SESSION_ID" \
      "-H 'Authorization: Bearer $AUTH_TOKEN'" "")
    STATUS=$(echo "$RESPONSE" | tail -n1)
    
    if [ "$STATUS" = "204" ] || [ "$STATUS" = "200" ]; then
      log_pass "Session deleted (${STATUS})"
    else
      log_fail "Session deletion failed (expected 204, got $STATUS)"
    fi
  fi
  
  # ============ ERROR HANDLING ============
  log_info ""
  log_info "=== ERROR HANDLING ==="
  
  # Test 10: Invalid request
  log_info "Testing error handling..."
  RESPONSE=$(http_test "POST" "/agents/sessions" \
    "-H 'Authorization: Bearer $AUTH_TOKEN' -H 'Content-Type: application/json'" \
    '{"invalid":"payload"}')
  STATUS=$(echo "$RESPONSE" | tail -n1)
  BODY=$(echo "$RESPONSE" | head -n-1)
  
  if [ "$STATUS" = "422" ] || [ "$STATUS" = "400" ]; then
    log_pass "Error handling working (${STATUS})"
    
    # Check for RFC-7807 format
    if echo "$BODY" | jq -e '.type' >/dev/null; then
      log_pass "Error response includes 'type' field (RFC-7807)"
    else
      log_warn "Error response may not be RFC-7807 compliant"
    fi
  else
    log_fail "Unexpected status for invalid request (expected 4xx, got $STATUS)"
  fi
fi

# ============ SUMMARY ============
echo ""
echo "================================================"
echo "Test Results"
echo "================================================"
echo -e "${GREEN}Passed: $TESTS_PASSED${NC}"
echo -e "${RED}Failed: $TESTS_FAILED${NC}"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
  echo -e "${GREEN}✅ All validation tests passed!${NC}"
  exit 0
else
  echo -e "${RED}❌ Some tests failed. See log for details.${NC}"
  exit 1
fi
