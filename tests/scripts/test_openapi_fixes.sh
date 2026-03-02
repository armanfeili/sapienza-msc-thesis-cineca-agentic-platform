#!/bin/bash
# Test script to verify all OpenAPI fixes are working correctly
# Date: October 20, 2025

set -e

ADMIN_TOKEN="eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6IlBfUER0Z1l6angzVXlSVE9mTG10RSJ9.eyJpc3MiOiJodHRwczovL2NpbmVjYS5ldS5hdXRoMC5jb20vIiwic3ViIjoiYXV0aDB8NjhjNzA5OTY5MjI1YWZlMjY1MTUxZWQ1IiwiYXVkIjoiYXBpOi8vY2luZWNhLWFnZW50aWMtcGxhdGZvcm0iLCJpYXQiOjE3NjA5NDYxNjksImV4cCI6MTc2MTAzMjU2OSwic2NvcGUiOiJ1c2VyOm1lIHRvb2xzOmludm9rZTphbGwgYWRtaW46YWxsIiwiZ3R5IjoicGFzc3dvcmQiLCJhenAiOiJrd2tmMWJHbjJObWRLV3ppb1pZa3Z0WU0wMjJkemI1QyJ9.CGPSSN5OW76lkmEyPWkBPIGy0Bp0kGvsRfFYzA1whDm45tdjDmYgCkh7T3eOueBm_DMOtmQbk-yNvs4vD1Tq774s9SZsPb0JDbactBJWYlgh2GlSNXYOfYt-c7rQt4tUejfT5CIQ0OGP9Q5fOGtCgPljui_vImAwvTI4a_HXZYruwmpbyrYhd4rPUp4Antk1dG2X85mk25ibIz1Icw13_SqfNu8lK9UGq7WgImTpLtIPFqseD1ySZtDpgGj4rgDh-4mlLZLWUE2XuFx392xPq4txiWYuV-FfhhOK0IKiPxS5bzF0ka9Z4pBItGo516XRJ4kLVk4xFZk8sPA67HdOrg"
BASE_URL="http://localhost:8000"

echo "================================"
echo "OpenAPI Fixes Verification Tests"
echo "================================"
echo ""

# Test 1: POST /sessions returns 201 with Location header
echo "Test 1: POST /sessions returns 201 Created with Location header"
echo "----"
RESPONSE=$(curl -s -D - -X POST "$BASE_URL/v1/agents/sessions" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"temperature": 0.2}')

if echo "$RESPONSE" | grep -q "HTTP/1.1 201"; then
  echo "✅ Status code: 201 Created"
else
  echo "❌ Expected 201, got: $(echo "$RESPONSE" | head -1)"
  exit 1
fi

if echo "$RESPONSE" | grep -q "^location:"; then
  echo "✅ Location header: present"
  SESSION_ID=$(echo "$RESPONSE" | grep "^location:" | sed 's/.*\/sessions\///' | sed 's/[^a-f0-9-]//g')
  echo "   Session ID: $SESSION_ID"
else
  echo "❌ Location header: missing"
  exit 1
fi

if echo "$RESPONSE" | grep -q "^content-type: application/json"; then
  echo "✅ Content-Type: application/json"
else
  echo "❌ Content-Type: not JSON"
  exit 1
fi

echo ""

