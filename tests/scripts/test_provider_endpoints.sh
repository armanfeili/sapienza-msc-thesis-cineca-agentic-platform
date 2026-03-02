#!/bin/bash
set -e

export ADMIN_TOKEN='eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6IlBfUER0Z1l6angzVXlSVE9mTG10RSJ9.eyJpc3MiOiJodHRwczovL2NpbmVjYS5ldS5hdXRoMC5jb20vIiwic3ViIjoiYXV0aDB8NjhjNzA5OTY5MjI1YWZlMjY1MTUxZWQ1IiwiYXVkIjoiYXBpOi8vY2luZWNhLWFnZW50aWMtcGxhdGZvcm0iLCJpYXQiOjE3NjAzNTEyNjksImV4cCI6MTc2MDQzNzY2OSwic2NvcGUiOiJ1c2VyOm1lIHRvb2xzOmludm9rZTphbGwgYWRtaW46YWxsIiwiZ3R5IjoicGFzc3dvcmQiLCJhenAiOiJrd2tmMWJHbjJObWRLV3ppb1pZa3Z0WU0wMjJkemI1QyJ9.RGg_mNap4czjgvl3fwCu8WkJhLghKdaykUkpIGHCZInWiNlt1ClVwrFI6VntA9eEhOsnPzSiwMFBdleQ0O4t3Pr0BmstK2d36Om3gcpyFd37xCJX2YhmlrjrRcEwAeQ_hM5EI_jWhtKYWJeYZPbFbDFiSvPLJss8LNWg1EDZ9_JppJz_NkjZ4AdqJpoH7QOWigpUZ3IsgFCb9aumR9RguvJmgGdxM5s4lW0-RjORFeo5x3XFD7TgRu4kyopVDIlsG2CJ7mqRSEJ3GLitKSEdnjpYcgEMNEErOA2lCn7XH8TytTikiZtDKDrHTK0CpN7rCXhmA86L6NkG-77dCrGRcw'

export USER_TOKEN='eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6IlBfUER0Z1l6angzVXlSVE9mTG10RSJ9.eyJpc3MiOiJodHRwczovL2NpbmVjYS5ldS5hdXRoMC5jb20vIiwic3ViIjoiYXV0aDB8NjhjNzE1ZDU2ZjVlN2Q0ZWZhNmFkNmU2IiwiYXVkIjoiYXBpOi8vY2luZWNhLWFnZW50aWMtcGxhdGZvcm0iLCJpYXQiOjE3NjAzNTEyOTQsImV4cCI6MTc2MDQzNzY5NCwic2NvcGUiOiJ1c2VyOm1lIHRvb2xzOmludm9rZTpiYXNpYyIsImd0eSI6InBhc3N3b3JkIiwiYXpwIjoia3drZjFiR24yTm1kS1d6aW9aWWt2dFlNMDIyZHpiNUMifQ.g25Gc1VOBSD9snJF3dTCMzY_7prP-b9WB6vnTyKaKWvXecEllrC-6yKhMWgPefaadyEuxlH4CP6gC7jYbjnSvf6Db7lg0ajt56sCpzoww2xKm0pUtoHfkjyh-cP6UkIFvfHbQ2uUycK0rWd_T-72ZIx6teCfRcAGnddK0PttnWZExpWWJnRfnzlX9bsgFwny7rJfar-7sXYH9X2tVoVAUZogAHI3pD70xCUViuN4RFtDHX0qxyN0GeSrDbFQ8Lh8-nSEXhPPb66OyTPIbEsFzmC4C8yNj3u5tTs90KZWWD3xqPUkYOiUQtZ6T2l7JXJrTSOvmPNLJ2vo6oo_xtPsow'

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║       COMPREHENSIVE PROVIDER ENDPOINTS TEST                    ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

PASS=0
FAIL=0

# Test 1: List providers
echo "▶ Test 1: GET /v1/admin/models/providers (list)"
CODE=$(curl -s -X GET http://localhost:8000/v1/admin/models/providers \
  -H "Authorization: Bearer $ADMIN_TOKEN" -o /dev/null -w "%{http_code}")
if [ "$CODE" = "200" ]; then 
  echo "  ✅ PASS (200)"
  ((PASS++))
