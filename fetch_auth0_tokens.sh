#!/bin/bash
# Fetch fresh Auth0 tokens for testing the Cineca Agentic Platform
# 
# This script fetches three types of tokens from Auth0:
#   1. Admin Token (Password Realm Grant) - Full scopes: user:me, tools:invoke:all, admin:all
#   2. User Token (Password Realm Grant) - Basic scopes: user:me, tools:invoke:basic
#   3. Machine Token (Client Credentials) - Service-to-service token
#
# Usage:
#   ./fetch_auth0_tokens.sh                 # Display tokens in console
#   ./fetch_auth0_tokens.sh --save-to-env   # Save tokens to .env file
#   ./fetch_auth0_tokens.sh --export        # Export to current shell session
#
# Prerequisites:
#   - jq must be installed (brew install jq or apt install jq)
#   - Auth0 credentials must be set in .env file
#
# The script will read configuration from .env in the parent directory.

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Check for jq
if ! command -v jq &> /dev/null; then
    echo -e "${RED}ERROR: jq is not installed${NC}"
    echo "Please install jq:"
    echo "  macOS: brew install jq"
    echo "  Ubuntu/Debian: sudo apt-get install jq"
    echo "  RHEL/CentOS: sudo yum install jq"
    exit 1
fi

# Determine script directory and load .env
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
ENV_FILE="$PROJECT_ROOT/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}ERROR: .env file not found at $ENV_FILE${NC}"
    echo "Please create a .env file with Auth0 credentials"
    exit 1
fi

