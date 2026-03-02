#!/bin/bash
# Deployment validation script - verifies deployment readiness
# Checks all critical functionality before going live

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
BASE_URL="${BASE_URL:-http://localhost:8000}"
ADMIN_TOKEN="${ADMIN_TOKEN:-}"
USER_TOKEN="${USER_TOKEN:-}"

# Counters
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0
WARNINGS=0

# Helper functions
check_pass() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
    ((PASSED_CHECKS++))
    ((TOTAL_CHECKS++))
}

check_fail() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    [ -n "$2" ] && echo "  └─ $2"
    ((FAILED_CHECKS++))
    ((TOTAL_CHECKS++))
}

check_warn() {
    echo -e "${YELLOW}⊘ WARN${NC}: $1"
    [ -n "$2" ] && echo "  └─ $2"
    ((WARNINGS++))
}

section() {
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════${NC}"
}

# Main execution
echo "========================================="
echo "Deployment Validation Script"
echo "========================================="
echo "Base URL: $BASE_URL"
echo "Timestamp: $(date -u +"%Y-%m-%d %H:%M:%S UTC")"
echo ""

# Section 1: Infrastructure Health
section "1. Infrastructure Health"

# Check Docker
if command -v docker &> /dev/null; then
    DOCKER_VERSION=$(docker --version | awk '{print $3}' | tr -d ',')
    check_pass "Docker installed (version $DOCKER_VERSION)"
else
    check_fail "Docker" "Docker not found"
fi

# Check Docker Compose
if command -v docker-compose &> /dev/null; then
    COMPOSE_VERSION=$(docker-compose --version | awk '{print $4}' | tr -d ',')
    check_pass "Docker Compose installed (version $COMPOSE_VERSION)"
else
    check_fail "Docker Compose" "docker-compose not found"
fi

# Check running containers
if docker-compose ps | grep -q "Up"; then
    RUNNING_CONTAINERS=$(docker-compose ps --services --filter "status=running" | wc -l)
    check_pass "Docker services running ($RUNNING_CONTAINERS services)"
else
    check_fail "Docker services" "No services running"
fi

# Section 2: API Health Checks
section "2. API Health Checks"

# Liveness check
LIVE_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/v1/health/live" 2>/dev/null || echo "000")
if [ "$LIVE_RESPONSE" = "200" ]; then
    check_pass "API liveness"
else
    check_fail "API liveness" "Expected 200, got $LIVE_RESPONSE"
fi

# Readiness check
READY_RESPONSE=$(curl -s -o /dev/null -w "%{http_CODE}" "$BASE_URL/v1/health/ready" 2>/dev/null || echo "000")
if [ "$READY_RESPONSE" = "200" ]; then
    check_pass "API readiness"
else
    check_fail "API readiness" "Expected 200, got $READY_RESPONSE"
fi

# Component health
COMPONENTS=$(curl -s "$BASE_URL/v1/health/components" 2>/dev/null || echo "")
if [ -n "$COMPONENTS" ]; then
    HEALTHY_COUNT=$(echo "$COMPONENTS" | grep -o '"status":"ok"' | wc -l)
    TOTAL_COUNT=$(echo "$COMPONENTS" | grep -o '"status":' | wc -l)
    
    if [ "$HEALTHY_COUNT" -eq "$TOTAL_COUNT" ]; then
        check_pass "Component health ($HEALTHY_COUNT/$TOTAL_COUNT healthy)"
    else
        check_fail "Component health" "$HEALTHY_COUNT/$TOTAL_COUNT healthy (expected all)"
    fi
else
    check_fail "Component health" "Failed to fetch components"
fi

# Section 3: Database Connectivity
section "3. Database Connectivity"

