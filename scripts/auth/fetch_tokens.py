#!/usr/bin/env python3
"""Fetch fresh Auth0 tokens for testing RBAC."""

import json
import requests

def fetch_token(name, payload):
    """Fetch a token from Auth0."""
    print(f"Fetching {name} token...")
    response = requests.post(
        "https://cineca.eu.auth0.com/oauth/token",
        headers={"content-type": "application/json"},
        json=payload,
        timeout=10
    )
    response.raise_for_status()
    data = response.json()
    token = data['access_token']
    print(f"✓ {name} token: {token[:50]}...")
    return token

# Fetch all three tokens
try:
    admin_token = fetch_token("ADMIN", {
        "grant_type": "http://auth0.com/oauth/grant-type/password-realm",
        "client_id": "kwkf1bGn2NmdKWzioZYkvtYM022dzb5C",
        "client_secret": "z8Qf1DeYl-6fDKlGn5tpOuAshkjhiJmNrYkPibfBoR5vA5VC_7qznoavBN0rSZEB",
        "audience": "api://cineca-agentic-platform",
        "username": "admin@example.com",
        "password": "AdminPass123!",
        "realm": "Username-Password-Authentication",
        "scope": "user:me tools:invoke:all admin:all"
    })
    
    user_token = fetch_token("USER", {
        "grant_type": "http://auth0.com/oauth/grant-type/password-realm",
        "client_id": "kwkf1bGn2NmdKWzioZYkvtYM022dzb5C",
        "client_secret": "z8Qf1DeYl-6fDKlGn5tpOuAshkjhiJmNrYkPibfBoR5vA5VC_7qznoavBN0rSZEB",
        "audience": "api://cineca-agentic-platform",
        "username": "user@example.com",
        "password": "UserPass123!",
        "realm": "Username-Password-Authentication",
        "scope": "user:me tools:invoke:basic"
    })
    
    machine_token = fetch_token("MACHINE", {
        "client_id": "OrcZzF86Wvh4DaSaaRf7uHLFRNpqa40N",
        "client_secret": "i7rLVZpe4ehgP4wUBuo3cSd-w3kP3a0hghEJshpv52Fw1tJfs3uGa6JOg-te9NSE",
        "audience": "api://cineca-agentic-platform",
        "grant_type": "client_credentials"
    })
    
    # Save to shell script
    with open("/tmp/tokens.sh", "w") as f:
        f.write(f'ADMIN_TOKEN="{admin_token}"\n')
        f.write(f'USER_TOKEN="{user_token}"\n')
        f.write(f'MACHINE_TOKEN="{machine_token}"\n')
    
    print("\n✅ All tokens fetched and saved to /tmp/tokens.sh")
    
    # Also save as JSON for easier parsing
    with open("/tmp/tokens.json", "w") as f:
        json.dump({
            "admin": admin_token,
            "user": user_token,
            "machine": machine_token
        }, f, indent=2)
    
    print("✅ Tokens also saved to /tmp/tokens.json")

except Exception as e:
    print(f"❌ Error fetching tokens: {e}")
    exit(1)
