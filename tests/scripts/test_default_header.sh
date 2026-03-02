#!/bin/bash
# Quick test to verify X-Tenant-Id header default behavior

set -e

echo "🧪 Testing Default X-Tenant-Id Header Behavior"
echo "=============================================="
echo

# Check if server is running
if ! curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "❌ Server not running at http://localhost:8000"
    echo "   Start server with: make dev"
    exit 1
fi

echo "✅ Server is running"
echo

# Test 1: POST tenant WITHOUT X-Tenant-Id header (should use default)
echo "📝 Test 1: POST /v1/admin/tenants WITHOUT X-Tenant-Id header"
echo "   (Should use default: tenant-admin-root)"

if [ -z "$ADMIN_TOKEN" ]; then
    echo "❌ ADMIN_TOKEN not set"
    echo "   Run: export ADMIN_TOKEN=<your-admin-token>"
    exit 1
fi

RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST http://localhost:8000/v1/admin/tenants \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"name":"TestTenant-'$(date +%s)'","admin_email":"test@example.com"}')

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | head -n -1)

if [ "$HTTP_CODE" = "201" ]; then
    echo "✅ POST succeeded with HTTP $HTTP_CODE"
    echo "   Response: $BODY"
else
    echo "❌ POST failed with HTTP $HTTP_CODE"
    echo "   Response: $BODY"
    exit 1
fi

echo
echo "🎉 All tests passed!"
echo
echo "Next steps:"
echo "1. Open Swagger UI: http://localhost:8000/docs"
echo "2. Expand POST /v1/admin/tenants"
echo "3. Click 'Try it out'"
echo "4. Verify X-Tenant-Id header is prefilled with 'tenant-admin-root'"
echo "5. Verify request body shows plain JSON examples"
echo "6. Click 'Execute' - should work without manual header entry!"
