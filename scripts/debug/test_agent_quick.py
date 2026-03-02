#!/usr/bin/env python3
"""
Quick test to verify agent execution with real LLM.
"""
import requests
import time
import json

# Test configuration
API_BASE = "http://localhost:8000"

# Get a test token (using demo auth)
print("🔐 Getting test token...")
auth_response = requests.get(f"{API_BASE}/debug/demo-token")
if auth_response.status_code != 200:
    print(f"❌ Failed to get token: {auth_response.status_code}")
    exit(1)

token_data = auth_response.json()
access_token = token_data.get("access_token")
print(f"✅ Got access token: {access_token[:20]}...")

headers = {"Authorization": f"Bearer {access_token}"}

# Create an agent run
print("\n🚀 Creating agent run...")
run_payload = {
    "prompt": "List the tools you have available."
}

create_response = requests.post(
    f"{API_BASE}/v1/agent-runs",
    headers=headers,
    json=run_payload
)

if create_response.status_code != 201:
    print(f"❌ Failed to create run: {create_response.status_code}")
    print(create_response.text)
    exit(1)

run_data = create_response.json()
run_id = run_data.get("run_id")
print(f"✅ Created run: {run_id}")
print(f"   Status: {run_data.get('status')}")
print(f"   Manager: {run_data.get('manager')}")
print(f"   Model: {run_data.get('model')}")

# Check if manager or model is set
manager = run_data.get("manager")
model = run_data.get("model")

if not manager and not model:
    print("⚠️  WARNING: Both manager and model are null!")
    print("   This likely means the orchestrator is in fallback/demo mode")
else:
    print(f"✅ LLM configured: {manager or model}")

# Poll for completion
print("\n⏳ Waiting for completion...")
max_attempts = 60
for attempt in range(max_attempts):
    status_response = requests.get(f"{API_BASE}/v1/agent-runs/{run_id}", headers=headers)
    if status_response.status_code != 200:
        print(f"❌ Failed to get status: {status_response.status_code}")
        break
    
    status_data = status_response.json()
    current_status = status_data.get("status")
    
    print(f"   [{attempt+1}/{max_attempts}] Status: {current_status}")
    
    if current_status in ["completed", "failed", "cancelled", "succeeded"]:
        print(f"\n✅ Run {current_status}!")
        print(f"   Output: {status_data.get('output', '')[:200]}...")
        
        # Check if TODOs were created
        todos = status_data.get("todos", [])
        if todos:
            print(f"\n📝 TODO List ({len(todos)} items):")
            for idx, todo in enumerate(todos, 1):
                task = todo.get("task", "")
                status = todo.get("status", "")
                print(f"   {idx}. [{status}] {task}")
        else:
            print("\n⚠️  No TODO list found in response")
        
        break
    
    time.sleep(1)
else:
    print(f"\n❌ Run did not complete within {max_attempts} seconds")

print("\n" + "="*60)
print("Test completed!")
