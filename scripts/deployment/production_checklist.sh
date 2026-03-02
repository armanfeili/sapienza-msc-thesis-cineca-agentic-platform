#!/bin/bash
# Production Readiness Checklist for Redis Job Store
# Run this script to validate all production features

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Redis Job Store: Production Readiness Checklist${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}\n"

# 1. Backend Toggle & Rollback
echo -e "${YELLOW}1. Backend Toggle & Rollback${NC}"
echo "   Testing backend switching (redis ↔ memory)..."
echo ""
echo "   📝 Manual Steps:"
echo "   - Set JOB_STORE_BACKEND=redis, restart, test POST/GET/DELETE"
echo "   - Set JOB_STORE_BACKEND=memory, restart, verify works"
echo "   - Switch back to redis, verify no data loss"
echo ""
read -p "   ✓ Completed backend toggle test? (y/n): " backend_test
if [[ "$backend_test" == "y" ]]; then
    echo -e "   ${GREEN}✅ Backend toggle verified${NC}\n"
else
    echo -e "   ${RED}❌ Backend toggle pending${NC}\n"
fi

# 2. Redis Durability
echo -e "${YELLOW}2. Redis Durability${NC}"
echo "   Checking Redis persistence configuration..."
redis-cli config get appendonly 2>/dev/null || echo "   ⚠️  Redis not running locally"
redis-cli config get save 2>/dev/null || echo ""
echo ""
echo "   📝 Recommended:"
echo "   - AOF: appendonly yes, appendfsync everysec"
echo "   - RDB: save 900 1 (snapshot every 15min if ≥1 change)"
echo ""
read -p "   ✓ Redis persistence configured? (y/n): " redis_durability
if [[ "$redis_durability" == "y" ]]; then
    echo -e "   ${GREEN}✅ Redis durability confirmed${NC}\n"
else
    echo -e "   ${RED}❌ Redis durability pending${NC}\n"
fi

# 3. TTL Sanity
echo -e "${YELLOW}3. TTL Sanity Checks${NC}"
echo "   Current TTL settings:"
grep -E "JOB_TTL_DAYS|IDEMPOTENCY_TTL_HOURS|SSE_RING_SIZE" .env 2>/dev/null || echo "   (using defaults)"
echo ""
echo "   📝 Expected:"
echo "   - Jobs auto-expire: ~10 days (JOB_TTL_DAYS=10)"
echo "   - Idempotency: ~24h (IDEMPOTENCY_TTL_HOURS=24)"
echo "   - Events roll: SSE_RING_SIZE=100 (or configured value)"
echo ""
read -p "   ✓ TTL settings verified? (y/n): " ttl_test
if [[ "$ttl_test" == "y" ]]; then
    echo -e "   ${GREEN}✅ TTL sanity confirmed${NC}\n"
else
    echo -e "   ${RED}❌ TTL sanity pending${NC}\n"
fi

# 4. Atomic Cancel Under Load
echo -e "${YELLOW}4. Atomic Cancel Under Load${NC}"
echo "   Running concurrent cancellation test..."
python3 tests/smoke_redis_production.py 2>/dev/null | grep -A2 "Atomic" || echo "   Run: python tests/smoke_redis_production.py"
echo ""
read -p "   ✓ Atomic cancel test passed? (y/n): " atomic_test
if [[ "$atomic_test" == "y" ]]; then
    echo -e "   ${GREEN}✅ Atomic cancellation verified${NC}\n"
else
    echo -e "   ${RED}❌ Atomic cancellation pending${NC}\n"
fi

# 5. ETag Parity
echo -e "${YELLOW}5. ETag Parity Across Backends${NC}"
echo "   Testing If-None-Match behavior..."
echo ""
echo "   📝 Test:"
echo "   GET /v2/jobs/{id} → ETag: \"xyz\""
echo "   GET /v2/jobs/{id} + If-None-Match: \"xyz\" → 304 Not Modified"
echo ""
read -p "   ✓ ETag parity verified in both backends? (y/n): " etag_test
if [[ "$etag_test" == "y" ]]; then
    echo -e "   ${GREEN}✅ ETag parity confirmed${NC}\n"
else
    echo -e "   ${RED}❌ ETag parity pending${NC}\n"
fi

# 6. Index Hygiene
echo -e "${YELLOW}6. Index Hygiene (Orphan Cleanup)${NC}"
echo "   Testing background maintenance task..."
echo ""
echo "   📝 Test Steps:"
echo "   1. redis-cli DEL job:{some-id}  # Delete HASH manually"
echo "   2. Wait for background cleanup (~1 hour or trigger manually)"
echo "   3. Verify ZSET member removed from jobs:all"
echo ""
read -p "   ✓ Index hygiene verified? (y/n): " hygiene_test
if [[ "$hygiene_test" == "y" ]]; then
    echo -e "   ${GREEN}✅ Index hygiene confirmed${NC}\n"
else
    echo -e "   ${RED}❌ Index hygiene pending${NC}\n"
