"""
Unit test for agent runs API with new typed schema.
Tests the API contract without requiring full orchestrator execution.
"""
import pytest
from fastapi.testclient import TestClient
from uuid import uuid4
from datetime import datetime, timezone
import sys
from pathlib import Path

# Add project root to path (scripts/debug -> root)
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Configure environment before imports
import os
os.environ["APP_ENV"] = "test"
os.environ["DEMO_MODE"] = "true"
os.environ["RATE_LIMIT_MODE"] = "test"
os.environ["DB_HOST"] = "localhost"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"

def test_agent_run_response_schema():
    """Test that agent run API returns properly typed response"""
    from src.app import create_app
    from tests.fixtures.oidc import generate_rsa_keypair, write_jwks, mint_jwt
    
    # Setup OIDC for auth
    keys = generate_rsa_keypair()
    jwks_path = write_jwks(keys["jwks"])
    
    os.environ["OIDC_ISSUER"] = keys["issuer"]
    os.environ["OIDC_AUDIENCE"] = keys["audience"]
    os.environ["OIDC_JWKS_URL"] = f"file://{jwks_path}"
    
    app = create_app()
    client = TestClient(app)
    
    # Mint JWT token
    token = mint_jwt(
        keys["priv_key_pem"],
        kid=keys["kid"],
        sub="test-user-123",
        iss=keys["issuer"],
        aud=keys["audience"],
        scopes=["user:me"]
    )
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create agent run
    response = client.post(
        "/v1/agent-runs",
        headers=headers,
        json={"prompt": "Hello, test!"}
    )
    
    assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"
    
    data = response.json()
    
    # Validate response structure
    assert "run_id" in data, "Response should have run_id"
    assert "status" in data, "Response should have status"
    assert "prompt" in data, "Response should have prompt"
    
    # Validate new typed fields
    print(f"\n✅ Response structure:")
    print(f"   run_id: {data.get('run_id')}")
    print(f"   status: {data.get('status')}")
    print(f"   steps: {data.get('steps')}")
    print(f"   todos: {data.get('todos')}")
    print(f"   errors: {data.get('errors')}")
    print(f"   metrics: {data.get('metrics')}")
    
    # Validate steps structure
    steps = data.get("steps")
    if steps:
        assert isinstance(steps, list), "steps should be a list"
        for step in steps:
            assert isinstance(step, dict), f"Each step should be a dict, got {type(step)}"
            assert "step_id" in step, "Each step should have step_id"
            # Check for discriminator field
            if "type" in step:
                assert step["type"] in ["step", "output"], f"step type should be 'step' or 'output', got {step['type']}"
            print(f"   Step: {step.get('step_id')} (type: {step.get('type', 'unknown')})")
    
    # Validate todos structure
    todos = data.get("todos")
    if todos:
        assert isinstance(todos, list), "todos should be a list"
        for todo in todos:
            assert isinstance(todo, dict), f"Each todo should be a dict, got {type(todo)}"
            assert "task" in todo, "Each todo should have task"
            if "status" in todo:
                assert todo["status"] in ["pending", "in_progress", "completed", "failed", None], \
                    f"todo status should be valid, got {todo['status']}"
            print(f"   Todo: {todo.get('task')[:50]}... (status: {todo.get('status')})")
    
    # Validate errors structure
    errors = data.get("errors")
    if errors is not None:
        assert isinstance(errors, list), "errors should be a list"
        print(f"   Errors: {len(errors)} error(s)")
    
    # Validate metrics structure  
    metrics = data.get("metrics")
    if metrics is not None:
        assert isinstance(metrics, dict), "metrics should be a dict"
        print(f"   Metrics: {metrics}")
    
    print("\n🎉 API response schema validation passed!")

if __name__ == "__main__":
    test_agent_run_response_schema()
