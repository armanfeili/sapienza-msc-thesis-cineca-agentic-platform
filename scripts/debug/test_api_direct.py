"""
Direct API test for agent runs endpoint.
Tests the full flow: create run -> poll status -> verify todos
"""
import asyncio
import json
import httpx
import time
import sys
from pathlib import Path

# Add project root to path (scripts/debug -> root)
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.conftest import mint_oidc_token_sync

# Configuration
API_BASE = "http://localhost:8000"
TEST_PROMPT = "List 3 simple tasks"

def get_token():
    """Get a valid bearer token for API calls."""
    from src.config import settings
    
    # Use the same JWT signing logic as tests
    keys = {
        "secret": settings.JWT_SECRET_KEY or "test-secret-key-for-local-dev-only",
        "algorithm": settings.JWT_ALGORITHM or "HS256",
        "audience": settings.JWT_AUDIENCE or "cineca-api",
        "issuer": settings.JWT_ISSUER or "https://test-issuer.example.com/",
        "kid": "test-key-id",
    }
    
    token = mint_oidc_token_sync(
        sub="test-user",
        issuer=keys["issuer"],
        audience=keys["audience"],
        scopes=["read:runs", "write:runs"],
        roles=["admin"],
        kid=keys["kid"],
    )
    return token


def main():
    """Run direct API test."""
    print("\n" + "="*80)
    print("🧪 DIRECT API TEST: Agent Run Execution")
    print("="*80)
    
    # Get token
    print("\n📝 Step 1: Getting authentication token...")
    try:
        token = get_token()
        print(f"✅ Token obtained: {token[:30]}...")
    except Exception as e:
        print(f"❌ Failed to get token: {e}")
        return
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # Create agent run
    print(f"\n📝 Step 2: Creating agent run with prompt: '{TEST_PROMPT}'")
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{API_BASE}/v1/agent-runs",
                json={"prompt": TEST_PROMPT},
                headers=headers
            )
            
            if response.status_code != 201:
                print(f"❌ Failed to create run: HTTP {response.status_code}")
                print(f"Response: {response.text}")
                return
            
            run_data = response.json()
            run_id = run_data.get("run_id")
            print(f"✅ Agent run created successfully!")
            print(f"   Run ID: {run_id}")
            print(f"   Status: {run_data.get('status')}")
            print(f"   Model: {run_data.get('model')}")
    except Exception as e:
        print(f"❌ Error creating run: {e}")
        return
    
    # Poll for completion
    print(f"\n⏳ Step 3: Polling for completion (max 5 minutes)...")
    max_wait = 300  # 5 minutes
    poll_interval = 5
    elapsed = 0
    
    try:
        with httpx.Client(timeout=30.0) as client:
            while elapsed < max_wait:
                response = client.get(
                    f"{API_BASE}/v1/agent-runs/{run_id}",
                    headers=headers
                )
                
                if response.status_code != 200:
                    print(f"❌ Failed to get run status: HTTP {response.status_code}")
                    return
                
                run_data = response.json()
                status = run_data.get("status")
                
                print(f"   [{elapsed:3d}s] Status: {status}")
                
                if status in ["succeeded", "failed", "cancelled"]:
                    print(f"\n✅ Agent run completed with status: {status}")
                    break
                
                time.sleep(poll_interval)
                elapsed += poll_interval
            else:
                print(f"\n⚠️  Timeout: Run did not complete within {max_wait}s")
                return
    except Exception as e:
        print(f"❌ Error polling run: {e}")
        return
    
    # Verify todos
    print(f"\n📝 Step 4: Verifying todos...")
    try:
        todos = run_data.get("todos", [])
        if not todos:
            print("⚠️  No todos found in response")
        else:
            print(f"✅ Found {len(todos)} todos:")
            for i, todo in enumerate(todos, 1):
                task = todo.get("task", "N/A")
                todo_status = todo.get("status", "N/A")
                print(f"   {i}. [{todo_status}] {task}")
    except Exception as e:
        print(f"❌ Error verifying todos: {e}")
        return
    
    # Check database persistence
    print(f"\n📝 Step 5: Checking database persistence...")
    print("   (Run this separately: docker compose exec postgres psql -U cineca_user -d cineca_platform -c \"SELECT run_id, status, jsonb_array_length(todos) as todo_count FROM agent_runs WHERE run_id::text LIKE '{}'::text LIMIT 1;\")".format(run_id[:8]))
    
    print("\n" + "="*80)
    if status == "succeeded" and todos:
        print("🎉 TEST PASSED: Direct API test successful!")
    else:
        print("⚠️  TEST INCOMPLETE: Check logs for details")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
