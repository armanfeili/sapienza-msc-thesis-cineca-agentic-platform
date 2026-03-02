#!/usr/bin/env bash
#
# User Flow Smoke Test
#
# Demonstrates typical user workflow:
# 1. Create job
# 2. List jobs
# 3. Get job status (with ETag)
# 4. Conditional GET (304 Not Modified)
# 5. Stream events via SSE (first 5 seconds)
# 6. Delete/cancel job
#
# Usage:
#   ./examples/user_flow_smoke.sh
#
# Prerequisites:
#   - API running at http://localhost:8000 (or set BASE_URL)
#   - Valid JWT token (or use mock OIDC dev mode)

set -euo pipefail

# Configuration
BASE_URL="${BASE_URL:-http://localhost:8000}"
TOKEN="${JWT_TOKEN:-}"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
log_step() {
    echo -e "${BLUE}>>> $1${NC}"
}

log_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

log_info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

# Check if jq is available
if ! command -v jq &> /dev/null; then
    echo "Error: jq is required but not installed. Install with: brew install jq"
    exit 1
fi

# Determine authentication method
if [ -z "$TOKEN" ]; then
    log_info "No JWT_TOKEN provided, using mock OIDC (dev mode)"
    AUTH_HEADER="Authorization: Bearer mock-user-token"
else
    AUTH_HEADER="Authorization: Bearer $TOKEN"
fi

echo "=================================================="
echo "User Flow Smoke Test"
echo "Base URL: $BASE_URL"
echo "=================================================="
echo

# Step 1: Create job
log_step "Step 1: Create job"
CREATE_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/jobs" \
    -H "Content-Type: application/json" \
    -H "$AUTH_HEADER" \
    -H "Idempotency-Key: smoke-test-$(date +%s)" \
    -d '{"type": "demo", "payload": {"duration_ms": 2000}}' \
    -w "\n%{http_code}")

HTTP_CODE=$(echo "$CREATE_RESPONSE" | tail -n1)
CREATE_BODY=$(echo "$CREATE_RESPONSE" | sed '$d')

if [ "$HTTP_CODE" -ne 202 ]; then
    echo "Error: Expected 202, got $HTTP_CODE"
    echo "Response: $CREATE_BODY"
    exit 1
fi

JOB_ID=$(echo "$CREATE_BODY" | jq -r '.id')
JOB_STATUS=$(echo "$CREATE_BODY" | jq -r '.status')
JOB_OWNER=$(echo "$CREATE_BODY" | jq -r '.owner')

log_success "Job created: $JOB_ID"
log_info "Status: $JOB_STATUS"
log_info "Owner: $JOB_OWNER"
echo

# Step 2: List jobs
log_step "Step 2: List jobs"
LIST_RESPONSE=$(curl -s "$BASE_URL/v1/jobs" \
    -H "$AUTH_HEADER" \
    -w "\n%{http_code}")

HTTP_CODE=$(echo "$LIST_RESPONSE" | tail -n1)
LIST_BODY=$(echo "$LIST_RESPONSE" | sed '$d')

if [ "$HTTP_CODE" -ne 200 ]; then
    echo "Error: Expected 200, got $HTTP_CODE"
    exit 1
fi

TOTAL_JOBS=$(echo "$LIST_BODY" | jq -r '.total')
HAS_MORE=$(echo "$LIST_BODY" | jq -r '.has_more')

log_success "Listed jobs: $TOTAL_JOBS total"
log_info "Has more pages: $HAS_MORE"
echo

# Step 3: Get job status (with ETag)
log_step "Step 3: Get job status (capture ETag)"
GET_RESPONSE=$(curl -s "$BASE_URL/v1/jobs/$JOB_ID" \
    -H "$AUTH_HEADER" \
    -D /dev/stderr \
    2>&1 | tee /tmp/smoke_headers.txt | tail -n1)

# Extract ETag from headers
ETAG=$(grep -i "^etag:" /tmp/smoke_headers.txt | cut -d: -f2- | tr -d '\r' | xargs)

JOB_STATUS=$(echo "$GET_RESPONSE" | jq -r '.status')

log_success "Job status: $JOB_STATUS"
log_info "ETag: $ETAG"
echo

# Step 4: Conditional GET (304 Not Modified)
log_step "Step 4: Conditional GET with If-None-Match"
CONDITIONAL_RESPONSE=$(curl -s -w "\n%{http_code}" "$BASE_URL/v1/jobs/$JOB_ID" \
    -H "$AUTH_HEADER" \
    -H "If-None-Match: $ETAG")

HTTP_CODE=$(echo "$CONDITIONAL_RESPONSE" | tail -n1)

if [ "$HTTP_CODE" -eq 304 ]; then
    log_success "Received 304 Not Modified (ETag matches)"
elif [ "$HTTP_CODE" -eq 200 ]; then
    log_info "Received 200 OK (job status changed, new ETag)"
else
    echo "Error: Expected 304 or 200, got $HTTP_CODE"
    exit 1
fi
echo

# Step 5: Stream SSE events (first 5 seconds)
log_step "Step 5: Stream SSE events (5 seconds)"
log_info "Listening to /v1/jobs/$JOB_ID/events..."

# Stream SSE in background, limit to 5 seconds
timeout 5 curl -s "$BASE_URL/v1/jobs/$JOB_ID/events" \
    -H "$AUTH_HEADER" \
    -H "Accept: text/event-stream" \
    --no-buffer 2>/dev/null | while IFS= read -r line; do
    if [[ "$line" == data:* ]]; then
        EVENT_DATA=$(echo "$line" | cut -d: -f2- | xargs)
        echo "  Event: $EVENT_DATA"
    fi
done || true

log_success "SSE stream closed"
echo

# Step 6: Delete/cancel job
log_step "Step 6: Delete/cancel job"
DELETE_RESPONSE=$(curl -s -X DELETE "$BASE_URL/v1/jobs/$JOB_ID" \
    -H "$AUTH_HEADER" \
    -w "\n%{http_code}")

HTTP_CODE=$(echo "$DELETE_RESPONSE" | tail -n1)
DELETE_BODY=$(echo "$DELETE_RESPONSE" | sed '$d')

if [ "$HTTP_CODE" -eq 202 ]; then
    log_success "Job cancelled (202 Accepted)"
elif [ "$HTTP_CODE" -eq 200 ]; then
    log_success "Job already terminal (200 OK)"
else
    echo "Error: Expected 202 or 200, got $HTTP_CODE"
    echo "Response: $DELETE_BODY"
    exit 1
fi

FINAL_STATUS=$(echo "$DELETE_BODY" | jq -r '.status')
log_info "Final status: $FINAL_STATUS"
echo

# Cleanup
rm -f /tmp/smoke_headers.txt

echo "=================================================="
echo -e "${GREEN}✓ All smoke test steps completed successfully!${NC}"
echo "=================================================="
