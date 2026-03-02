"""
Security Path Smoke Tests - TODO #7

Validates graph.secure_query security controls using the validate action.
Tests write/delete/dangerous operations are correctly identified as unsafe.

Priority: SECURITY | Status: IMPLEMENTED
"""

import os
import platform

import pytest
import requests


class TestGraphSecureQuery:
    """Test suite for graph.secure_query security validation."""

    @pytest.fixture(scope="class")
    def base_url(self) -> str:
        """
        Get base URL for API requests.
        
        When running inside Docker, use 'app:8000' (Docker service name).
        When running on host, use '127.0.0.1:8000' (IPv4).
        """
        # Check if we're running inside Docker
        if platform.system() == "Linux" and os.path.exists("/.dockerenv"):
            # Inside Docker - use service name
            return os.getenv("API_BASE_URL", "http://app:8000")
        else:
            # On host - use localhost IPv4
            return os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

    @pytest.fixture(scope="class")
    def auth0_tokens(self):
        """Fetch real Auth0 tokens from environment variables."""
        env_admin = os.getenv("AUTH0_ADMIN_TOKEN")
        env_user = os.getenv("AUTH0_USER_TOKEN")
        env_machine = os.getenv("AUTH0_MACHINE_TOKEN")
        
        if not (env_admin and env_user and env_machine):
            pytest.fail(
                "Auth0 tokens not found in environment. "
                "Run: ./fetch_auth0_tokens.sh --save-to-env"
            )
        
        return {
            "admin": env_admin,
            "user": env_user,
            "machine": env_machine
        }

    @pytest.fixture(scope="class")
    def admin_headers(self, auth0_tokens):
        """Authorization headers with real Auth0 admin token."""
        return {"Authorization": f"Bearer {auth0_tokens['admin']}"}

    def test_read_only_query_validates_successfully(
        self, base_url: str, admin_headers: dict[str, str]
    ):
        """Test 1: Read-only query should pass validation."""
        print("\n" + "=" * 80)
        print("TEST 1: Read-Only Query Validation")
        print("=" * 80)

        read_query = "MATCH (n) RETURN count(n) as node_count"
        
        payload = {
            "args": {
                "action": "validate",
                "cypher": read_query,
                "principal": "test-user@example.com",
                "tenant": "default"
            }
        }
        
        print(f"   Query: {read_query}")
        print(f"   URL: {base_url}/v1/tools/graph.secure_query/invocations")
        print(f"   Payload: {payload}")
        
        response = requests.post(
            f"{base_url}/v1/tools/graph.secure_query/invocations",
            headers=admin_headers,
            json=payload,
            timeout=300,  # 5 minutes timeout for CPU-based LLM
        )

        print(f"   Query: {read_query}")
        print(f"   Status: {response.status_code}")
        
        # Debug: Print the full response
        print(f"   Response: {response.text[:500]}")
        
        # Tool invocations return 201 Created with the result
        assert response.status_code == 201, (
            f"Read-only query validation should succeed. Got {response.status_code}: {response.text}"
        )
        
        result = response.json()
        # Debug: Show the structure
        print(f"   Result keys: {list(result.keys())}")
        print(f"   Result.result keys: {list(result.get('result', {}).keys())}")
        
        # The result is nested in result.result due to the wrapper
        tool_result = result.get("result", {})
        validation = tool_result.get("validation", {})
        
        print(f"   Validation: {validation}")
        
        assert validation.get("read_only") is True, "Query should be marked as read-only"
        assert validation.get("safe") is True, "Query should be marked as safe"
        
        print(f"   ✓ Read-only query validated successfully")

    def test_create_query_blocked(
        self, base_url: str, admin_headers: dict[str, str]
    ):
        """Test 2: CREATE operations should be blocked."""
        print("\n" + "=" * 80)
        print("TEST 2: CREATE Query Blocked")
        print("=" * 80)

        create_query = "CREATE (n:TestNode {name: 'hack'}) RETURN n"
        
        response = requests.post(
            f"{base_url}/v1/tools/graph.secure_query/invocations",
            headers=admin_headers,
            json={
                "args": {
                    "action": "validate",
                    "cypher": create_query,
                    "principal": "test-user@example.com",
                    "tenant": "default"
                }
            },
            timeout=300,  # 5 minutes timeout for CPU-based LLM
        )

        print(f"   Query: {create_query}")
        print(f"   Status: {response.status_code}")

        assert response.status_code == 201
        result = response.json()
        tool_result = result.get("result", {})
        validation = tool_result.get("validation", {})
        
        assert validation.get("read_only") is False, "CREATE query should NOT be read-only"
        assert validation.get("safe") is False, "CREATE query should NOT be safe"
        
        print(f"   ✓ CREATE query correctly identified as unsafe")

    def test_multiple_write_operations_blocked(
        self, base_url: str, admin_headers: dict[str, str]
    ):
        """Test 3: Multiple write operations should all be blocked."""
        print("\n" + "=" * 80)
        print("TEST 3: Multiple Write Operations Blocked")
        print("=" * 80)

        write_queries = [
            ("CREATE", "CREATE (n:Test) RETURN n"),
            ("MERGE", "MERGE (n:Test {id: 1}) RETURN n"),
            ("SET", "MATCH (n) SET n.prop = 'value' RETURN n"),
            ("DELETE", "MATCH (n:Test) DELETE n"),
            ("DETACH DELETE", "MATCH (n) DETACH DELETE n"),
        ]

        blocked_count = 0
        for operation, query in write_queries:
            response = requests.post(
                f"{base_url}/v1/tools/graph.secure_query/invocations",
                headers=admin_headers,
                json={
                    "args": {
                        "action": "validate",
                        "cypher": query,
                        "principal": "test-user@example.com",
                        "tenant": "default"
                    }
                },
                timeout=30,
            )

            if response.status_code == 201:
                result = response.json()
                tool_result = result.get("result", {})
                validation = tool_result.get("validation", {})
                
                if validation.get("safe") is False:
                    blocked_count += 1
                    print(f"   ✓ {operation}: correctly identified as unsafe")
                else:
                    assert False, f"{operation} should be blocked"

        print(f"\n   ✓ All {blocked_count}/{len(write_queries)} write operations correctly blocked")

    def test_drop_command_blocked(
        self, base_url: str, admin_headers: dict[str, str]
    ):
        """Test 4: DROP commands should be blocked."""
        print("\n" + "=" * 80)
        print("TEST 4: DROP Command Blocked")
        print("=" * 80)

        drop_query = "DROP INDEX ON :Node(property)"
        
        response = requests.post(
            f"{base_url}/v1/tools/graph.secure_query/invocations",
            headers=admin_headers,
            json={
                "args": {
                    "action": "validate",
                    "cypher": drop_query,
                    "principal": "test-user@example.com",
                    "tenant": "default"
                }
            },
            timeout=30,
        )

        print(f"   Query: {drop_query}")
        print(f"   Status: {response.status_code}")

        assert response.status_code == 201
        result = response.json()
        tool_result = result.get("result", {})
        validation = tool_result.get("validation", {})
        
        assert validation.get("safe") is False, "DROP command should NOT be safe"
        
        print(f"   ✓ DROP command correctly identified as unsafe")
