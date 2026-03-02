#!/bin/bash
#
# Test the PostgreSQL-backed jobs worker
#
set -e

echo "============================================"
echo "Jobs Worker Test"
echo "============================================"
echo ""

# Test 1: Start worker in background for 20 seconds
echo "[Test 1] Starting worker for 20 seconds..."
docker compose exec -T app python -m src.workers.jobs_worker &
WORKER_PID=$!

echo "Worker PID: $WORKER_PID"
echo ""

# Give worker time to start
sleep 3

# Test 2: Create test jobs
echo "[Test 2] Creating test jobs..."

JOB1=$(curl -s http://localhost:8000/v1/jobs \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type":"demo","agent_config":{"llm_model":"gpt-4"},"tool_ids":[],"tenant_id":"global"}' | jq -r '.id')

echo "  ✓ Demo job: $JOB1"

JOB2=$(curl -s http://localhost:8000/v1/jobs \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type":"test","agent_config":{},"tool_ids":[],"tenant_id":"global"}' | jq -r '.id')

echo "  ✓ Test job: $JOB2"
echo ""

# Test 3: Wait for jobs to complete
echo "[Test 3] Waiting for jobs to complete (15 seconds)..."
sleep 15

# Test 4: Check job statuses
echo ""
echo "[Test 4] Checking job statuses..."
docker compose exec -T postgres psql -U cineca_user -d cineca_platform -c \
  "SELECT id, type, status, started_at IS NOT NULL as was_started, completed_at IS NOT NULL as was_completed 
   FROM jobs 
   WHERE id IN ('$JOB1', '$JOB2')
   ORDER BY created_at;"

echo ""
echo "[Test 5] Checking job events..."
docker compose exec -T postgres psql -U cineca_user -d cineca_platform -c \
  "SELECT job_id, seq_id, event_type, created_at 
   FROM job_events 
   WHERE job_id IN ('$JOB1', '$JOB2')
   ORDER BY job_id, seq_id 
   LIMIT 20;"

# Cleanup
echo ""
echo "Stopping worker..."
kill $WORKER_PID 2>/dev/null || true
wait $WORKER_PID 2>/dev/null || true

echo ""
echo "============================================"
echo "Worker test completed"
echo "============================================"
