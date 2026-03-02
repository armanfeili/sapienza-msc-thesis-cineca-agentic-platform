#!/bin/bash
# Test /v1/agent-runs endpoint behavior with polling support
# Usage: ./test_endpoint_behavior.sh [PROMPT] [ROLE]
# Examples:
#   ./test_endpoint_behavior.sh "How many :Blast nodes are there?" admin
#   ./test_endpoint_behavior.sh "hello" user
#   ./test_endpoint_behavior.sh  # Uses default prompt and admin role

set -e

echo "======================================================================"
echo "🔍 Testing /v1/agent-runs Endpoint Behavior (Async + Polling)"
echo "======================================================================"

# Parse arguments
PROMPT="${1:-hello}"
ROLE="${2:-admin}"

echo "📝 Prompt: $PROMPT"
echo "👤 Role: $ROLE"
echo ""

# Select token based on role
if [ "$ROLE" = "admin" ]; then
    if [ -z "$AUTH0_ADMIN_TOKEN" ]; then
        echo "❌ ERROR: AUTH0_ADMIN_TOKEN not set"
        echo "   Run: source .env or export AUTH0_ADMIN_TOKEN=..."
        exit 1
    fi
    TOKEN="$AUTH0_ADMIN_TOKEN"
    echo "🔐 Using AUTH0_ADMIN_TOKEN from environment"
elif [ "$ROLE" = "user" ]; then
    if [ -z "$AUTH0_USER_TOKEN" ]; then
        echo "❌ ERROR: AUTH0_USER_TOKEN not set"
        echo "   Run: source .env or export AUTH0_USER_TOKEN=..."
        exit 1
    fi
    TOKEN="$AUTH0_USER_TOKEN"
    echo "🔐 Using AUTH0_USER_TOKEN from environment"
else
    echo "❌ ERROR: Invalid ROLE: $ROLE"
    echo "   Must be 'admin' or 'user'"
    exit 1
fi

BASE_URL="${API_BASE_URL:-http://localhost:8000}"
echo "� Base URL: $BASE_URL"
echo ""

# Step 1: Create run (async endpoint - should return quickly)
echo "======================================================================"
echo "📝 Step 1: Create Agent Run (Async Endpoint)"
echo "======================================================================"
echo "   Expected: Returns quickly (< 1s) with status='queued'"
echo ""

START_TIME=$(date +%s)
echo "   🔄 Sending POST request..."

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/v1/agent-runs" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"prompt\": \"$PROMPT\"}" \
    --max-time 30 || echo "TIMEOUT")

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

if [ "$RESPONSE" = "TIMEOUT" ]; then
    echo "   ❌ Request timed out after 30s"
    echo "   🔍 This suggests the endpoint is BLOCKED or backend is hung"
    echo ""
    echo "   📋 Check backend logs:"
    echo "      docker compose logs app --tail=50 | grep -i 'agent_run\|error'"
    exit 1
fi

# Extract HTTP code (last line)
HTTP_CODE=$(echo "$RESPONSE" | tail -n 1)
BODY=$(echo "$RESPONSE" | sed '$d')

echo "   ✅ Response received after ${ELAPSED}s"
echo "   📊 HTTP Status: $HTTP_CODE"
echo ""

if [ "$HTTP_CODE" != "201" ]; then
    echo "   ❌ Unexpected status: $HTTP_CODE"
    echo "   📄 Response:"
    echo "$BODY"
    exit 1
fi

# Extract run_id and status
RUN_ID=$(echo "$BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('run_id', ''))" 2>/dev/null || echo "")
STATUS=$(echo "$BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', ''))" 2>/dev/null || echo "")

if [ -z "$RUN_ID" ]; then
    echo "   ❌ ERROR: No run_id in response"
    echo "   📄 Response:"
    echo "$BODY"
    exit 1
fi

echo "   ✅ Run created successfully"
echo "   📋 Run ID: $RUN_ID"
echo "   📊 Initial status: $STATUS"
echo ""

if [ "$STATUS" = "queued" ] || [ "$STATUS" = "running" ]; then
    echo "   ✅ Status is '$STATUS' - endpoint is ASYNC (as expected)"
elif [ "$STATUS" = "succeeded" ] || [ "$STATUS" = "failed" ]; then
    echo "   ⚠️  Status is '$STATUS' - orchestration already complete!"
    echo "   ℹ️  This is unusual - the endpoint should return status='queued'"
    echo "   ℹ️  Either orchestration was very fast or endpoint is still synchronous"
else
    echo "   ⚠️  Unknown status: $STATUS"
fi

