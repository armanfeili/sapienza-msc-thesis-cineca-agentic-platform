#!/bin/bash
# Test RBAC for internal endpoints
# Expected outcomes:
#   - M2M token (internal:all) → HTTP 200 ✅
#   - ADMIN token (admin:all) → HTTP 403 ❌
#   - USER token (user:me) → HTTP 403 ❌

# Load fresh tokens from file
source /tmp/tokens.sh

URL="http://localhost:8000/v1/internal/ops/preview-staged"

echo "===== RBAC Testing for Internal Endpoints ====="
echo ""

echo "Test 1: M2M Token (internal:all) - SHOULD SUCCEED"
echo "-------------------------------------------------"
HTTP_CODE=$(curl -s -o /tmp/response1.json -w "%{http_code}" \
  -X GET "$URL" \
  -H "Authorization: Bearer $MACHINE_TOKEN")
echo "HTTP Status: $HTTP_CODE"
echo "Response:"
cat /tmp/response1.json | python3 -m json.tool 2>/dev/null || cat /tmp/response1.json
echo ""
echo ""

echo "Test 2: ADMIN Token (admin:all) - SHOULD FAIL WITH 403"
echo "-------------------------------------------------------"
HTTP_CODE=$(curl -s -o /tmp/response2.json -w "%{http_code}" \
  -X GET "$URL" \
  -H "Authorization: Bearer $ADMIN_TOKEN")
echo "HTTP Status: $HTTP_CODE"
echo "Response:"
cat /tmp/response2.json | python3 -m json.tool 2>/dev/null || cat /tmp/response2.json
echo ""
echo ""

echo "Test 3: USER Token (user:me) - SHOULD FAIL WITH 403"
echo "----------------------------------------------------"
HTTP_CODE=$(curl -s -o /tmp/response3.json -w "%{http_code}" \
  -X GET "$URL" \
  -H "Authorization: Bearer $USER_TOKEN")
echo "HTTP Status: $HTTP_CODE"
echo "Response:"
cat /tmp/response3.json | python3 -m json.tool 2>/dev/null || cat /tmp/response3.json
echo ""

echo "===== Test Summary ====="
echo "Expected results:"
echo "  Test 1: HTTP 200 ✅"
echo "  Test 2: HTTP 403 ❌ (admin:all explicitly rejected)"
echo "  Test 3: HTTP 403 ❌ (user:me explicitly rejected)"
