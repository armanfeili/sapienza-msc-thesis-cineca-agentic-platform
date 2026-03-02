#!/bin/bash
# Run integration test inside Docker container (not on host)

set -e

# Get the project root directory
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

echo "🐳 Running integration test inside Docker container..."
echo "   This ensures the test runs in a Linux environment with proper resource allocation"
echo ""

# Step 1: Fetch Auth0 tokens on HOST (has access to .env)
echo "🔐 Fetching Auth0 tokens on host..."
TOKEN_OUTPUT=$(./scripts/fetch_auth0_tokens.sh 2>&1)

# Extract tokens from output (handle leading/trailing whitespace and quotes)
ADMIN_TOKEN=$(echo "$TOKEN_OUTPUT" | grep "AUTH0_ADMIN_TOKEN=" | sed "s/.*AUTH0_ADMIN_TOKEN='//g" | sed "s/'.*//g" | tr -d '[:space:]' | head -1)
USER_TOKEN=$(echo "$TOKEN_OUTPUT" | grep "AUTH0_USER_TOKEN=" | sed "s/.*AUTH0_USER_TOKEN='//g" | sed "s/'.*//g" | tr -d '[:space:]' | head -1)
MACHINE_TOKEN=$(echo "$TOKEN_OUTPUT" | grep "AUTH0_MACHINE_TOKEN=" | sed "s/.*AUTH0_MACHINE_TOKEN='//g" | sed "s/'.*//g" | tr -d '[:space:]' | head -1)

if [ -z "$ADMIN_TOKEN" ] || [ -z "$USER_TOKEN" ] || [ -z "$MACHINE_TOKEN" ]; then
    echo "❌ Failed to fetch Auth0 tokens"
    echo "Admin token length: ${#ADMIN_TOKEN}"
    echo "User token length: ${#USER_TOKEN}"
    echo "Machine token length: ${#MACHINE_TOKEN}"
    echo ""
    echo "Debug output:"
    echo "$TOKEN_OUTPUT"
    exit 1
fi

echo "✅ Auth0 tokens fetched successfully"
echo "   Admin token length: ${#ADMIN_TOKEN} chars"
echo "   User token length: ${#USER_TOKEN} chars"
echo "   Machine token length: ${#MACHINE_TOKEN} chars"
echo ""

# Step 2: Run pytest inside the app container with tokens as env vars
echo "🧪 Running integration test in Docker..."
docker compose exec -T \
    -e AUTH0_ADMIN_TOKEN="$ADMIN_TOKEN" \
    -e AUTH0_USER_TOKEN="$USER_TOKEN" \
    -e AUTH0_MACHINE_TOKEN="$MACHINE_TOKEN" \
    app python -m pytest \
    -v -s \
    tests/integration/test_agent_execution.py::TestAgentExecution::test_agent_run_executes_successfully \
    --tb=short \
    2>&1 | tee integration_test_docker.log

echo ""
echo "✅ Test completed. Check integration_test_docker.log for full output."
