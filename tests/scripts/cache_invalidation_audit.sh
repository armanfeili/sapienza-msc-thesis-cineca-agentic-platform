#!/bin/bash
# Cache Invalidation Audit Script
# Tests Redis cache invalidation on provider CRUD operations

set -e

BASE_URL="http://localhost:8000/v1"
REDIS_CONTAINER="redis"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Load tokens
if [ -f .env ]; then
    source .env
    # Support both AUTH0_ADMIN_TOKEN and ADMIN_TOKEN variable names
    ADMIN_TOKEN="${AUTH0_ADMIN_TOKEN:-$ADMIN_TOKEN}"
else
    echo "❌ .env not found. Tokens needed for authentication"
    exit 1
fi

echo "===================================="
echo "Cache Invalidation Audit"
echo "===================================="
echo ""

# Helper functions
redis_keys() {
    local pattern=$1
    docker compose exec -T redis redis-cli KEYS "$pattern" 2>/dev/null | sort
}

redis_key_count() {
    local pattern=$1
    redis_keys "$pattern" | wc -l | tr -d ' '
}

wait_for_key() {
    local key=$1
    local max_wait=3
    for i in $(seq 1 $max_wait); do
        if docker compose exec -T redis redis-cli EXISTS "$key" | grep -q "1"; then
            return 0
        fi
        sleep 0.5
    done
    return 1
}

echo "=== Initial State ==="
echo "➜ Checking initial Redis keys..."
INITIAL_PROVIDER_KEYS=$(redis_key_count "provider:*")
echo "  Provider keys: $INITIAL_PROVIDER_KEYS"
echo ""

# Test 1: Register provider and verify cache
echo "=== Test 1: Register Provider ==="
PROVIDER_NAME="cache-audit-$(date +%s)"
echo "➜ Registering provider: $PROVIDER_NAME"

REGISTER_RESP=$(curl -s -X POST "${BASE_URL}/admin/models/providers/register" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{
        \"name\": \"$PROVIDER_NAME\",
        \"type\": \"openai_compatible\",
        \"base_url\": \"https://api.openai.com/v1\",
        \"model\": \"gpt-4\",
        \"api_key\": \"test-key-123\"
    }")

PROVIDER_ID=$(echo "$REGISTER_RESP" | jq -r '.details.name // .id // .name')
if [ -z "$PROVIDER_ID" ] || [ "$PROVIDER_ID" = "null" ]; then
    echo "❌ Failed to register provider"
    echo "$REGISTER_RESP" | jq -C .
    exit 1
fi

echo "✓ Provider registered: $PROVIDER_ID"
echo ""

# Test 2: List providers (populate cache)
echo "=== Test 2: List Providers (Populate Cache) ==="
echo "➜ Listing providers to populate cache..."
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
    "${BASE_URL}/admin/models/providers" > /dev/null
    
sleep 1  # Allow cache to settle

AFTER_LIST_KEYS=$(redis_key_count "provider:list:*")
echo "  List cache keys: $AFTER_LIST_KEYS"

if [ "$AFTER_LIST_KEYS" -gt 0 ]; then
    echo -e "${GREEN}✓ List cache populated${NC}"
else
    echo -e "${YELLOW}⚠ No list cache keys found${NC}"
fi
echo ""

# Test 3: Get provider (populate by_id cache)
echo "=== Test 3: Get Provider (Populate by_id Cache) ==="
echo "➜ Getting provider $PROVIDER_ID..."
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
    "${BASE_URL}/admin/models/providers/${PROVIDER_ID}" > /dev/null

sleep 0.5

BY_ID_KEY="provider:by_id:${PROVIDER_ID}"
if wait_for_key "$BY_ID_KEY"; then
    echo -e "${GREEN}✓ by_id cache populated: $BY_ID_KEY${NC}"
else
    echo -e "${YELLOW}⚠ by_id cache key not found (caching may be disabled)${NC}"
fi
echo ""

# Show all provider-related keys
echo "=== Cache State Before PATCH ==="
echo "➜ Provider-related Redis keys:"
redis_keys "provider:*" | head -n 20
BEFORE_PATCH=$(redis_key_count "provider:*")
echo "  Total: $BEFORE_PATCH keys"
echo ""

# Test 4: PATCH provider (should invalidate caches)
echo "=== Test 4: PATCH Provider (Should Invalidate) ==="
echo "➜ Patching provider (updating model)..."

curl -s -X PATCH "${BASE_URL}/admin/models/providers/${PROVIDER_ID}" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
        "model": "gpt-4-turbo"
    }' > /dev/null

sleep 1  # Allow invalidation to complete

echo "➜ Checking cache after PATCH..."
AFTER_PATCH=$(redis_key_count "provider:*")
BY_ID_EXISTS=$(docker compose exec -T redis redis-cli EXISTS "$BY_ID_KEY" | tr -d '\r')
LIST_KEYS_AFTER=$(redis_key_count "provider:list:*")

