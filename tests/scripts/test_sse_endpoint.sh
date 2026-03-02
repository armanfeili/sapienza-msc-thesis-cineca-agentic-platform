#!/bin/bash

# Test script for SSE (Server-Sent Events) endpoint with PostgreSQL backend
# Usage: ./test_sse_endpoint.sh

set -e

BASE_URL="http://localhost:8000"
TOKEN="${ADMIN_TOKEN:-}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Testing SSE Endpoint (PostgreSQL)${NC}"
echo -e "${BLUE}========================================${NC}\n"

# Check for token
if [ -z "$TOKEN" ]; then
    echo -e "${YELLOW}No ADMIN_TOKEN provided. Checking run/admin-token.txt...${NC}"
    if [ -f "run/admin-token.txt" ]; then
        TOKEN=$(cat run/admin-token.txt)
        echo -e "${GREEN}✓${NC} Using token from run/admin-token.txt\n"
    else
        echo -e "${RED}✗${NC} No token available. Please set ADMIN_TOKEN environment variable."
        exit 1
    fi
fi

# Step 1: Create a job
echo -e "${YELLOW}Step 1: Creating a test job...${NC}"
JOB_RESPONSE=$(curl -s -X POST "${BASE_URL}/v1/jobs" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: sse-test-$(date +%s)" \
  -d '{"type": "demo", "payload": {"test": "sse"}}')

JOB_ID=$(echo "$JOB_RESPONSE" | jq -r '.id')

if [ "$JOB_ID" = "null" ] || [ -z "$JOB_ID" ]; then
    echo -e "${RED}✗${NC} Failed to create job"
    echo "$JOB_RESPONSE" | jq
    exit 1
fi

echo -e "${GREEN}✓${NC} Created job: ${JOB_ID}\n"

# Step 2: Test SSE endpoint (listen for 10 seconds)
echo -e "${YELLOW}Step 2: Testing SSE endpoint (listening for 10 seconds)...${NC}"
echo -e "${BLUE}Events received:${NC}\n"

timeout 10s curl -N -H "Authorization: Bearer ${TOKEN}" \
  -H "Accept: text/event-stream" \
  "${BASE_URL}/v1/jobs/${JOB_ID}/events?retry_ms=2000" \
  2>/dev/null || true

echo -e "\n${GREEN}✓${NC} SSE stream completed\n"

# Step 3: Test Last-Event-ID resume
echo -e "${YELLOW}Step 3: Testing Last-Event-ID resume...${NC}"
timeout 5s curl -N -H "Authorization: Bearer ${TOKEN}" \
  -H "Accept: text/event-stream" \
  -H "Last-Event-ID: 0" \
  "${BASE_URL}/v1/jobs/${JOB_ID}/events?retry_ms=2000" \
  2>/dev/null | head -20 || true

echo -e "\n${GREEN}✓${NC} Resume test completed\n"

# Step 4: Cancel the job and watch for end event
echo -e "${YELLOW}Step 4: Cancelling job and watching for end event...${NC}"

# Cancel in background
(sleep 2 && curl -s -X DELETE "${BASE_URL}/v1/jobs/${JOB_ID}" \
  -H "Authorization: Bearer ${TOKEN}" > /dev/null) &

# Watch for end event
timeout 8s curl -N -H "Authorization: Bearer ${TOKEN}" \
  -H "Accept: text/event-stream" \
  "${BASE_URL}/v1/jobs/${JOB_ID}/events?retry_ms=1000" \
  2>/dev/null || true

echo -e "\n${GREEN}✓${NC} Cancel + end event test completed\n"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}All SSE tests completed!${NC}"
echo -e "${GREEN}========================================${NC}"
