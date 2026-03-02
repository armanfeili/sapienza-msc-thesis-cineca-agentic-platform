#!/usr/bin/env python3
"""Manual test of security validation endpoint."""
import os
import requests

# Get token from environment
token = os.getenv('AUTH0_ADMIN_TOKEN')

if not token:
    print("❌ AUTH0_ADMIN_TOKEN not found in environment")
    print("Run: ./scripts/fetch_auth0_tokens.sh --save-to-env")
    exit(1)

print(f"✅ Token found: {token[:20]}...")

# Test the endpoint
print("\n🔒 Testing graph.secure_query validate action...")

try:
    response = requests.post(
        'http://app:8000/v1/tools/graph.secure_query/invocations',
        headers={'Authorization': f'Bearer {token}'},
        json={
            'args': {
                'action': 'validate',
                'cypher': 'MATCH (n) RETURN count(n)',
                'principal': 'test@example.com',
                'tenant': 'default'
            }
        },
        timeout=10
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response:\n{response.text[:500]}")
    
    if response.status_code == 201:
        data = response.json()
        print("\n✅ Tool invocation successful!")
        print(f"Result keys: {list(data.keys())}")
        
except requests.exceptions.Timeout:
    print("❌ Request timed out after 10 seconds")
except Exception as e:
    print(f"❌ Error: {e}")
