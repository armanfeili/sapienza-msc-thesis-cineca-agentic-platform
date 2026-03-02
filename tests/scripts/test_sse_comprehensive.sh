#!/bin/bash
echo "============================================"
echo "PostgreSQL SSE Endpoint Verification"
echo "============================================"

API="http://localhost:8000"

# Test 1: Basic SSE stream
echo -e "\n[Test 1] Creating job and streaming events..."
JOB_ID=$(curl -s "$API/v1/jobs" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type":"demo","agent_config":{"llm_model":"gpt-4"},"tool_ids":[],"tenant_id":"global"}' | jq -r '.id')

echo "Job ID: $JOB_ID"
echo -e "\nSSE Stream Output:"
perl -e 'alarm 8; exec @ARGV' curl -N -s -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$API/v1/jobs/$JOB_ID/events" 2>/dev/null | head -20 || true

# Test 2: Check events in database
echo -e "\n\n[Test 2] Verifying events in PostgreSQL..."
docker compose exec -T postgres psql -U cineca_user -d cineca_platform -c \
  "SELECT seq_id, event_type, created_at FROM job_events WHERE job_id = '$JOB_ID' ORDER BY seq_id;" 2>/dev/null || echo "Database check skipped"

# Test 3: Last-Event-ID resume
echo -e "\n[Test 3] Testing Last-Event-ID resume (from ID 15)..."
perl -e 'alarm 5; exec @ARGV' curl -N -s \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Last-Event-ID: 15" \
  "$API/v1/jobs/$JOB_ID/events" 2>/dev/null | head -15 || true

# Test 4: Cancel and watch for end event
echo -e "\n\n[Test 4] Cancelling job and watching for end event..."
JOB_ID2=$(curl -s "$API/v1/jobs" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type":"demo","agent_config":{"llm_model":"gpt-4"},"tool_ids":[],"tenant_id":"global"}' | jq -r '.id')

echo "New Job ID: $JOB_ID2"
echo "Streaming events (will cancel after 3 seconds)..."

# Start stream in background
(perl -e 'alarm 10; exec @ARGV' curl -N -s -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$API/v1/jobs/$JOB_ID2/events" 2>/dev/null | head -25) &
STREAM_PID=$!

# Cancel job after 3 seconds
sleep 3
echo -e "\n>>> Cancelling job now..."
curl -s -X DELETE "$API/v1/jobs/$JOB_ID2" -H "Authorization: Bearer $ADMIN_TOKEN" > /dev/null
wait $STREAM_PID 2>/dev/null || true

echo -e "\n\n============================================"
echo "✅ All SSE Tests Completed"
echo "============================================"