# PostgreSQL
PG_HEALTH=$(echo "$COMPONENTS" | grep -o '"postgresql":{[^}]*}' | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
if [ "$PG_HEALTH" = "ok" ]; then
    check_pass "PostgreSQL connectivity"
else
    check_fail "PostgreSQL connectivity" "Status: $PG_HEALTH"
fi

# Redis
REDIS_HEALTH=$(echo "$COMPONENTS" | grep -o '"redis":{[^}]*}' | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
if [ "$REDIS_HEALTH" = "ok" ]; then
    check_pass "Redis connectivity"
else
    check_fail "Redis connectivity" "Status: $REDIS_HEALTH"
fi

# Memgraph
MG_HEALTH=$(echo "$COMPONENTS" | grep -o '"memgraph":{[^}]*}' | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
if [ "$MG_HEALTH" = "ok" ]; then
    check_pass "Memgraph connectivity"
else
    check_fail "Memgraph connectivity" "Status: $MG_HEALTH"
fi

# Section 4: Model System
section "4. Model System"

# Check if Ollama is available
OLLAMA_HEALTH=$(echo "$COMPONENTS" | grep -o '"ollama":{[^}]*}' | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
if [ "$OLLAMA_HEALTH" = "ok" ]; then
    check_pass "Ollama provider connectivity"
else
    check_warn "Ollama provider" "Status: $OLLAMA_HEALTH (optional)"
fi

# Check model instances (requires auth)
if [ -n "$ADMIN_TOKEN" ]; then
    INSTANCES=$(curl -s -H "Authorization: Bearer $ADMIN_TOKEN" "$BASE_URL/v1/admin/models/instances" 2>/dev/null || echo "")
    if [ -n "$INSTANCES" ]; then
        INSTANCE_COUNT=$(echo "$INSTANCES" | grep -o '"id":' | wc -l)
        if [ "$INSTANCE_COUNT" -gt 0 ]; then
            check_pass "Model instances configured ($INSTANCE_COUNT instances)"
        else
            check_warn "Model instances" "No instances found (may need manual setup)"
        fi
    else
        check_warn "Model instances" "Could not fetch instances (auth may be required)"
    fi
else
    check_warn "Model instances" "Skipped (no admin token provided)"
fi

# Section 5: Authentication
section "5. Authentication"

# Check auth endpoint
AUTH_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/v1/auth/me" 2>/dev/null || echo "000")
if [ "$AUTH_RESPONSE" = "401" ]; then
    check_pass "Auth endpoint (401 for unauthenticated)"
elif [ "$AUTH_RESPONSE" = "200" ]; then
    check_pass "Auth endpoint (200 with valid token)"
else
    check_fail "Auth endpoint" "Unexpected response: $AUTH_RESPONSE"
fi

# Section 6: Tools API
section "6. Tools API"

# List tools (requires auth)
if [ -n "$USER_TOKEN" ] || [ -n "$ADMIN_TOKEN" ]; then
    TOKEN="${USER_TOKEN:-$ADMIN_TOKEN}"
    TOOLS=$(curl -s -H "Authorization: Bearer $TOKEN" "$BASE_URL/v1/tools" 2>/dev/null || echo "")
    if [ -n "$TOOLS" ]; then
        TOOL_COUNT=$(echo "$TOOLS" | grep -o '"name":' | wc -l)
        if [ "$TOOL_COUNT" -gt 0 ]; then
            check_pass "Tools API ($TOOL_COUNT tools available)"
        else
            check_fail "Tools API" "No tools found"
        fi
    else
        check_fail "Tools API" "Failed to fetch tools"
    fi
else
    check_warn "Tools API" "Skipped (no token provided)"
fi

# Section 7: Environment Configuration
section "7. Environment Configuration"

# Check .env file exists
if [ -f ".env" ] || [ -f ".env.production" ]; then
    check_pass "Environment configuration file present"
    
    # Check critical variables
    if [ -f ".env.production" ]; then
        ENV_FILE=".env.production"
    else
        ENV_FILE=".env"
    fi
    
    # JWT_SECRET
    if grep -q "JWT_SECRET=" "$ENV_FILE" && ! grep -q "JWT_SECRET=REPLACE_ME" "$ENV_FILE"; then
        check_pass "JWT_SECRET configured"
    else
        check_fail "JWT_SECRET" "Not configured or using default value"
    fi
    
    # DB_PASSWORD
    if grep -q "DB_PASSWORD=" "$ENV_FILE" && ! grep -q "DB_PASSWORD=change_me_now" "$ENV_FILE"; then
        check_pass "DB_PASSWORD configured"
    else
        check_fail "DB_PASSWORD" "Not configured or using default value"
    fi
else
    check_fail "Environment configuration" ".env or .env.production not found"
fi

# Section 8: Security Configuration
section "8. Security Configuration"

# Check security headers
HEADERS=$(curl -I -s "$BASE_URL/v1/health/ready" 2>/dev/null)

if echo "$HEADERS" | grep -qi "X-Frame-Options"; then
    check_pass "Security headers enabled"
else
    check_warn "Security headers" "X-Frame-Options not found"
fi

# Check if HTTPS is enforced (in production)
if [[ "$BASE_URL" == https://* ]]; then
    if echo "$HEADERS" | grep -qi "Strict-Transport-Security"; then
        check_pass "HSTS enabled"
    else
        check_fail "HSTS" "Strict-Transport-Security header missing"
    fi
else
    check_warn "HTTPS" "Not using HTTPS (expected in production)"
fi

# Section 9: File Structure
section "9. File Structure"

# Check critical files exist
CRITICAL_FILES=(
    "docker-compose.yml"
    "Dockerfile"
    "requirements.txt"
    "src/app.py"
    "src/config.py"
)

for file in "${CRITICAL_FILES[@]}"; do
    if [ -f "$file" ]; then
        check_pass "File exists: $file"
    else
        check_fail "File exists: $file" "File not found"
    fi
done

# Section 10: Documentation
section "10. Documentation"

# Check documentation files
DOC_FILES=(
    "README.md"
    "docs/PRODUCTION_DEPLOYMENT_GUIDE.md"
    "docs/GO_LIVE_REPORT_TEMPLATE.md"
)

for doc in "${DOC_FILES[@]}"; do
    if [ -f "$doc" ]; then
        check_pass "Documentation exists: $doc"
    else
        check_warn "Documentation" "$doc not found"
    fi
done

# Summary
echo ""
echo "========================================="
echo "Validation Summary"
echo "========================================="
echo -e "${BLUE}Total Checks: $TOTAL_CHECKS${NC}"
echo -e "${GREEN}Passed: $PASSED_CHECKS${NC}"
echo -e "${RED}Failed: $FAILED_CHECKS${NC}"
echo -e "${YELLOW}Warnings: $WARNINGS${NC}"
echo ""

# Calculate success rate
if [ $TOTAL_CHECKS -gt 0 ]; then
    SUCCESS_RATE=$((PASSED_CHECKS * 100 / TOTAL_CHECKS))
    echo "Success Rate: $SUCCESS_RATE%"
fi

# Final verdict
echo ""
if [ $FAILED_CHECKS -eq 0 ]; then
    echo -e "${GREEN}✓ DEPLOYMENT VALIDATION PASSED${NC}"
    echo "All critical checks passed. System is ready for deployment."
    exit 0
else
    echo -e "${RED}✗ DEPLOYMENT VALIDATION FAILED${NC}"
    echo "$FAILED_CHECKS critical check(s) failed. Please address issues before deploying."
    exit 1
fi

