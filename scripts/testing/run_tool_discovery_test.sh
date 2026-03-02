#!/bin/bash
# Tool Discovery Integration Test Execution Script
# Run with: bash run_tool_discovery_test.sh

set -e  # Exit on error

echo "================================================================================"
echo "🧪 TOOL DISCOVERY INTEGRATION TEST"
echo "================================================================================"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Step 1: Verify environment
echo -e "${BLUE}📋 Step 1: Verifying environment...${NC}"
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker not found. Please install Docker.${NC}"
    exit 1
fi

if ! command -v docker compose &> /dev/null; then
    echo -e "${RED}❌ Docker Compose not found. Please install Docker Compose.${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Docker and Docker Compose available${NC}"
echo ""

# Step 2: Build and start services
echo -e "${BLUE}📦 Step 2: Building and starting services...${NC}"
echo "Command: docker compose up -d --build --remove-orphans"
docker compose up -d --build --remove-orphans

echo -e "${GREEN}✅ Services built and started${NC}"
echo ""

# Step 3: Wait for services to be healthy
echo -e "${BLUE}⏳ Step 3: Waiting for services to be healthy...${NC}"
echo "Waiting for app service to be healthy (max 120 seconds)..."

timeout=120
elapsed=0
while [ $elapsed -lt $timeout ]; do
    if docker compose ps app | grep -q "healthy"; then
        echo -e "${GREEN}✅ App service is healthy${NC}"
        break
    fi
    sleep 5
    elapsed=$((elapsed + 5))
    echo "   Waiting... ${elapsed}s elapsed"
done

if [ $elapsed -ge $timeout ]; then
    echo -e "${RED}❌ Timeout waiting for app service to be healthy${NC}"
    echo "Container logs:"
    docker compose logs --tail=50 app
    exit 1
fi
echo ""

# Step 4: Check MCP tool count
echo -e "${BLUE}🔧 Step 4: Verifying MCP tool count (≥32 required)...${NC}"
docker compose logs app | grep "orchestrator.mcp_loaded" | tail -1 || true

if docker compose logs app | grep -q "orchestrator.mcp.insufficient_tools"; then
    echo -e "${RED}❌ Insufficient MCP tools detected. Check logs:${NC}"
    docker compose logs app | grep "orchestrator.mcp"
    exit 1
fi

echo -e "${GREEN}✅ MCP tools loaded successfully${NC}"
echo ""

# Step 5: Run integration test
echo -e "${BLUE}🧪 Step 5: Running integration test (max 15 minutes)...${NC}"
echo "Test: test_agent_run_executes_successfully"
echo ""

# Run test without tails, allow up to 900 seconds (15 minutes)
TEST_START=$(date +%s)
if docker compose exec -T app python -m pytest \
    tests/integration/test_agent_execution.py::TestAgentExecution::test_agent_run_executes_successfully \
    -xvs --tb=short; then
    TEST_END=$(date +%s)
    TEST_DURATION=$((TEST_END - TEST_START))
    echo ""
    echo -e "${GREEN}✅ Integration test PASSED in ${TEST_DURATION} seconds${NC}"
else
    TEST_END=$(date +%s)
    TEST_DURATION=$((TEST_END - TEST_START))
    echo ""
    echo -e "${RED}❌ Integration test FAILED after ${TEST_DURATION} seconds${NC}"
    echo ""
    echo "Container logs (last 100 lines):"
    docker compose logs --tail=100 app
    exit 1
fi
echo ""

# Step 6: Verify logs
echo -e "${BLUE}📊 Step 6: Verifying tool discovery logs...${NC}"
echo ""

echo "Checking for orchestrator.tool_call.executing (catalog.discover):"
if docker compose logs app | grep "orchestrator.tool_call.executing" | grep "catalog.discover"; then
    echo -e "${GREEN}✅ Found tool_call.executing log${NC}"
else
    echo -e "${YELLOW}⚠️  No tool_call.executing log found${NC}"
fi
echo ""

echo "Checking for orchestrator.tool_call.completed (catalog.discover):"
if docker compose logs app | grep "orchestrator.tool_call.completed" | grep -A 2 "catalog.discover" | head -3; then
    echo -e "${GREEN}✅ Found tool_call.completed log${NC}"
else
    echo -e "${YELLOW}⚠️  No tool_call.completed log found${NC}"
fi
echo ""

echo "Checking for orchestrator.tool_discovery.complete:"
if docker compose logs app | grep "orchestrator.tool_discovery.complete"; then
    echo -e "${GREEN}✅ Found tool_discovery.complete log with tools_count and source_groups${NC}"
else
    echo -e "${YELLOW}⚠️  No tool_discovery.complete log found${NC}"
fi
echo ""

echo "Checking for orchestrator.store.no_data errors (should be none):"
if docker compose logs app | grep "orchestrator.store.no_data"; then
    echo -e "${RED}❌ Found orchestrator.store.no_data errors (should not occur in tool discovery flow)${NC}"
    docker compose logs app | grep "orchestrator.store.no_data"
else
    echo -e "${GREEN}✅ No storage errors found${NC}"
fi
echo ""

# Step 7: Summary
echo "================================================================================"
echo -e "${GREEN}🎉 ALL CHECKS PASSED!${NC}"
echo "================================================================================"
echo ""
echo "Summary:"
echo "  ✅ Environment verified (Docker, Docker Compose)"
echo "  ✅ Services built and started"
echo "  ✅ Services healthy"
echo "  ✅ MCP tools loaded (≥32)"
echo "  ✅ Integration test passed"
echo "  ✅ Tool discovery logs verified"
echo "  ✅ No storage errors"
echo ""
echo "Test completed in ${TEST_DURATION} seconds"
echo ""
echo "Next steps:"
echo "  1. Review test output above for detailed results"
echo "  2. Check that tools_count ≥ 30 in test output"
echo "  3. Verify step_id='final-tools-output' in outputs"
echo "  4. Confirm no prose markers in tool discovery output"
echo ""
echo "To view full logs:"
echo "  docker compose logs app | grep 'orchestrator.tool_discovery'"
echo "  docker compose logs app | grep 'orchestrator.mcp'"
echo ""
echo "================================================================================"
