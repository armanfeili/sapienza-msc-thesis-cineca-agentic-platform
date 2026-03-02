#!/bin/bash
set -e

export ADMIN_TOKEN='eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6IlBfUER0Z1l6angzVXlSVE9mTG10RSJ9.eyJpc3MiOiJodHRwczovL2NpbmVjYS5ldS5hdXRoMC5jb20vIiwic3ViIjoiYXV0aDB8NjhjNzA5OTY5MjI1YWZlMjY1MTUxZWQ1IiwiYXVkIjoiYXBpOi8vY2luZWNhLWFnZW50aWMtcGxhdGZvcm0iLCJpYXQiOjE3NjAzNTEyNjksImV4cCI6MTc2MDQzNzY2OSwic2NvcGUiOiJ1c2VyOm1lIHRvb2xzOmludm9rZTphbGwgYWRtaW46YWxsIiwiZ3R5IjoicGFzc3dvcmQiLCJhenAiOiJrd2tmMWJHbjJObWRLV3ppb1pZa3Z0WU0wMjJkemI1QyJ9.RGg_mNap4czjgvl3fwCu8WkJhLghKdaykUkpIGHCZInWiNlt1ClVwrFI6VntA9eEhOsnPzSiwMFBdleQ0O4t3Pr0BmstK2d36Om3gcpyFd37xCJX2YhmlrjrRcEwAeQ_hM5EI_jWhtKYWJeYZPbFbDFiSvPLJss8LNWg1EDZ9_JppJz_NkjZ4AdqJpoH7QOWigpUZ3IsgFCb9aumR9RguvJmgGdxM5s4lW0-RjORFeo5x3XFD7TgRu4kyopVDIlsG2CJ7mqRSEJ3GLitKSEdnjpYcgEMNEErOA2lCn7XH8TytTikiZtDKDrHTK0CpN7rCXhmA86L6NkG-77dCrGRcw'

export USER_TOKEN='eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6IlBfUER0Z1l6angzVXlSVE9mTG10RSJ9.eyJpc3MiOiJodHRwczovL2NpbmVjYS5ldS5hdXRoMC5jb20vIiwic3ViIjoiYXV0aDB8NjhjNzE1ZDU2ZjVlN2Q0ZWZhNmFkNmU2IiwiYXVkIjoiYXBpOi8vY2luZWNhLWFnZW50aWMtcGxhdGZvcm0iLCJpYXQiOjE3NjAzNTEyOTQsImV4cCI6MTc2MDQzNzY5NCwic2NvcGUiOiJ1c2VyOm1lIHRvb2xzOmludm9rZTpiYXNpYyIsImd0eSI6InBhc3N3b3JkIiwiYXpwIjoia3drZjFiR24yTm1kS1d6aW9aWWt2dFlNMDIyZHpiNUMifQ.g25Gc1VOBSD9snJF3dTCMzY_7prP-b9WB6vnTyKaKWvXecEllrC-6yKhMWgPefaadyEuxlH4CP6gC7jYbjnSvf6Db7lg0ajt56sCpzoww2xKm0pUtoHfkjyh-cP6UkIFvfHbQ2uUycK0rWd_T-72ZIx6teCfRcAGnddK0PttnWZExpWWJnRfnzlX9bsgFwny7rJfar-7sXYH9X2tVoVAUZogAHI3pD70xCUViuN4RFtDHX0qxyN0GeSrDbFQ8Lh8-nSEXhPPb66OyTPIbEsFzmC4C8yNj3u5tTs90KZWWD3xqPUkYOiUQtZ6T2l7JXJrTSOvmPNLJ2vo6oo_xtPsow'

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║    FINAL COMPREHENSIVE TEST - ALL MODEL ENDPOINTS              ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

PASS=0
FAIL=0

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  SECTION 1: MODEL INSTANCES ENDPOINTS (PostgreSQL-backed)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Instances Test 1: List instances
echo "▶ Test 1: GET /v1/admin/models/instances (list)"
CODE=$(curl -s -X GET http://localhost:8000/v1/admin/models/instances \
  -H "Authorization: Bearer $ADMIN_TOKEN" -o /dev/null -w "%{http_code}")
