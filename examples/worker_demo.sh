#!/bin/bash
#
# PostgreSQL Jobs Worker End-to-End Demonstration
# 
# This script demonstrates the complete worker functionality:
# 1. Create jobs via API
# 2. Worker picks up and executes jobs
# 3. Verify status transitions and results in PostgreSQL
# 4. Check SSE event logging
#

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== PostgreSQL Jobs Worker Demo ===${NC}\n"

# Check if admin token exists
if [ ! -f run/admin-token.txt ]; then
    echo -e "${YELLOW}⚠️  Admin token not found. Please run the setup first.${NC}"
    exit 1
fi

TOKEN=$(cat run/admin-token.txt)

echo -e "${GREEN}Step 1: Creating a test job (instant completion)${NC}"
echo "POST http://localhost:8000/v1/jobs"
echo '{"type": "test", "payload": {"message": "Hello Worker!"}}'
echo

TEST_RESP=$(docker compose exec -T app curl -s -X POST "http://localhost:8000/v1/jobs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type": "test", "payload": {"message": "Hello Worker!"}}')

TEST_JOB_ID=$(echo "$TEST_RESP" | docker compose exec -T app python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null)

if [ -z "$TEST_JOB_ID" ]; then
    echo -e "${YELLOW}❌ Failed to create test job${NC}"
    echo "$TEST_RESP"
    exit 1
fi

echo -e "✅ Created test job: ${GREEN}$TEST_JOB_ID${NC}\n"

echo -e "${BLUE}Waiting 2 seconds for worker to process...${NC}"
sleep 2

echo -e "\n${GREEN}Step 2: Checking test job status${NC}"
docker compose exec -T postgres psql -U cineca_user -d cineca_platform -c \
  "SELECT id, type, status, result_json::text as result FROM jobs WHERE id = '$TEST_JOB_ID'::uuid;"

echo -e "\n${GREEN}Step 3: Creating a demo job (3-second sleep)${NC}"
echo "POST http://localhost:8000/v1/jobs"
echo '{"type": "demo", "payload": {"duration_ms": 3000}}'
echo

DEMO_RESP=$(docker compose exec -T app curl -s -X POST "http://localhost:8000/v1/jobs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type": "demo", "payload": {"duration_ms": 3000}}')

DEMO_JOB_ID=$(echo "$DEMO_RESP" | docker compose exec -T app python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null)

if [ -z "$DEMO_JOB_ID" ]; then
    echo -e "${YELLOW}❌ Failed to create demo job${NC}"
    echo "$DEMO_RESP"
    exit 1
fi

echo -e "✅ Created demo job: ${GREEN}$DEMO_JOB_ID${NC}\n"

echo -e "${BLUE}Waiting 4 seconds for worker to process (job will sleep for 3s)...${NC}"
sleep 4

echo -e "\n${GREEN}Step 4: Checking demo job status${NC}"
docker compose exec -T postgres psql -U cineca_user -d cineca_platform -c \
  "SELECT id, type, status, result_json::text as result, created_at, started_at, completed_at FROM jobs WHERE id = '$DEMO_JOB_ID'::uuid;"

echo -e "\n${GREEN}Step 5: Checking job events (for SSE streaming)${NC}"
docker compose exec -T postgres psql -U cineca_user -d cineca_platform -c \
  "SELECT seq_id, event_type, LEFT(event_json::text, 60) as event_preview FROM job_events WHERE job_id IN ('$TEST_JOB_ID'::uuid, '$DEMO_JOB_ID'::uuid) ORDER BY job_id, seq_id;"

echo -e "\n${GREEN}Step 6: Checking worker logs${NC}"
docker compose logs worker --tail=15 | grep -E "Popped job|transitioned|completed"

echo -e "\n${GREEN}=== Demo Complete! ===${NC}"
echo -e "
Key Observations:
${GREEN}✅${NC} Jobs created via API are queued in PostgreSQL
${GREEN}✅${NC} Worker polls Redis queues and picks up jobs
${GREEN}✅${NC} Status transitions: queued → running → finished
${GREEN}✅${NC} Results stored in PostgreSQL (result_json column)
${GREEN}✅${NC} All transitions logged as events for SSE streaming
${GREEN}✅${NC} Worker handles different job types (test, demo)
${GREEN}✅${NC} Worker runs continuously in Docker Compose

To monitor worker in real-time:
  ${BLUE}docker compose logs -f worker${NC}

To create more jobs:
  ${BLUE}curl -X POST http://localhost:8000/v1/jobs \\
    -H \"Authorization: Bearer \$TOKEN\" \\
    -H \"Content-Type: application/json\" \\
    -d '{\"type\": \"demo\", \"payload\": {\"duration_ms\": 5000}}'${NC}
"