else 
  echo "  ❌ FAIL ($CODE)"
  ((FAIL++))
fi
echo ""

# Test 2: Register provider
echo "▶ Test 2: POST /v1/admin/models/providers/register"
PROVIDER_ID="comprehensive-test-$(date +%s)"
CODE=$(curl -s -X POST http://localhost:8000/v1/admin/models/providers/register \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"$PROVIDER_ID\", \"type\": \"openai_compatible\", \"base_url\": \"https://api.openai.com/v1\", \"model\": \"gpt-4\"}" -o /dev/null -w "%{http_code}")
if [ "$CODE" = "200" ]; then 
  echo "  ✅ PASS (200) - Provider ID: $PROVIDER_ID"
  ((PASS++))
else 
  echo "  ❌ FAIL ($CODE)"
  ((FAIL++))
fi
echo ""

# Test 3: Get provider by ID
echo "▶ Test 3: GET /v1/admin/models/providers/{id}"
CODE=$(curl -s -X GET http://localhost:8000/v1/admin/models/providers/$PROVIDER_ID \
  -H "Authorization: Bearer $ADMIN_TOKEN" -o /dev/null -w "%{http_code}")
if [ "$CODE" = "200" ]; then 
  echo "  ✅ PASS (200)"
  ((PASS++))
else 
  echo "  ❌ FAIL ($CODE)"
  ((FAIL++))
fi
echo ""

# Test 4: Get main provider
echo "▶ Test 4: GET /v1/admin/models/providers/main"
CODE=$(curl -s -X GET http://localhost:8000/v1/admin/models/providers/main \
  -H "Authorization: Bearer $ADMIN_TOKEN" -o /dev/null -w "%{http_code}")
if [ "$CODE" = "200" ] || [ "$CODE" = "404" ]; then 
  echo "  ✅ PASS ($CODE) - 404 is valid if no default set"
  ((PASS++))
else 
  echo "  ❌ FAIL ($CODE)"
  ((FAIL++))
fi
echo ""

# Test 5: PATCH provider
echo "▶ Test 5: PATCH /v1/admin/models/providers/{id}"
CODE=$(curl -s -X PATCH http://localhost:8000/v1/admin/models/providers/$PROVIDER_ID \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-4-turbo", "config": {"timeout": 60}}' -o /dev/null -w "%{http_code}")
if [ "$CODE" = "200" ]; then 
  echo "  ✅ PASS (200)"
  ((PASS++))
else 
  echo "  ❌ FAIL ($CODE)"
  ((FAIL++))
fi
echo ""

# Test 6: Set default provider
echo "▶ Test 6: PUT /v1/admin/models/providers/default"
CODE=$(curl -s -X PUT http://localhost:8000/v1/admin/models/providers/default \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"provider_id\": \"$PROVIDER_ID\"}" -o /dev/null -w "%{http_code}")
if [ "$CODE" = "200" ]; then 
  echo "  ✅ PASS (200)"
  ((PASS++))
else 
  echo "  ❌ FAIL ($CODE)"
  ((FAIL++))
fi
echo ""

# Test 7: DELETE provider
echo "▶ Test 7: DELETE /v1/admin/models/providers/{id}"
CODE=$(curl -s -X DELETE http://localhost:8000/v1/admin/models/providers/$PROVIDER_ID \
  -H "Authorization: Bearer $ADMIN_TOKEN" -o /dev/null -w "%{http_code}")
if [ "$CODE" = "204" ]; then 
  echo "  ✅ PASS (204)"
  ((PASS++))
else 
  echo "  ❌ FAIL ($CODE)"
  ((FAIL++))
fi
echo ""

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                      TEST SUMMARY                              ║"
echo "╠════════════════════════════════════════════════════════════════╣"
echo "║  Total Tests:    7                                             ║"
echo "║  Passed:         $PASS                                             ║"
echo "║  Failed:         $FAIL                                             ║"
if [ $FAIL -eq 0 ]; then
echo "║  Status:         🎉 ALL TESTS PASSED                           ║"
else
echo "║  Status:         ⚠️  SOME TESTS FAILED                         ║"
fi
echo "╚════════════════════════════════════════════════════════════════╝"