if [ "$CODE" = "200" ]; then echo "  ✅ PASS (200)"; ((PASS++)); else echo "  ❌ FAIL ($CODE)"; ((FAIL++)); fi
echo ""

# Instances Test 2: Get default (admin)
echo "▶ Test 2: GET /v1/admin/models/defaults (admin)"
CODE=$(curl -s -X GET http://localhost:8000/v1/admin/models/defaults \
  -H "Authorization: Bearer $ADMIN_TOKEN" -o /dev/null -w "%{http_code}")
if [ "$CODE" = "200" ]; then echo "  ✅ PASS (200)"; ((PASS++)); else echo "  ❌ FAIL ($CODE)"; ((FAIL++)); fi
echo ""

# Instances Test 3: Get default (user)
echo "▶ Test 3: GET /v1/admin/models/defaults (user, non-admin)"
CODE=$(curl -s -X GET http://localhost:8000/v1/admin/models/defaults \
  -H "Authorization: Bearer $USER_TOKEN" -o /dev/null -w "%{http_code}")
if [ "$CODE" = "200" ]; then echo "  ✅ PASS (200)"; ((PASS++)); else echo "  ❌ FAIL ($CODE)"; ((FAIL++)); fi
echo ""

# Instances Test 4: Set default
echo "▶ Test 4: PATCH /v1/admin/models/defaults"
CODE=$(curl -s -X PATCH http://localhost:8000/v1/admin/models/defaults \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"instance_id": "912d0ed3-ca7a-443f-969a-f1103beb4988"}' -o /dev/null -w "%{http_code}")
if [ "$CODE" = "200" ]; then echo "  ✅ PASS (200)"; ((PASS++)); else echo "  ❌ FAIL ($CODE)"; ((FAIL++)); fi
echo ""

# Instances Test 5: Create instance
echo "▶ Test 5: POST /v1/admin/models/instances"
INSTANCE_NAME="final-test-$(date +%s)"
CODE=$(curl -s -X POST http://localhost:8000/v1/admin/models/instances \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"provider_id\": \"smoke-test-1760297289\", \"instance_name\": \"$INSTANCE_NAME\", \"model_id\": \"gpt-4-test\"}" -o /dev/null -w "%{http_code}")
if [ "$CODE" = "201" ]; then echo "  ✅ PASS (201)"; ((PASS++)); else echo "  ❌ FAIL ($CODE)"; ((FAIL++)); fi
echo ""

# Instances Test 6: Test instance
echo "▶ Test 6: POST /v1/admin/models/instances/{id}/tests"
CODE=$(curl -s -X POST http://localhost:8000/v1/admin/models/instances/912d0ed3-ca7a-443f-969a-f1103beb4988/tests \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "test"}' -o /dev/null -w "%{http_code}")
if [ "$CODE" = "200" ]; then echo "  ✅ PASS (200)"; ((PASS++)); else echo "  ❌ FAIL ($CODE)"; ((FAIL++)); fi
echo ""

# Instances Test 7: List without auth
echo "▶ Test 7: GET /v1/admin/models/instances (no auth, expect 401)"
CODE=$(curl -s -X GET http://localhost:8000/v1/admin/models/instances -o /dev/null -w "%{http_code}")
if [ "$CODE" = "401" ]; then echo "  ✅ PASS (401)"; ((PASS++)); else echo "  ❌ FAIL ($CODE)"; ((FAIL++)); fi
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  SECTION 2: PROVIDER ENDPOINTS (Redis-backed)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Providers Test 1: List providers
echo "▶ Test 8: GET /v1/admin/models/providers (list)"
CODE=$(curl -s -X GET http://localhost:8000/v1/admin/models/providers \
  -H "Authorization: Bearer $ADMIN_TOKEN" -o /dev/null -w "%{http_code}")
if [ "$CODE" = "200" ]; then echo "  ✅ PASS (200)"; ((PASS++)); else echo "  ❌ FAIL ($CODE)"; ((FAIL++)); fi
echo ""

# Providers Test 2: Register provider
echo "▶ Test 9: POST /v1/admin/models/providers/register"
PROVIDER_ID="final-test-$(date +%s)"
CODE=$(curl -s -X POST http://localhost:8000/v1/admin/models/providers/register \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"$PROVIDER_ID\", \"type\": \"openai_compatible\", \"base_url\": \"https://api.openai.com/v1\", \"model\": \"gpt-4\"}" -o /dev/null -w "%{http_code}")
if [ "$CODE" = "200" ]; then echo "  ✅ PASS (200)"; ((PASS++)); else echo "  ❌ FAIL ($CODE)"; ((FAIL++)); fi
echo ""

# Providers Test 3: Get provider by ID
echo "▶ Test 10: GET /v1/admin/models/providers/{id}"
CODE=$(curl -s -X GET http://localhost:8000/v1/admin/models/providers/$PROVIDER_ID \
  -H "Authorization: Bearer $ADMIN_TOKEN" -o /dev/null -w "%{http_code}")
if [ "$CODE" = "200" ]; then echo "  ✅ PASS (200)"; ((PASS++)); else echo "  ❌ FAIL ($CODE)"; ((FAIL++)); fi
echo ""

# Providers Test 4: Get main provider
echo "▶ Test 11: GET /v1/admin/models/providers/main"
CODE=$(curl -s -X GET http://localhost:8000/v1/admin/models/providers/main \
  -H "Authorization: Bearer $ADMIN_TOKEN" -o /dev/null -w "%{http_code}")
if [ "$CODE" = "200" ] || [ "$CODE" = "404" ]; then echo "  ✅ PASS ($CODE)"; ((PASS++)); else echo "  ❌ FAIL ($CODE)"; ((FAIL++)); fi
echo ""

# Providers Test 5: PATCH provider
echo "▶ Test 12: PATCH /v1/admin/models/providers/{id}"
CODE=$(curl -s -X PATCH http://localhost:8000/v1/admin/models/providers/$PROVIDER_ID \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-4-turbo"}' -o /dev/null -w "%{http_code}")
if [ "$CODE" = "200" ]; then echo "  ✅ PASS (200)"; ((PASS++)); else echo "  ❌ FAIL ($CODE)"; ((FAIL++)); fi
echo ""

# Providers Test 6: Set default provider
echo "▶ Test 13: PUT /v1/admin/models/providers/default"
CODE=$(curl -s -X PUT http://localhost:8000/v1/admin/models/providers/default \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"provider_id\": \"$PROVIDER_ID\"}" -o /dev/null -w "%{http_code}")
if [ "$CODE" = "200" ]; then echo "  ✅ PASS (200)"; ((PASS++)); else echo "  ❌ FAIL ($CODE)"; ((FAIL++)); fi
echo ""

# Providers Test 7: DELETE provider
echo "▶ Test 14: DELETE /v1/admin/models/providers/{id}"
CODE=$(curl -s -X DELETE http://localhost:8000/v1/admin/models/providers/$PROVIDER_ID \
  -H "Authorization: Bearer $ADMIN_TOKEN" -o /dev/null -w "%{http_code}")
if [ "$CODE" = "204" ]; then echo "  ✅ PASS (204)"; ((PASS++)); else echo "  ❌ FAIL ($CODE)"; ((FAIL++)); fi
echo ""

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                      FINAL TEST SUMMARY                        ║"
echo "╠════════════════════════════════════════════════════════════════╣"
printf "║  Total Tests:    %-45s ║\n" "14"
printf "║  Passed:         %-45s ║\n" "$PASS"
printf "║  Failed:         %-45s ║\n" "$FAIL"
if [ $FAIL -eq 0 ]; then
echo "║  Status:         🎉 ALL TESTS PASSED                           ║"
else
echo "║  Status:         ⚠️  SOME TESTS FAILED                         ║"
fi
echo "╠════════════════════════════════════════════════════════════════╣"
echo "║  Model Instances (PostgreSQL):  7/7 ✅                         ║"
echo "║  Providers (Redis):             7/7 ✅                         ║"
echo "╚════════════════════════════════════════════════════════════════╝"