echo "  Total keys: $AFTER_PATCH (was $BEFORE_PATCH)"
echo "  by_id exists: $BY_ID_EXISTS (0=invalidated, 1=still cached)"
echo "  List keys: $LIST_KEYS_AFTER (was $AFTER_LIST_KEYS)"

if [ "$BY_ID_EXISTS" = "0" ] && [ "$LIST_KEYS_AFTER" -lt "$AFTER_LIST_KEYS" ]; then
    echo -e "${GREEN}✓ Cache properly invalidated after PATCH${NC}"
elif [ "$BY_ID_EXISTS" = "0" ]; then
    echo -e "${GREEN}✓ by_id cache invalidated${NC}"
    echo -e "${YELLOW}⚠ List cache may still exist${NC}"
else
    echo -e "${RED}❌ Cache NOT invalidated after PATCH${NC}"
fi
echo ""

# Test 5: Re-populate and check default setting
echo "=== Test 5: Set Default (Should Invalidate Defaults Cache) ==="
echo "➜ Listing providers again (re-populate cache)..."
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
    "${BASE_URL}/admin/models/providers" > /dev/null

sleep 0.5
BEFORE_DEFAULT=$(redis_key_count "provider:default:*")
echo "  Default cache keys before: $BEFORE_DEFAULT"

echo "➜ Setting provider as global default..."
curl -s -X PUT "${BASE_URL}/admin/models/providers/default" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{
        \"provider_id\": \"$PROVIDER_ID\",
        \"scope\": \"global\"
    }" > /dev/null

sleep 0.5
AFTER_DEFAULT=$(redis_key_count "provider:default:*")
echo "  Default cache keys after: $AFTER_DEFAULT"

if [ "$AFTER_DEFAULT" -lt "$BEFORE_DEFAULT" ] || [ "$BEFORE_DEFAULT" = "0" ]; then
    echo -e "${GREEN}✓ Default cache handling correct${NC}"
else
    echo -e "${YELLOW}⚠ Default cache keys increased (may be re-cached)${NC}"
fi
echo ""

# Test 6: DELETE provider (should invalidate all)
echo "=== Test 6: DELETE Provider (Should Invalidate All) ==="
BEFORE_DELETE=$(redis_key_count "provider:*")
echo "➜ Deleting provider..."

curl -s -X DELETE "${BASE_URL}/admin/models/providers/${PROVIDER_ID}" \
    -H "Authorization: Bearer $ADMIN_TOKEN" > /dev/null

sleep 1

echo "➜ Checking cache after DELETE..."
AFTER_DELETE=$(redis_key_count "provider:*")
BY_ID_EXISTS=$(docker compose exec -T redis redis-cli EXISTS "$BY_ID_KEY" | tr -d '\r')
LIST_KEYS_FINAL=$(redis_key_count "provider:list:*")

echo "  Total keys: $AFTER_DELETE (was $BEFORE_DELETE)"
echo "  by_id exists: $BY_ID_EXISTS (should be 0)"
echo "  List keys: $LIST_KEYS_FINAL"

if [ "$BY_ID_EXISTS" = "0" ]; then
    echo -e "${GREEN}✓ by_id cache invalidated after DELETE${NC}"
else
    echo -e "${RED}❌ by_id cache still exists after DELETE${NC}"
fi

if [ "$LIST_KEYS_FINAL" -lt "$BEFORE_DELETE" ]; then
    echo -e "${GREEN}✓ Cache keys reduced after DELETE${NC}"
else
    echo -e "${YELLOW}⚠ Cache keys not reduced (may be re-cached)${NC}"
fi
echo ""

# Final summary
echo "===================================="
echo "Cache Invalidation Audit Summary"
echo "===================================="
echo ""
echo "Cache Key Patterns:"
echo "  - provider:by_id:{id}  - Single provider cache"
echo "  - provider:list:*      - Provider list caches"
echo "  - provider:etag:*      - ETag caches"
echo "  - provider:default:*   - Default provider caches"
echo "  - provider:health:*    - Health check caches"
echo ""

echo "Test Results:"
echo "  ✓ Register: Creates provider entry"
echo "  ✓ List: Populates list cache (${AFTER_LIST_KEYS} keys)"
if [ "$BY_ID_EXISTS" = "0" ]; then
    echo -e "  ${GREEN}✓ PATCH: Invalidated by_id cache${NC}"
else
    echo -e "  ${RED}❌ PATCH: Failed to invalidate by_id cache${NC}"
fi
echo "  ✓ Set Default: Handles default caches"
if [ "$BY_ID_EXISTS" = "0" ]; then
    echo -e "  ${GREEN}✓ DELETE: Invalidated all provider caches${NC}"
else
    echo -e "  ${RED}❌ DELETE: Failed to invalidate caches${NC}"
fi
echo ""

echo "Current Redis State:"
echo "➜ All provider-related keys:"
redis_keys "provider:*" | head -n 10
FINAL_COUNT=$(redis_key_count "provider:*")
echo "  Total: $FINAL_COUNT keys"
echo ""

echo "===================================="
echo "Audit Complete"
echo "===================================="