fi

# 7. SSE Resilience
echo -e "${YELLOW}7. SSE Resilience${NC}"
echo "   Testing SSE stream behavior..."
echo ""
echo "   📝 Test:"
echo "   - Connect without Last-Event-ID → get all events"
echo "   - Kill client, reconnect with Last-Event-ID → resume from last"
echo "   - Verify monotonic IDs, no duplicated 'end' event"
echo ""
read -p "   ✓ SSE resilience verified? (y/n): " sse_test
if [[ "$sse_test" == "y" ]]; then
    echo -e "   ${GREEN}✅ SSE resilience confirmed${NC}\n"
else
    echo -e "   ${RED}❌ SSE resilience pending${NC}\n"
fi

# 8. Metrics & Alerts
echo -e "${YELLOW}8. Metrics & Alerts${NC}"
echo "   Checking Prometheus metrics..."
curl -s http://localhost:8000/metrics 2>/dev/null | grep -E "job_create_total|job_get_duration" | head -3 || echo "   ⚠️  /metrics not accessible"
echo ""
echo "   📝 Verify:"
echo "   - Counters tick: job_create_total, job_cancel_total"
echo "   - Histograms track: job_get_duration_seconds{quantile}"
echo "   - Fake Redis outage triggers: RedisConnectionErrors alert"
echo ""
read -p "   ✓ Metrics & alerts verified? (y/n): " metrics_test
if [[ "$metrics_test" == "y" ]]; then
    echo -e "   ${GREEN}✅ Metrics & alerts confirmed${NC}\n"
else
    echo -e "   ${RED}❌ Metrics & alerts pending${NC}\n"
fi

# 9. Security Pass
echo -e "${YELLOW}9. Security Enforcement${NC}"
echo "   Testing access control..."
echo ""
echo "   📝 Test:"
echo "   - /admin/* without admin:all → 403 Forbidden"
echo "   - Non-owner GET /jobs/{id} → 404 Not Found (anti-enum)"
echo ""
read -p "   ✓ Security enforcement verified? (y/n): " security_test
if [[ "$security_test" == "y" ]]; then
    echo -e "   ${GREEN}✅ Security pass confirmed${NC}\n"
else
    echo -e "   ${RED}❌ Security pass pending${NC}\n"
fi

# 10. Docs Discoverability
echo -e "${YELLOW}10. Documentation Discoverability${NC}"
echo "   Checking documentation links..."
echo ""
echo "   📝 Verify README.md contains:"
echo "   - Link to docs/redis-job-store-quickstart.md"
echo "   - Link to docs/redis-job-store-production.md"
echo "   - Link to docs/runbooks/redis-job-store.md (if exists)"
echo ""
grep -q "redis-job-store" README.md && echo "   ✓ Found redis-job-store references in README" || echo "   ⚠️  No redis-job-store links in README"
echo ""
read -p "   ✓ Documentation linked in README? (y/n): " docs_test
if [[ "$docs_test" == "y" ]]; then
    echo -e "   ${GREEN}✅ Docs discoverability confirmed${NC}\n"
else
    echo -e "   ${RED}❌ Docs discoverability pending${NC}\n"
fi

# Summary
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Checklist Summary${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}\n"

echo "Production Readiness Status:"
echo ""
echo "1. Backend Toggle & Rollback: ${backend_test}"
echo "2. Redis Durability: ${redis_durability}"
echo "3. TTL Sanity: ${ttl_test}"
echo "4. Atomic Cancel Under Load: ${atomic_test}"
echo "5. ETag Parity: ${etag_test}"
echo "6. Index Hygiene: ${hygiene_test}"
echo "7. SSE Resilience: ${sse_test}"
echo "8. Metrics & Alerts: ${metrics_test}"
echo "9. Security Pass: ${security_test}"
echo "10. Docs Discoverability: ${docs_test}"
echo ""

# Calculate score
score=0
[[ "$backend_test" == "y" ]] && ((score++))
[[ "$redis_durability" == "y" ]] && ((score++))
[[ "$ttl_test" == "y" ]] && ((score++))
[[ "$atomic_test" == "y" ]] && ((score++))
[[ "$etag_test" == "y" ]] && ((score++))
[[ "$hygiene_test" == "y" ]] && ((score++))
[[ "$sse_test" == "y" ]] && ((score++))
[[ "$metrics_test" == "y" ]] && ((score++))
[[ "$security_test" == "y" ]] && ((score++))
[[ "$docs_test" == "y" ]] && ((score++))

echo -e "${BLUE}Score: ${score}/10${NC}"

if [[ $score -eq 10 ]]; then
    echo -e "${GREEN}🚀 ALL CHECKS PASSED - PRODUCTION READY!${NC}"
elif [[ $score -ge 7 ]]; then
    echo -e "${YELLOW}⚠️  MOSTLY READY - Address remaining items${NC}"
else
    echo -e "${RED}❌ NOT READY - Complete checklist before production${NC}"
fi

echo ""
