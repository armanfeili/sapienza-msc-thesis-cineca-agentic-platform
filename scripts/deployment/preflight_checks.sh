#!/bin/bash
# Pre-flight Checks for Tool Discovery Test
# Run with: bash preflight_checks.sh

set -e

echo "================================================================================"
echo "🚀 PRE-FLIGHT CHECKS - Tool Discovery Test"
echo "================================================================================"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Track overall status
ALL_CHECKS_PASSED=true

# Check 1: Build & Start Services
echo -e "${BLUE}📦 Check 1: Building and starting services...${NC}"
echo "Command: docker compose up -d --build --remove-orphans"
if docker compose up -d --build --remove-orphans; then
    echo -e "${GREEN}✅ Services built and started${NC}"
else
    echo -e "${RED}❌ Failed to build/start services${NC}"
    ALL_CHECKS_PASSED=false
fi
echo ""

# Wait for services to be ready
echo -e "${BLUE}⏳ Waiting for services to be healthy (max 120s)...${NC}"
timeout=120
elapsed=0
while [ $elapsed -lt $timeout ]; do
    if docker compose ps app 2>/dev/null | grep -q "healthy\|running"; then
        echo -e "${GREEN}✅ App service is ready${NC}"
        break
    fi
    sleep 5
    elapsed=$((elapsed + 5))
    if [ $((elapsed % 20)) -eq 0 ]; then
        echo "   Still waiting... ${elapsed}s elapsed"
    fi
done

if [ $elapsed -ge $timeout ]; then
    echo -e "${RED}❌ Timeout waiting for app service${NC}"
    ALL_CHECKS_PASSED=false
fi
echo ""

# Check 2: Auth0 Tokens Script
echo -e "${BLUE}🔐 Check 2: Auth0 tokens script...${NC}"
if [ -f "fetch_auth0_tokens.sh" ]; then
    if [ -x "fetch_auth0_tokens.sh" ]; then
        echo -e "${GREEN}✅ fetch_auth0_tokens.sh exists and is executable${NC}"
        echo "   Testing script with --export flag..."
        if bash fetch_auth0_tokens.sh --export > /dev/null 2>&1; then
            echo -e "${GREEN}✅ Script executes successfully${NC}"
        else
            echo -e "${YELLOW}⚠️  Script exists but may have issues (this is OK if Auth0 not configured)${NC}"
        fi
    else
        echo -e "${YELLOW}⚠️  fetch_auth0_tokens.sh exists but is not executable${NC}"
        echo "   Run: chmod +x fetch_auth0_tokens.sh"
    fi
else
    echo -e "${YELLOW}⚠️  fetch_auth0_tokens.sh not found (test fixture will skip token fetching)${NC}"
fi
echo ""

# Check 3: CPU-Only (No GPU assumptions)
echo -e "${BLUE}🖥️  Check 3: CPU-only verification...${NC}"
GPU_REFS=$(grep -r "CUDA\|cuda" src/ --include="*.py" 2>/dev/null | grep -v "HAS_GPU" | wc -l | tr -d ' ')
if [ "$GPU_REFS" -eq "0" ]; then
    echo -e "${GREEN}✅ No GPU dependencies found (CPU-only confirmed)${NC}"
else
    echo -e "${YELLOW}⚠️  Found $GPU_REFS GPU references (check if intentional)${NC}"
fi
echo ""

# Check 4: MCP Tools Loaded (≥32)
echo -e "${BLUE}🔧 Check 4: MCP tools loaded (≥32 required)...${NC}"
sleep 3  # Give orchestrator time to initialize
MCP_LOG=$(docker compose logs app 2>/dev/null | grep "orchestrator.mcp_loaded" | tail -1)
if [ -n "$MCP_LOG" ]; then
    echo "   Found: $MCP_LOG"
    TOOLS_COUNT=$(echo "$MCP_LOG" | grep -oE "tools_registered[=:]?[[:space:]]*[0-9]+" | grep -oE "[0-9]+")
    if [ -n "$TOOLS_COUNT" ]; then
        if [ "$TOOLS_COUNT" -ge 32 ]; then
            echo -e "${GREEN}✅ MCP tools loaded: $TOOLS_COUNT (≥32 required)${NC}"
        else
            echo -e "${RED}❌ Insufficient MCP tools: $TOOLS_COUNT (need ≥32)${NC}"
            ALL_CHECKS_PASSED=false
        fi
    else
        echo -e "${YELLOW}⚠️  Could not parse tools count from log${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  orchestrator.mcp_loaded log not found yet (may still be starting)${NC}"
    echo "   Run manually: docker compose logs app | grep orchestrator.mcp_loaded"
