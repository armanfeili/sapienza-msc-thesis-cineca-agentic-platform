#!/bin/bash
# Verification script to ensure moved files still work correctly

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "🔍 Verifying File Reorganization"
echo "================================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

ERRORS=0

# Test 1: Check Python scripts can find project root
echo "📦 Test 1: Checking Python script path resolution..."
for script in scripts/debug/*.py; do
    if grep -q "from src\." "$script" 2>/dev/null; then
        if grep -q "sys.path.insert.*parent\.parent\.parent" "$script"; then
            echo -e "  ${GREEN}✓${NC} $(basename "$script") - path correctly set"
        else
            echo -e "  ${RED}✗${NC} $(basename "$script") - missing correct sys.path"
            ERRORS=$((ERRORS + 1))
        fi
    fi
done
echo ""

# Test 2: Check shell scripts reference correct paths
echo "🐚 Test 2: Checking shell script paths..."
if [ -f "scripts/testing/run_integration_test_in_docker.sh" ]; then
    if grep -q "./scripts/fetch_auth0_tokens.sh" "scripts/testing/run_integration_test_in_docker.sh"; then
        echo -e "  ${GREEN}✓${NC} run_integration_test_in_docker.sh uses correct path"
    else
        echo -e "  ${RED}✗${NC} run_integration_test_in_docker.sh has wrong path"
        ERRORS=$((ERRORS + 1))
    fi
fi

if [ -f "scripts/testing/test_permission_fix.sh" ]; then
    if grep -q "./scripts/fetch_auth0_tokens.sh" "scripts/testing/test_permission_fix.sh"; then
        echo -e "  ${GREEN}✓${NC} test_permission_fix.sh uses correct path"
    else
        echo -e "  ${RED}✗${NC} test_permission_fix.sh has wrong path"
        ERRORS=$((ERRORS + 1))
    fi
fi
echo ""

# Test 3: Verify key files exist in expected locations
echo "📂 Test 3: Checking file locations..."
files_to_check=(
    "scripts/fetch_auth0_tokens.sh"
    "scripts/fetch_tokens.py"
    "scripts/preflight_checks.sh"
    "scripts/debug/debug_agent_run.py"
    "scripts/debug/minimal_agent_test.py"
    "scripts/testing/run_integration_test_in_docker.sh"
    "docs/status-reports/archive"
    "docs/project-history/REORGANIZATION_2025_11_13.md"
    ".env_backups"
    "examples/test_batch.json"
    "db/redis/dump.rdb"
)

for file in "${files_to_check[@]}"; do
    if [ -e "$file" ]; then
        echo -e "  ${GREEN}✓${NC} $file exists"
    else
        echo -e "  ${YELLOW}⚠${NC} $file not found (may be optional)"
    fi
done
echo ""

# Test 4: Check root directory is clean
echo "🧹 Test 4: Checking root directory cleanliness..."
root_md_count=$(ls -1 *.md 2>/dev/null | grep -v "README\|CHANGELOG\|SECURITY\|LICENSE" | wc -l | tr -d ' ')
if [ "$root_md_count" -eq 0 ]; then
    echo -e "  ${GREEN}✓${NC} Root directory contains only essential .md files"
else
    echo -e "  ${YELLOW}⚠${NC} Found $root_md_count unexpected .md files in root"
    ls -1 *.md 2>/dev/null | grep -v "README\|CHANGELOG\|SECURITY\|LICENSE" | head -5
fi
echo ""

# Test 5: Verify scripts are executable
echo "🔧 Test 5: Checking script permissions..."
for script in scripts/*.sh scripts/testing/*.sh scripts/debug/*.py; do
    if [ -f "$script" ]; then
        if [ -x "$script" ]; then
            : # Silent success
        else
            echo -e "  ${YELLOW}⚠${NC} $(basename "$script") not executable"
        fi
    fi
done
echo -e "  ${GREEN}✓${NC} Script permissions checked"
echo ""

# Summary
echo "================================"
if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}✅ All verification tests passed!${NC}"
    exit 0
else
    echo -e "${RED}❌ Found $ERRORS error(s)${NC}"
    exit 1
fi
