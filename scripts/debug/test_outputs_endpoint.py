"""
Quick test to verify /v1/agent-runs/{run_id}/outputs endpoint.
Tests that it returns 200 with empty list when run exists but has no outputs.
"""
import requests
import time

# Use the test user credentials
BASE_URL = "http://localhost:8000"
TEST_USER_EMAIL = "test@example.com"
TEST_USER_PASSWORD = "testpass123"

def get_auth_token():
    """Get JWT token for test user."""
    response = requests.post(
        f"{BASE_URL}/v1/auth/login",
        json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD}
    )
    if response.status_code != 200:
        print(f"❌ Login failed: {response.status_code} - {response.text}")
        return None
    
    data = response.json()
    print(f"✅ Login successful")
    return data.get("access_token")

def test_outputs_endpoint():
    """Test the outputs endpoint."""
    print("\n" + "="*80)
    print("🧪 QUICK TEST: /v1/agent-runs/{run_id}/outputs Endpoint")
    print("="*80 + "\n")
    
    # Step 1: Get auth token
    print("📝 Step 1: Getting auth token...")
    token = get_auth_token()
    if not token:
        print("❌ Failed to get auth token")
        return False
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Step 2: Create an agent run
    print("\n📝 Step 2: Creating agent run...")
    create_response = requests.post(
        f"{BASE_URL}/v1/agent-runs",
        headers=headers,
        json={
            "prompt": "Hello"  # Simple prompt to minimize execution time
        }
    )
    
    if create_response.status_code != 201:
        print(f"❌ Failed to create run: {create_response.status_code} - {create_response.text[:200]}")
        return False
    
    run_data = create_response.json()
    run_id = run_data["run_id"]
    print(f"✅ Run created: {run_id}")
    
    # Step 3: Wait for run to complete
    print("\n📝 Step 3: Waiting for run to complete...")
    max_wait = 60  # Wait up to 60 seconds
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        status_response = requests.get(
            f"{BASE_URL}/v1/agent-runs/{run_id}",
            headers=headers
        )
        
        if status_response.status_code != 200:
            print(f"❌ Failed to get run status: {status_response.status_code}")
            return False
        
        status_data = status_response.json()
        current_status = status_data.get("status")
        print(f"   Status: {current_status}")
        
        if current_status in ["succeeded", "failed", "completed"]:
            print(f"✅ Run completed with status: {current_status}")
            break
        
        time.sleep(2)
    else:
        print("⚠️  Run didn't complete in time, but continuing to test endpoint...")
    
    # Step 4: Test the outputs endpoint
    print("\n📝 Step 4: Testing /v1/agent-runs/{run_id}/outputs...")
    outputs_response = requests.get(
        f"{BASE_URL}/v1/agent-runs/{run_id}/outputs",
        headers=headers
    )
    
    print(f"   HTTP Status: {outputs_response.status_code}")
    print(f"   Response: {outputs_response.text[:500]}")
    
    # Verify the endpoint returns 200
    if outputs_response.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {outputs_response.status_code}")
        return False
    
    print("✅ SUCCESS: Endpoint returns 200")
    
    # Verify it returns a list
    outputs_data = outputs_response.json()
    if not isinstance(outputs_data, list):
        print(f"❌ FAILED: Expected list, got {type(outputs_data)}")
        return False
    
    print(f"✅ SUCCESS: Returns a list with {len(outputs_data)} items")
    
    # Step 5: Test with invalid run_id (should return 404)
    print("\n📝 Step 5: Testing with invalid run_id...")
    invalid_response = requests.get(
        f"{BASE_URL}/v1/agent-runs/00000000-0000-0000-0000-000000000000/outputs",
        headers=headers
    )
    
    print(f"   HTTP Status: {invalid_response.status_code}")
    
    if invalid_response.status_code != 404:
        print(f"❌ FAILED: Expected 404 for invalid run_id, got {invalid_response.status_code}")
        return False
    
    print("✅ SUCCESS: Returns 404 for invalid run_id")
    
    print("\n" + "="*80)
    print("✅ ALL TESTS PASSED")
    print("="*80)
    return True

if __name__ == "__main__":
    success = test_outputs_endpoint()
    exit(0 if success else 1)
