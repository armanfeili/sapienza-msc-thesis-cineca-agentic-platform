#!/bin/bash
# Generate Auth0 tokens for testing
# Usage: ./generate_auth0_tokens.sh

set -e

# Load credentials from consolidated .env file
if [ -f .env ]; then
    source .env
else
    echo "❌ Error: .env file not found"
    echo "Create it with AUTH0_* variables"
    exit 1
fi

echo "=== Generating Auth0 Tokens ==="
echo ""

# Function to get token
get_token() {
    local username=$1
    local password=$2
    local scope=$3
    local label=$4
    
    echo "➜ Fetching $label token..." >&2
    
    response=$(curl -s --request POST \
        --url "https://${AUTH0_DOMAIN}/oauth/token" \
        --header 'content-type: application/json' \
        --data "{
            \"grant_type\": \"http://auth0.com/oauth/grant-type/password-realm\",
            \"client_id\": \"${AUTH0_CLIENT_ID}\",
            \"client_secret\": \"${AUTH0_CLIENT_SECRET}\",
            \"audience\": \"${AUTH0_AUDIENCE}\",
            \"username\": \"${username}\",
            \"password\": \"${password}\",
            \"realm\": \"${AUTH0_REALM}\",
            \"scope\": \"${scope}\"
        }")
    
    # Check for errors
    if echo "$response" | grep -q "error"; then
        echo "❌ Error getting $label token:" >&2
        echo "$response" | jq -C '.' 2>/dev/null || echo "$response" >&2
        return 1
    fi
    
    # Extract access_token
    token=$(echo "$response" | jq -r '.access_token')
    
    if [ "$token" = "null" ] || [ -z "$token" ]; then
        echo "❌ Failed to extract token from response" >&2
        echo "$response" | jq -C '.' 2>/dev/null || echo "$response" >&2
        return 1
    fi
    
    echo "✓ $label token obtained" >&2
    echo "$token"
}

# Get Admin token
echo "=== Admin Token ==="
ADMIN_TOKEN=$(get_token "$ADMIN_USERNAME" "$ADMIN_PASSWORD" "$ADMIN_SCOPE" "Admin")
if [ $? -eq 0 ]; then
    echo ""
    echo "ADMIN_TOKEN=\"$ADMIN_TOKEN\""
    echo ""
fi

echo ""

# Get User token
echo "=== User Token ==="
USER_TOKEN=$(get_token "$USER_USERNAME" "$USER_PASSWORD" "$USER_SCOPE" "User")
if [ $? -eq 0 ]; then
    echo ""
    echo "USER_TOKEN=\"$USER_TOKEN\""
    echo ""
fi

# Save to consolidated .env file (append new tokens, removing old ones first)
if [ ! -z "$ADMIN_TOKEN" ] && [ ! -z "$USER_TOKEN" ]; then
    echo ""
    echo "=== Updating .env with fresh tokens ==="
    
    # Create backup
    cp .env .env.backup.$(date +%Y%m%d_%H%M%S)
    
    # Remove old token lines
    sed -i.tmp '/^AUTH0_ADMIN_TOKEN=/d' .env
    sed -i.tmp '/^AUTH0_USER_TOKEN=/d' .env
    sed -i.tmp '/^ADMIN_TOKEN=/d' .env
    sed -i.tmp '/^USER_TOKEN=/d' .env
    rm .env.tmp 2>/dev/null || true
    
    # Append new tokens
    cat >> .env << EOF

# Auth0 Tokens (generated $(date))
AUTH0_ADMIN_TOKEN=$ADMIN_TOKEN
AUTH0_USER_TOKEN=$USER_TOKEN
ADMIN_TOKEN=$ADMIN_TOKEN
USER_TOKEN=$USER_TOKEN
EOF
    echo "✓ Tokens saved to .env"
    echo ""
    echo "=== Usage ==="
    echo "source .env"
    echo "./smoke_test_providers_jobs.sh"
fi