# Step 2: Poll for completion
echo ""
echo "======================================================================"
echo "⏳ Step 2: Poll for Completion"
echo "======================================================================"
echo "   Max attempts: 300 (10 minutes with 2s intervals)"
echo "   You can Ctrl+C to stop polling"
echo ""

MAX_ATTEMPTS=300
ATTEMPT=0
LAST_STATUS="$STATUS"

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    ATTEMPT=$((ATTEMPT + 1))
    
    # Fetch current status
    STATUS_RESPONSE=$(curl -s -w "\n%{http_code}" -X GET "$BASE_URL/v1/agent-runs/$RUN_ID" \
        -H "Authorization: Bearer $TOKEN" \
        --max-time 10 || echo "ERROR")
    
    STATUS_HTTP=$(echo "$STATUS_RESPONSE" | tail -n 1)
    STATUS_BODY=$(echo "$STATUS_RESPONSE" | sed '$d')
    
    if [ "$STATUS_RESPONSE" = "ERROR" ] || [ "$STATUS_HTTP" != "200" ]; then
        echo "   ⚠️  [Attempt $ATTEMPT] Failed to fetch status: HTTP $STATUS_HTTP"
        sleep 2
        continue
    fi
    
    # Extract current status
    CURRENT_STATUS=$(echo "$STATUS_BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', ''))" 2>/dev/null || echo "")
    
    # Print update if status changed or every 10 attempts
    if [ "$CURRENT_STATUS" != "$LAST_STATUS" ] || [ $((ATTEMPT % 10)) -eq 0 ]; then
        ELAPSED=$((ATTEMPT * 2))
        echo "   📍 [${ELAPSED}s] Attempt $ATTEMPT: Status = $CURRENT_STATUS"
        LAST_STATUS="$CURRENT_STATUS"
    fi
    
    # Check for terminal status
    if [ "$CURRENT_STATUS" = "succeeded" ] || [ "$CURRENT_STATUS" = "failed" ] || [ "$CURRENT_STATUS" = "cancelled" ]; then
        echo ""
        echo "   🏁 Run finished: $CURRENT_STATUS (took ${ELAPSED}s, $ATTEMPT attempts)"
        
        # Step 3: Fetch steps
        echo ""
        echo "======================================================================"
        echo "📋 Step 3: Fetch Execution Steps"
        echo "======================================================================"
        
        STEPS_RESPONSE=$(curl -s -w "\n%{http_code}" -X GET "$BASE_URL/v1/agent-runs/$RUN_ID/steps" \
            -H "Authorization: Bearer $TOKEN" \
            --max-time 10 || echo "ERROR")
        
        STEPS_HTTP=$(echo "$STEPS_RESPONSE" | tail -n 1)
        STEPS_BODY=$(echo "$STEPS_RESPONSE" | sed '$d')
        
        if [ "$STEPS_HTTP" = "200" ]; then
            STEP_COUNT=$(echo "$STEPS_BODY" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
            echo "   ✅ Fetched $STEP_COUNT execution steps"
            
            # Show first 2 steps (truncated)
            echo ""
            echo "   📄 Steps (first 2, truncated):"
            echo "$STEPS_BODY" | python3 -c "
import sys, json
try:
    steps = json.load(sys.stdin)
    for i, step in enumerate(steps[:2]):
        action = step.get('action', 'unknown')
        step_id = step.get('step_id', 'unknown')
        print(f'      Step {i+1}: {step_id} - {action}')
        if 'input' in step:
            inp = str(step['input'])[:100]
            print(f'         Input: {inp}...')
        if 'output' in step:
            out = str(step['output'])[:100]
            print(f'         Output: {out}...')
except:
    pass
" || echo "      (Could not parse steps)"
        else
            echo "   ❌ Failed to fetch steps: HTTP $STEPS_HTTP"
        fi
        
        # Show final output
        echo ""
        echo "======================================================================"
        echo "📊 Final Status: $CURRENT_STATUS"
        echo "======================================================================"
        
        OUTPUT=$(echo "$STATUS_BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('output', 'None'))" 2>/dev/null || echo "None")
        echo "   Output: $OUTPUT" | head -c 300
        echo ""
        
        exit 0
    fi
    
    # Sleep before next attempt
    sleep 2
done

echo ""
echo "   ❌ TIMEOUT after $ATTEMPT attempts (${MAX_ATTEMPTS}s)"
echo "   Last status: $LAST_STATUS"
echo ""
echo "   📋 Troubleshooting:"
echo "      1. Check app logs: docker compose logs app --tail=100 | grep '$RUN_ID'"
echo "      2. Check Ollama: docker compose logs ollama --tail=50"
echo "      3. Try again with longer timeout or simpler prompt"

exit 1

echo ""
echo "======================================================================"
echo "✅ Test complete"
echo "======================================================================"
