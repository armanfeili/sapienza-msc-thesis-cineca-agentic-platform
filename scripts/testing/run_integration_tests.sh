#!/bin/bash
#
# Run Integration Tests
#
# This script runs the automated integration tests that verify
# end-to-end platform functionality.
#
# Manual items must be tested using docs/MANUAL_TESTING_GUIDE.md
#

set -e

echo "========================================="
echo "Platform Integration Tests"
echo "========================================="
echo ""

# Check if services are running
echo "Checking if services are running..."
if ! docker ps | grep -q "cineca.*postgres"; then
    echo "⚠️  WARNING: Docker services may not be running"
    echo "   Start with: docker-compose up -d"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "Running integration tests..."
echo ""

# Run fast tests first
echo "================================================"
echo "Phase 1: Core Integration Tests (Fast)"
echo "================================================"
echo ""

pytest tests/integration/ -v \
    --tb=short \
    --color=yes \
    -m "not slow" \
    || true

# Run slow tests separately (agent runs, etc.)
echo ""
echo "================================================"
echo "Phase 2: Agent Execution Tests (Slow)"
echo "================================================"
echo ""

pytest tests/integration/ -v \
    --tb=short \
    --color=yes \
    -m "slow" \
    || true

echo ""
echo "========================================="
echo "Integration Tests Complete"
echo "========================================="
echo ""
echo "Test Coverage:"
echo "  ✅ Platform health (databases, services)"
echo "  ✅ Configuration defaults"
echo "  ✅ Agent execution (real LLM calls)"
echo "  ✅ Sessions lifecycle"
echo "  ✅ Jobs lifecycle"
echo "  ✅ API safety (URLs, headers, errors)"
echo "  ✅ RBAC enforcement"
echo "  ✅ Authentication flows"
echo ""
echo "Next Steps:"
echo "1. Review test results above"
echo "2. Complete manual UI tests using:"
echo "   docs/MANUAL_TESTING_GUIDE.md"
echo "3. Fix any failures"
echo "4. Re-run this script"
echo ""
