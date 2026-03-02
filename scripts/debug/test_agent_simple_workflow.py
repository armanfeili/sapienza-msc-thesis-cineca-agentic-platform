#!/usr/bin/env python3
"""
Simple test to verify the agent workflow with hybrid LLM setup.
This test creates a simple agent run and verifies it executes successfully.
"""
import asyncio
import httpx
import time
from datetime import datetime

BASE_URL = "http://localhost:8000"

async def test_simple_agent_workflow():
    """Test a simple agent workflow: List available tools."""
    
    print("=" * 80)
    print("🧪 SIMPLE AGENT WORKFLOW TEST")
    print("=" * 80)
    print()
    
    # Get auth token
    print("📝 Step 1: Getting authentication token...")
    async with httpx.AsyncClient(timeout=30.0) as client:
        auth_response = await client.post(
            f"{BASE_URL}/v1/auth/token",
            json={
                "username": "admin",
                "password": "admin123"
            }
        )
        
        if auth_response.status_code != 200:
            print(f"❌ Auth failed: {auth_response.status_code}")
            print(f"Response: {auth_response.text}")
            return False
        
        token = auth_response.json().get("access_token")
        if not token:
            print("❌ No token received")
            return False
        
        print(f"✅ Token received: {token[:20]}...")
        print()
    
    # Create agent run
    print("📝 Step 2: Creating agent run...")
    print("   Goal: 'Say hello and tell me your name'")
    print("   (This is a simple task that doesn't require tools)")
    print()
    
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient(timeout=720.0) as client:  # 12 minute timeout
        start_time = time.time()
        
        create_response = await client.post(
            f"{BASE_URL}/v1/agent-runs",
            headers=headers,
            json={
                "prompt": "Say hello and tell me your name"
            }
        )
        
        if create_response.status_code != 201:
            print(f"❌ Failed to create agent run: {create_response.status_code}")
            print(f"Response: {create_response.text}")
            return False
        
        run_data = create_response.json()
        run_id = run_data.get("run_id")
        
        print(f"✅ Agent run created successfully")
        print(f"   Run ID: {run_id}")
        print(f"   Status: {run_data.get('status')}")
        print(f"   Model: {run_data.get('model')}")
        print(f"   Manager: {run_data.get('manager')}")
        print()
        
        # Poll for completion
        print("⏳ Step 3: Waiting for completion...")
        print("   This may take several minutes for CPU-based model...")
        print()
        
        max_wait = 720  # 12 minutes
        poll_interval = 10  # Check every 10 seconds
        elapsed = 0
        
        while elapsed < max_wait:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            
            status_response = await client.get(
                f"{BASE_URL}/v1/agent-runs/{run_id}",
                headers=headers
            )
            
            if status_response.status_code != 200:
                print(f"❌ Failed to get status: {status_response.status_code}")
                return False
            
            status_data = status_response.json()
            current_status = status_data.get("status")
            
            elapsed_time = time.time() - start_time
            print(f"   [{int(elapsed_time)}s] Status: {current_status}")
            
            if current_status in ["succeeded", "failed", "cancelled"]:
                print()
                print(f"✅ Agent run completed with status: {current_status}")
                print(f"   Total time: {elapsed_time:.1f} seconds")
                print()
                
                # Show output
                if current_status == "succeeded":
                    output = status_data.get("output", "")
                    todos = status_data.get("todos", [])
                    
                    print("📊 Results:")
                    print(f"   TODOs created: {len(todos)}")
                    if todos:
                        print("   TODO list:")
                        for i, todo in enumerate(todos, 1):
                            task = todo.get("task", "Unknown")
                            status = todo.get("status", "unknown")
                            print(f"     {i}. [{status}] {task}")
                    
                    print()
                    print("   Output preview:")
                    print(f"   {output[:200]}..." if len(output) > 200 else f"   {output}")
                    print()
                    
                    return True
                else:
                    error = status_data.get("error", "Unknown error")
                    print(f"❌ Run failed: {error}")
                    return False
        
        print(f"⏰ Timeout after {max_wait} seconds")
        return False

if __name__ == "__main__":
    print(f"Starting test at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    result = asyncio.run(test_simple_agent_workflow())
    
    print()
    print("=" * 80)
    if result:
        print("🎉 TEST PASSED: Agent workflow successful!")
    else:
        print("❌ TEST FAILED: Agent workflow unsuccessful")
    print("=" * 80)
