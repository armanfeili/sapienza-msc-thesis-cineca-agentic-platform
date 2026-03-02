#!/bin/bash
set -e

ADMIN_TOKEN=$(cat /tmp/admin_token.txt)
USER_TOKEN=$(cat /tmp/user_token.txt)

echo "=== FINAL SMOKE TEST: Model Instances API ==="
echo ""

echo "Test 1: List instances (admin)"
curl -s -X GET http://localhost:8000/v1/admin/models/instances \
  -H "Authorization: Bearer $ADMIN_TOKEN" -o /dev/null -w "  Status: %{http_code}\n"

echo "Test 2: Get default (admin)"
curl -s -X GET http://localhost:8000/v1/admin/models/defaults \
  -H "Authorization: Bearer $ADMIN_TOKEN" -o /dev/null -w "  Status: %{http_code}\n"

echo "Test 3: Get default (user, non-admin)"
curl -s -X GET http://localhost:8000/v1/admin/models/defaults \
  -H "Authorization: Bearer $USER_TOKEN" -o /dev/null -w "  Status: %{http_code}\n"

echo "Test 4: Set default (admin)"
curl -s -X PATCH http://localhost:8000/v1/admin/models/defaults \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"instance_id": "912d0ed3-ca7a-443f-969a-f1103beb4988"}' -o /dev/null -w "  Status: %{http_code}\n"

echo "Test 5: Test instance (admin)"
curl -s -X POST http://localhost:8000/v1/admin/models/instances/912d0ed3-ca7a-443f-969a-f1103beb4988/tests \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "test"}' -o /dev/null -w "  Status: %{http_code}\n"

echo "Test 6: Create instance (admin)"
INSTANCE_NAME="smoke-test-$(date +%s)"
curl -s -X POST http://localhost:8000/v1/admin/models/instances \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"provider_id\": \"smoke-test-1760297289\", \"instance_name\": \"$INSTANCE_NAME\", \"model_id\": \"gpt-4-test\"}" -o /dev/null -w "  Status: %{http_code}\n"

echo "Test 7: List without auth (expect 401)"
curl -s -X GET http://localhost:8000/v1/admin/models/instances -o /dev/null -w "  Status: %{http_code}\n"

echo ""
echo "=== SMOKE TEST COMPLETE ===" 
echo "All 7 tests should return expected status codes"
echo "Expected: 200, 200, 200, 200, 200, 201, 401"