fi
echo ""

# Check 5: Models Reachable (Ollama on CPU)
echo -e "${BLUE}🤖 Check 5: Ollama models reachable...${NC}"
OLLAMA_LOG=$(docker compose logs app 2>/dev/null | grep "ollama.probe.success\|model.loaded\|orchestrator.model.warmup" | tail -3)
if [ -n "$OLLAMA_LOG" ]; then
    echo "   Recent model logs:"
    echo "$OLLAMA_LOG" | head -3
    echo -e "${GREEN}✅ Ollama/model logs found${NC}"
else
    echo -e "${YELLOW}⚠️  No ollama.probe.success logs found yet${NC}"
    echo "   This is OK if models are still loading"
fi
echo ""

# Check 6: Intent Keyword in Test
echo -e "${BLUE}🔍 Check 6: Intent keyword in test...${NC}"
TEST_FILE="tests/integration/test_agent_execution.py"
if [ -f "$TEST_FILE" ]; then
    if grep -q "List the available tools you can use" "$TEST_FILE"; then
        echo -e "${GREEN}✅ Intent keyword found in test: 'List the available tools you can use.'${NC}"
    else
        echo -e "${RED}❌ Intent keyword not found in test${NC}"
        echo "   Expected prompt: 'List the available tools you can use.'"
        ALL_CHECKS_PASSED=false
    fi
else
    echo -e "${RED}❌ Test file not found: $TEST_FILE${NC}"
    ALL_CHECKS_PASSED=false
fi
echo ""

# Check 7: Script Permissions
echo -e "${BLUE}📝 Check 7: Test script permissions...${NC}"
if [ -f "run_tool_discovery_test.sh" ]; then
    if [ -x "run_tool_discovery_test.sh" ]; then
        echo -e "${GREEN}✅ run_tool_discovery_test.sh is executable${NC}"
    else
        echo -e "${YELLOW}⚠️  run_tool_discovery_test.sh is not executable${NC}"
        echo "   Run: chmod +x run_tool_discovery_test.sh"
        chmod +x run_tool_discovery_test.sh
        echo -e "${GREEN}✅ Fixed permissions${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  run_tool_discovery_test.sh not found (optional)${NC}"
fi
echo ""

# Summary
echo "================================================================================"
if [ "$ALL_CHECKS_PASSED" = true ]; then
    echo -e "${GREEN}🎉 ALL PRE-FLIGHT CHECKS PASSED!${NC}"
    echo ""
    echo "Ready to run test:"
    echo "  docker compose exec -T app python -m pytest \\"
    echo "    tests/integration/test_agent_execution.py::TestAgentExecution::test_agent_run_executes_successfully \\"
    echo "    -xvs --tb=short"
    echo ""
    echo "Or use automated script:"
    echo "  bash run_tool_discovery_test.sh"
else
    echo -e "${YELLOW}⚠️  SOME CHECKS FAILED OR INCOMPLETE${NC}"
    echo ""
    echo "Review the warnings above and fix any critical issues."
    echo "You may still proceed if only optional checks failed."
fi
echo "================================================================================"
echo ""

# Verification checklist
echo "After test completes, verify:"
echo "  1. Steps API has action='catalog.discover'"
echo "  2. Outputs API has step_id='final-tools-output' with:"
echo "     - tools_count ≥30"
echo "     - tools (array)"
echo "     - source_groups (e.g., ['mcp','llm'])"
echo "     - known_tools includes ≥2 of [agent.context, catalog.discover, graph.query]"
echo "  3. Logs show:"
echo "     - orchestrator.tool_call.executing for catalog.discover"
echo "     - orchestrator.tool_call.completed for catalog.discover"
echo "     - orchestrator.tool_discovery.complete with tools_count ≥30"
echo "     - NO orchestrator.store.no_data errors"
echo ""

exit 0