# Load environment variables (safer parsing to avoid command execution)
while IFS='=' read -r key value; do
    # Skip comments and empty lines
    [[ $key =~ ^#.*$ ]] && continue
    [[ -z $key ]] && continue
    # Remove leading/trailing whitespace
    key=$(echo "$key" | xargs)
    value=$(echo "$value" | xargs)
    # Export the variable
    export "$key=$value"
done < <(grep -v '^#' "$ENV_FILE" | grep -v '^$')

# Validate required configuration
MISSING_VARS=()
[ -z "$AUTH0_DOMAIN" ] && MISSING_VARS+=("AUTH0_DOMAIN")
[ -z "$AUTH0_AUDIENCE" ] && MISSING_VARS+=("AUTH0_AUDIENCE")
[ -z "$AUTH0_USER_CLIENT_ID" ] && MISSING_VARS+=("AUTH0_USER_CLIENT_ID")
[ -z "$AUTH0_USER_CLIENT_SECRET" ] && MISSING_VARS+=("AUTH0_USER_CLIENT_SECRET")
[ -z "$AUTH0_MACHINE_CLIENT_ID" ] && MISSING_VARS+=("AUTH0_MACHINE_CLIENT_ID")
[ -z "$AUTH0_MACHINE_CLIENT_SECRET" ] && MISSING_VARS+=("AUTH0_MACHINE_CLIENT_SECRET")
[ -z "$AUTH0_ADMIN_USERNAME" ] && MISSING_VARS+=("AUTH0_ADMIN_USERNAME")
[ -z "$AUTH0_ADMIN_PASSWORD" ] && MISSING_VARS+=("AUTH0_ADMIN_PASSWORD")
[ -z "$AUTH0_USER_USERNAME" ] && MISSING_VARS+=("AUTH0_USER_USERNAME")
[ -z "$AUTH0_USER_PASSWORD" ] && MISSING_VARS+=("AUTH0_USER_PASSWORD")

if [ ${#MISSING_VARS[@]} -ne 0 ]; then
    echo -e "${RED}ERROR: Missing required environment variables:${NC}"
    for var in "${MISSING_VARS[@]}"; do
        echo "  - $var"
    done
    echo ""
    echo "Please add these to your .env file"
    exit 1
fi

# Parse command line arguments
SAVE_TO_ENV=false
EXPORT_TO_SHELL=false
for arg in "$@"; do
    case $arg in
        --save-to-env)
            SAVE_TO_ENV=true
            ;;
        --export)
            EXPORT_TO_SHELL=true
            ;;
        *)
            echo -e "${RED}ERROR: Unknown argument: $arg${NC}"
            echo "Usage: $0 [--save-to-env] [--export]"
            exit 1
            ;;
    esac
done

echo ""
echo -e "${CYAN}=============================================${NC}"
echo -e "${CYAN}  Auth0 Token Fetcher - Cineca Platform${NC}"
echo -e "${CYAN}=============================================${NC}"
echo ""
echo -e "${BLUE}Configuration:${NC}"
echo "  Domain:   $AUTH0_DOMAIN"
echo "  Audience: $AUTH0_AUDIENCE"
echo ""

# Function to fetch token
fetch_token() {
    local token_type=$1
    local grant_type=$2
    local client_id=$3
    local client_secret=$4
    local username=$5
    local password=$6
    local scopes=$7
    
    echo -e "${YELLOW}Fetching $token_type token...${NC}" >&2
    
    local data
    if [ "$grant_type" = "password" ]; then
        data="{
            \"grant_type\": \"password\",
            \"username\": \"$username\",
            \"password\": \"$password\",
            \"audience\": \"$AUTH0_AUDIENCE\",
            \"scope\": \"$scopes\",
            \"client_id\": \"$client_id\",
            \"client_secret\": \"$client_secret\"
        }"
    else
        data="{
            \"grant_type\": \"client_credentials\",
            \"client_id\": \"$client_id\",
            \"client_secret\": \"$client_secret\",
            \"audience\": \"$AUTH0_AUDIENCE\"
        }"
    fi
    
    local response=$(curl -s --request POST \
        --url "https://$AUTH0_DOMAIN/oauth/token" \
        --header "content-type: application/json" \
        --data "$data")
    
    # Check for errors
    if echo "$response" | jq -e '.error' >/dev/null 2>&1; then
        local error=$(echo "$response" | jq -r '.error_description // .error')
        echo -e "${RED}  ✗ Failed: $error${NC}" >&2
        return 1
    fi
    
    # Extract token
    local token=$(echo "$response" | jq -r '.access_token')
    local expires_in=$(echo "$response" | jq -r '.expires_in')
    
    if [ -z "$token" ] || [ "$token" = "null" ]; then
        echo -e "${RED}  ✗ No token in response${NC}" >&2
        return 1
    fi
    
    # Decode token payload to extract claims
    local payload=$(echo "$token" | cut -d'.' -f2)
    # Add padding if needed for base64 decoding
    local padding=$((4 - ${#payload} % 4))
    if [ $padding -ne 4 ]; then
        payload="${payload}$(printf '%*s' $padding | tr ' ' '=')"
    fi
    
    local decoded=$(echo -n "$payload" | base64 -d 2>/dev/null || echo '{}')
    local exp=$(echo "$decoded" | jq -r '.exp // "unknown"')
    local permissions=$(echo "$decoded" | jq -r '.permissions // [] | join(", ")')
    
    if [ "$exp" != "unknown" ]; then
        local expiry_date=$(date -r "$exp" 2>/dev/null || date -d "@$exp" 2>/dev/null || echo "Check manually")
        echo -e "${GREEN}  ✓ Success${NC}" >&2
        echo "    Expires in: $expires_in seconds (~$((expires_in / 3600)) hours)" >&2
        echo "    Expiry: $expiry_date" >&2
        if [ -n "$permissions" ] && [ "$permissions" != "" ]; then
            echo "    Permissions: $permissions" >&2
        fi
    else
        echo -e "${GREEN}  ✓ Success${NC}" >&2
        echo "    Expires in: $expires_in seconds" >&2
    fi
    
    echo "$token"
}

# Fetch all three token types
echo -e "${BLUE}1. Admin Token (Password Realm)${NC}"
ADMIN_TOKEN=$(fetch_token "Admin" "password" \
    "$AUTH0_USER_CLIENT_ID" \
    "$AUTH0_USER_CLIENT_SECRET" \
    "$AUTH0_ADMIN_USERNAME" \
    "$AUTH0_ADMIN_PASSWORD" \
    "user:me tools:invoke:all admin:all")
echo ""

echo -e "${BLUE}2. User Token (Password Realm)${NC}"
USER_TOKEN=$(fetch_token "User" "password" \
    "$AUTH0_USER_CLIENT_ID" \
    "$AUTH0_USER_CLIENT_SECRET" \
    "$AUTH0_USER_USERNAME" \
    "$AUTH0_USER_PASSWORD" \
    "user:me tools:invoke:basic")
echo ""

echo -e "${BLUE}3. Machine Token (Client Credentials)${NC}"
MACHINE_TOKEN=$(fetch_token "Machine" "client_credentials" \
    "$AUTH0_MACHINE_CLIENT_ID" \
    "$AUTH0_MACHINE_CLIENT_SECRET" \
    "" "" "")
echo ""

# Save to .env if requested
if [ "$SAVE_TO_ENV" = true ]; then
    echo -e "${YELLOW}Saving tokens to .env file...${NC}"
    
    # Create backup
    cp "$ENV_FILE" "$ENV_FILE.backup.$(date +%Y%m%d_%H%M%S)"
    
    # Remove old token lines if they exist
    sed -i.tmp '/^AUTH0_ADMIN_TOKEN=/d' "$ENV_FILE"
    sed -i.tmp '/^AUTH0_USER_TOKEN=/d' "$ENV_FILE"
    sed -i.tmp '/^AUTH0_MACHINE_TOKEN=/d' "$ENV_FILE"
    rm "$ENV_FILE.tmp"
    
    # Append new tokens
    cat >> "$ENV_FILE" << EOF

# Auth0 Tokens (fetched $(date))
AUTH0_ADMIN_TOKEN=$ADMIN_TOKEN
AUTH0_USER_TOKEN=$USER_TOKEN
AUTH0_MACHINE_TOKEN=$MACHINE_TOKEN
EOF
    
    echo -e "${GREEN}✓ Tokens saved to .env${NC}"
    echo "  Backup created: $ENV_FILE.backup.*"
    echo ""
fi

# Export to shell if requested
if [ "$EXPORT_TO_SHELL" = true ]; then
    export AUTH0_ADMIN_TOKEN="$ADMIN_TOKEN"
    export AUTH0_USER_TOKEN="$USER_TOKEN"
    export AUTH0_MACHINE_TOKEN="$MACHINE_TOKEN"
    echo -e "${GREEN}✓ Tokens exported to current shell${NC}"
    echo ""
fi

# Display usage examples
echo -e "${CYAN}=============================================${NC}"
echo -e "${CYAN}  Usage Examples${NC}"
echo -e "${CYAN}=============================================${NC}"
echo ""
echo -e "${BLUE}Export to current shell:${NC}"
echo "  export AUTH0_ADMIN_TOKEN='$ADMIN_TOKEN'"
echo "  export AUTH0_USER_TOKEN='$USER_TOKEN'"
echo "  export AUTH0_MACHINE_TOKEN='$MACHINE_TOKEN'"
echo ""
echo -e "${BLUE}Test admin endpoints:${NC}"
echo "  curl -H \"Authorization: Bearer \$AUTH0_ADMIN_TOKEN\" \\"
echo "    http://localhost:8000/v1/user/me"
echo ""
echo -e "${BLUE}Test user endpoints:${NC}"
echo "  curl -H \"Authorization: Bearer \$AUTH0_USER_TOKEN\" \\"
echo "    http://localhost:8000/v1/user/me"
echo ""
echo -e "${BLUE}Test machine endpoints:${NC}"
echo "  curl -H \"Authorization: Bearer \$AUTH0_MACHINE_TOKEN\" \\"
echo "    http://localhost:8000/v1/health"
echo ""
