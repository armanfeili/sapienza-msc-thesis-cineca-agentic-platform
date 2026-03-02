#!/bin/bash
#
# Comprehensive test to diagnose and fix the /v1/models/defaults permission issue
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}=============================================${NC}"
echo -e "${CYAN}  Permission Issue Diagnostic Test${NC}"
echo -e "${CYAN}=============================================${NC}"
echo ""

# Step 1: Fetch fresh admin token
echo -e "${BLUE}Step 1: Fetching fresh admin token from Auth0...${NC}"
echo ""

# Run the fetch script with --export flag
source ./scripts/fetch_auth0_tokens.sh --export 2>&1 | tail -20

if [ -z "$AUTH0_ADMIN_TOKEN" ]; then
    echo -e "${RED}ERROR: Failed to fetch admin token${NC}"
    echo "Please check your .env configuration and try again"
    exit 1
fi

echo ""
echo -e "${GREEN}✓ Admin token fetched successfully${NC}"
echo ""

# Step 2: Decode and analyze token
echo -e "${BLUE}Step 2: Decoding token to inspect claims...${NC}"
echo ""
python3 debug_token.py "$AUTH0_ADMIN_TOKEN"
echo ""

# Step 3: Test the /v1/auth/me endpoint
echo -e "${BLUE}Step 3: Testing /v1/auth/me endpoint (verifies token is valid)...${NC}"
echo ""

API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"

RESPONSE=$(curl -s -w "\n%{http_code}" -X GET "$API_BASE_URL/v1/auth/me" \
  -H "Authorization: Bearer $AUTH0_ADMIN_TOKEN" \
  -H "Content-Type: application/json")

HTTP_BODY=$(echo "$RESPONSE" | head -n -1)
HTTP_STATUS=$(echo "$RESPONSE" | tail -n 1)

echo "HTTP Status: $HTTP_STATUS"
echo "Response:"
echo "$HTTP_BODY" | python3 -m json.tool 2>/dev/null || echo "$HTTP_BODY"
echo ""

if [ "$HTTP_STATUS" != "200" ]; then
    echo -e "${RED}✗ ERROR: /v1/auth/me failed${NC}"
    echo "The token is not being accepted by the backend"
    echo "This indicates a token validation issue, not a permission issue"
    exit 1
else
    echo -e "${GREEN}✓ Token is valid and accepted by backend${NC}"
    
    # Extract permissions from response
    BACKEND_PERMS=$(echo "$HTTP_BODY" | python3 -c "import sys, json; data=json.load(sys.stdin); print(', '.join(data.get('permissions', [])))" 2>/dev/null || echo "unknown")
    echo -e "${YELLOW}Backend extracted permissions: $BACKEND_PERMS${NC}"
fi
echo ""

# Step 4: Test the /v1/models/defaults endpoint
echo -e "${BLUE}Step 4: Testing /v1/models/defaults (the failing endpoint)...${NC}"
echo ""

RESPONSE=$(curl -s -w "\n%{http_code}" -X GET "$API_BASE_URL/v1/models/defaults" \
  -H "Authorization: Bearer $AUTH0_ADMIN_TOKEN" \
  -H "Content-Type: application/json")

HTTP_BODY=$(echo "$RESPONSE" | head -n -1)
HTTP_STATUS=$(echo "$RESPONSE" | tail -n 1)

echo "HTTP Status: $HTTP_STATUS"
echo "Response:"
echo "$HTTP_BODY" | python3 -m json.tool 2>/dev/null || echo "$HTTP_BODY"
echo ""

if [ "$HTTP_STATUS" = "403" ]; then
    echo -e "${RED}✗ ERROR: Got 403 Forbidden${NC}"
    echo ""
    echo -e "${YELLOW}DIAGNOSIS:${NC}"
    echo "The token is valid (Step 3 passed) but the permission check is failing."
    echo ""
    echo "This means:"
    echo "  1. Token has scopes in the JWT ✓"
    echo "  2. Backend can validate the token ✓"
    echo "  3. get_current_user() extracts permissions: $BACKEND_PERMS"
    echo "  4. has_any_permission() is rejecting the request ✗"
    echo ""
    echo -e "${CYAN}LIKELY CAUSE:${NC}"
    echo "The permissions array is not being populated correctly in UserInfo"
    echo ""
    echo -e "${GREEN}SOLUTION:${NC}"
    echo "Check the backend logs for these debug messages:"
    echo "  - 'get_current_user: extracted permissions=...'"
    echo "  - 'has_any_permission check: user_perms=...'"
    echo ""
    echo "If user_perms is empty [], that's the problem!"
    
elif [ "$HTTP_STATUS" = "404" ]; then
    echo -e "${GREEN}✓ SUCCESS: Permission check passed!${NC}"
    echo -e "${YELLOW}Got 404 Not Found - No defaults configured yet${NC}"
    echo ""
    echo "The 403 error is FIXED! The 404 just means you need to set a default model."
    echo "Go to the Models tab and set a default model instance."
    
elif [ "$HTTP_STATUS" = "200" ]; then
    echo -e "${GREEN}✓ SUCCESS: Everything working perfectly!${NC}"
    echo "The endpoint is accessible and defaults are configured."
    
else
    echo -e "${YELLOW}Got unexpected status: $HTTP_STATUS${NC}"
fi

echo ""
echo -e "${CYAN}=============================================${NC}"
echo -e "${CYAN}  Test Complete${NC}"
echo -e "${CYAN}=============================================${NC}"
echo ""

if [ "$HTTP_STATUS" = "403" ]; then
    echo -e "${YELLOW}Next steps:${NC}"
    echo "1. Check backend logs for the debug messages I added"
    echo "2. Look for: 'get_current_user: extracted permissions=...'"
    echo "3. Share the output with me"
    exit 1
fi