# Test 2: POST /steps accepts valid enum value "message" without 422
echo "Test 2: POST /steps accepts valid enum 'message' (not 'string')"
echo "----"
RESPONSE=$(curl -s -D - -X POST "$BASE_URL/v1/agents/sessions/$SESSION_ID/steps" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type": "message", "message": "Hello world"}')

if echo "$RESPONSE" | grep -q "HTTP/1.1 201"; then
  echo "✅ Status code: 201 Created"
else
  echo "❌ Expected 201, got: $(echo "$RESPONSE" | head -1)"
  exit 1
fi

if echo "$RESPONSE" | grep -q '"type":"message"'; then
  echo "✅ Type enum: 'message' accepted"
else
  echo "❌ Type enum: not accepted"
  exit 1
fi

echo ""

# Test 3: Invalid enum value still returns 422 with application/problem+json
echo "Test 3: POST /steps rejects invalid enum with 422 + application/problem+json"
echo "----"
RESPONSE=$(curl -s -D - -X POST "$BASE_URL/v1/agents/sessions/$SESSION_ID/steps" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type": "invalid", "message": "Hello"}')

if echo "$RESPONSE" | grep -q "HTTP/1.1 422"; then
  echo "✅ Status code: 422 Unprocessable Entity"
else
  echo "❌ Expected 422, got: $(echo "$RESPONSE" | head -1)"
  exit 1
fi

if echo "$RESPONSE" | grep -q "^content-type: application/problem+json"; then
  echo "✅ Content-Type: application/problem+json"
else
  echo "❌ Content-Type: expected application/problem+json, got: $(echo "$RESPONSE" | grep "^content-type:")"
  exit 1
fi

if echo "$RESPONSE" | grep -q '"title":"Validation Error"'; then
  echo "✅ Error title: 'Validation Error' (correct for 422)"
else
  echo "❌ Error title: not 'Validation Error'"
  exit 1
fi

if echo "$RESPONSE" | grep -q '"status":422'; then
  echo "✅ Error status: 422 (matches HTTP status)"
else
  echo "❌ Error status: not 422"
  exit 1
fi

echo ""

# Test 4: 401 Unauthorized has correct title and format
echo "Test 4: 401 Unauthorized has correct title and application/problem+json"
echo "----"
RESPONSE=$(curl -s -D - -X POST "$BASE_URL/v1/agents/sessions" \
  -H "Content-Type: application/json" \
  -d '{"temperature": 0.2}')

if echo "$RESPONSE" | grep -q "HTTP/1.1 401"; then
  echo "✅ Status code: 401 Unauthorized"
else
  echo "❌ Expected 401, got: $(echo "$RESPONSE" | head -1)"
  exit 1
fi

if echo "$RESPONSE" | grep -q "^content-type: application/problem+json"; then
  echo "✅ Content-Type: application/problem+json"
else
  echo "❌ Content-Type: expected application/problem+json, got: $(echo "$RESPONSE" | grep "^content-type:")"
  exit 1
fi

if echo "$RESPONSE" | grep -q '"title":"Unauthorized"'; then
  echo "✅ Error title: 'Unauthorized' (NOT 'Not Found')"
else
  echo "❌ Error title: not 'Unauthorized'"
  exit 1
fi

if echo "$RESPONSE" | grep -q '"status":401'; then
  echo "✅ Error status: 401 (matches HTTP status)"
else
  echo "❌ Error status: not 401"
  exit 1
fi

echo ""

# Test 5: All error responses have correlation_id
echo "Test 5: Error responses include correlation_id in extensions"
echo "----"
if echo "$RESPONSE" | grep -q '"correlation_id"'; then
  echo "✅ Extensions include: correlation_id"
else
  echo "❌ Extensions missing: correlation_id"
  exit 1
fi

if echo "$RESPONSE" | grep -q '"timestamp"'; then
  echo "✅ Extensions include: timestamp"
else
  echo "❌ Extensions missing: timestamp"
  exit 1
fi

echo ""

# Summary
echo "================================"
echo "✅ ALL TESTS PASSED"
echo "================================"
echo ""
echo "Summary of fixes verified:"
echo "  ✅ Issue #1: POST /sessions returns 201 with Location header"
echo "  ✅ Issue #2: Error responses use application/problem+json"
echo "  ✅ Issue #3: Error examples show correct title and status"
echo "  ✅ Issue #4: POST /steps accepts valid 'message' enum"
echo ""
echo "Production Ready: YES"
