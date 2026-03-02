#!/bin/bash

# Auth0 Configuration for Cineca Agentic Platform
AUTH0_DOMAIN="cineca.eu.auth0.com"
CLIENT_ID="kwkf1bGn2NmdKWzioZYkvtYM022dzb5C"
AUDIENCE="api://cineca-agentic-platform"

echo "🔐 Requesting Auth0 tokens with MODEL scopes..."
echo ""

# ========== ADMIN TOKEN ==========
echo "📋 ADMIN TOKEN (admin user with full access):"
echo "   Username: admin@cineca.local"
echo "   Scopes: user:me tools:invoke:all admin:all"
echo ""

read -s -p "Enter admin password: " ADMIN_PASSWORD
echo ""

ADMIN_RESPONSE=$(curl -s --request POST \
  --url "https://$AUTH0_DOMAIN/oauth/token" \
  --header 'content-type: application/json' \
  --data "{
    \"grant_type\": \"password\",
    \"username\": \"admin@cineca.local\",
    \"password\": \"$ADMIN_PASSWORD\",
    \"audience\": \"$AUDIENCE\",
    \"client_id\": \"$CLIENT_ID\",
    \"scope\": \"user:me tools:invoke:all admin:all\"
  }")

ADMIN_TOKEN=$(echo "$ADMIN_RESPONSE" | jq -r '.access_token // empty')

if [ -z "$ADMIN_TOKEN" ]; then
  echo "❌ Failed to get admin token:"
  echo "$ADMIN_RESPONSE" | jq '.'
  exit 1
else
  echo "✅ Admin token obtained!"
  echo ""
fi

# ========== USER TOKEN WITH MODEL SCOPES ==========
echo "📋 USER TOKEN (regular user with MODEL access):"
echo "   Username: user@cineca.local"
echo "   Scopes: user:me tools:invoke:basic models:read models:test models:defaults:read models:defaults:write:self"
echo ""

read -s -p "Enter user password: " USER_PASSWORD
echo ""

USER_RESPONSE=$(curl -s --request POST \
  --url "https://$AUTH0_DOMAIN/oauth/token" \
  --header 'content-type: application/json' \
  --data "{
    \"grant_type\": \"password\",
    \"username\": \"user@cineca.local\",
    \"password\": \"$USER_PASSWORD\",
    \"audience\": \"$AUDIENCE\",
    \"client_id\": \"$CLIENT_ID\",
    \"scope\": \"user:me tools:invoke:basic models:read models:test models:defaults:read models:defaults:write:self\"
  }")

USER_TOKEN=$(echo "$USER_RESPONSE" | jq -r '.access_token // empty')

if [ -z "$USER_TOKEN" ]; then
  echo "❌ Failed to get user token:"
  echo "$USER_RESPONSE" | jq '.'
  exit 1
else
  echo "✅ User token obtained!"
  echo ""
fi

# ========== OUTPUT ==========
echo ""
echo "════════════════════════════════════════════════════════════════"
echo "✅ SUCCESS! Copy these tokens:"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "export ADMIN_TOKEN=\"$ADMIN_TOKEN\""
echo ""
echo "export USER_TOKEN=\"$USER_TOKEN\""
echo ""
echo "════════════════════════════════════════════════════════════════"
echo ""

# Verify tokens
echo "🔍 Verifying tokens..."
echo ""

echo "ADMIN TOKEN claims:"
echo "$ADMIN_TOKEN" | cut -d'.' -f2 | base64 -d 2>/dev/null | jq '{sub, scope, exp}' || echo "$ADMIN_TOKEN" | cut -d'.' -f2 | base64 -D 2>/dev/null | jq '{sub, scope, exp}'
echo ""

echo "USER TOKEN claims:"
echo "$USER_TOKEN" | cut -d'.' -f2 | base64 -d 2>/dev/null | jq '{sub, scope, exp}' || echo "$USER_TOKEN" | cut -d'.' -f2 | base64 -D 2>/dev/null | jq '{sub, scope, exp}'
echo ""

echo "✅ Done! Use the export commands above to set your tokens."
