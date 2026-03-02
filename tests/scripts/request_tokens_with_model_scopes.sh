#!/bin/bash

echo "🔐 Requesting Auth0 Tokens with Model Scopes..."
echo ""

# Admin token (unchanged - already has admin:all)
echo "📋 Requesting ADMIN TOKEN..."
ADMIN_RESPONSE=$(curl -s --request POST \
  --url https://cineca.eu.auth0.com/oauth/token \
  --header 'content-type: application/json' \
  --data '{
    "grant_type": "http://auth0.com/oauth/grant-type/password-realm",
    "client_id": "kwkf1bGn2NmdKWzioZYkvtYM022dzb5C",
    "client_secret": "z8Qf1DeYl-6fDKlGn5tpOuAshkjhiJmNrYkPibfBoR5vA5VC_7qznoavBN0rSZEB",
    "audience": "api://cineca-agentic-platform",
    "username": "admin@example.com",
    "password": "AdminPass123!",
    "realm": "Username-Password-Authentication",
    "scope": "user:me tools:invoke:all admin:all"
  }')

ADMIN_TOKEN=$(echo "$ADMIN_RESPONSE" | jq -r '.access_token // empty')

if [ -z "$ADMIN_TOKEN" ]; then
  echo "❌ Failed to get admin token:"
  echo "$ADMIN_RESPONSE" | jq '.'
else
  echo "✅ Admin token obtained!"
fi

echo ""

# User token WITH MODEL SCOPES
echo "📋 Requesting USER TOKEN with MODEL SCOPES..."
USER_RESPONSE=$(curl -s --request POST \
  --url https://cineca.eu.auth0.com/oauth/token \
  --header 'content-type: application/json' \
  --data '{
    "grant_type": "http://auth0.com/oauth/grant-type/password-realm",
    "client_id": "kwkf1bGn2NmdKWzioZYkvtYM022dzb5C",
    "client_secret": "z8Qf1DeYl-6fDKlGn5tpOuAshkjhiJmNrYkPibfBoR5vA5VC_7qznoavBN0rSZEB",
    "audience": "api://cineca-agentic-platform",
    "username": "user@example.com",
    "password": "UserPass123!",
    "realm": "Username-Password-Authentication",
    "scope": "user:me tools:invoke:basic models:read models:test models:defaults:read models:defaults:write:self"
  }')

USER_TOKEN=$(echo "$USER_RESPONSE" | jq -r '.access_token // empty')

if [ -z "$USER_TOKEN" ]; then
  echo "❌ Failed to get user token:"
  echo "$USER_RESPONSE" | jq '.'
  echo ""
  echo "⚠️  If Auth0 rejects the model scopes, you need to:"
  echo "   1. Go to Auth0 Dashboard → APIs → cineca-agentic-platform"
  echo "   2. Add the following scopes:"
  echo "      - models:read"
  echo "      - models:test"
  echo "      - models:defaults:read"
  echo "      - models:defaults:write:self"
  echo "   3. Assign these scopes to the user or make them default"
  echo "   4. Try again"
else
  echo "✅ User token obtained!"
fi

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "✅ Export these tokens:"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "export ADMIN_TOKEN=\"$ADMIN_TOKEN\""
echo ""
echo "export USER_TOKEN=\"$USER_TOKEN\""
echo ""
echo "════════════════════════════════════════════════════════════════"
echo ""

# Verify scopes
if [ -n "$USER_TOKEN" ]; then
  echo "🔍 Verifying USER_TOKEN scopes..."
  USER_PAYLOAD=$(echo "$USER_TOKEN" | cut -d'.' -f2)
  # Try both base64 commands (Linux and macOS)
  USER_CLAIMS=$(echo "$USER_PAYLOAD" | base64 -d 2>/dev/null || echo "$USER_PAYLOAD" | base64 -D 2>/dev/null)
  USER_SCOPE=$(echo "$USER_CLAIMS" | jq -r '.scope // "NONE"')
  echo "Scopes: $USER_SCOPE"
  echo ""
  
  # Check if required scopes are present
  if echo "$USER_SCOPE" | grep -q "models:read"; then
    echo "✅ Has models:read"
  else
    echo "❌ Missing models:read"
  fi
  
  if echo "$USER_SCOPE" | grep -q "models:test"; then
    echo "✅ Has models:test"
  else
    echo "❌ Missing models:test"
  fi
  
  if echo "$USER_SCOPE" | grep -q "models:defaults:read"; then
    echo "✅ Has models:defaults:read"
  else
    echo "❌ Missing models:defaults:read"
  fi
  
  if echo "$USER_SCOPE" | grep -q "models:defaults:write:self"; then
    echo "✅ Has models:defaults:write:self"
  else
    echo "❌ Missing models:defaults:write:self"
  fi
fi

echo ""
echo "✅ Done! Copy the export commands above."
