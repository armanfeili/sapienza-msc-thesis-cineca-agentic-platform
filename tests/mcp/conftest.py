"""
Test fixtures and utilities for MCP tools testing.

Provides:
- Memgraph, Postgres, Redis fixtures
- Test data seeding
- Mock identities (admin, operator, user)
- Assertion helpers
- Contract test utilities
"""

import os
from typing import Any, Dict, Generator, List, Optional

import pytest

# ── Test identities with RBAC scopes ────────────────────────────────────────

TEST_IDENTITIES = {
    "admin": {
        "principal": "admin@test.local",
        "tenant": "test-tenant",
        "roles": ["admin"],
        "scopes": ["*", "admin:all", "tools:all", "tools:basic"],
    },
    "operator": {
        "principal": "operator@test.local",
        "tenant": "test-tenant",
        "roles": ["operator"],
        "scopes": ["tools:all", "tools:basic"],
    },
    "user": {
        "principal": "user@test.local",
        "tenant": "test-tenant",
        "roles": ["user"],
        "scopes": ["tools:basic"],
    },
    "guest": {
        "principal": None,
        "tenant": "test-tenant",
        "roles": [],
        "scopes": [],
    },
}


def get_identity(role: str = "user") -> Dict[str, Any]:
    """Get test identity by role."""
    return TEST_IDENTITIES.get(role, TEST_IDENTITIES["user"]).copy()


# ── Pytest markers ───────────────────────────────────────────────────────────


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests (no external dependencies)")
    config.addinivalue_line("markers", "integration: Integration tests (require services)")
    config.addinivalue_line("markers", "contract: Contract tests (API shape verification)")
    config.addinivalue_line("markers", "slow: Slow-running tests")


# ── Service fixtures ─────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def docker_compose_file():
    """Path to docker-compose file for integration tests."""
    return os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "docker-compose.yml",
    )


@pytest.fixture(scope="session")
def memgraph_connection():
    """Memgraph connection for integration tests."""
    pytest.importorskip("neo4j", reason="neo4j driver required for Memgraph tests")

    try:
        from src.adapters.db_memgraph import MemgraphAdapter

        db = MemgraphAdapter()
        # Test connection
        db.query("RETURN 1 AS test")
        yield db
    except Exception as e:
        pytest.skip(f"Memgraph not available: {e}")


@pytest.fixture(scope="session")
def postgres_connection():
    """Postgres connection for integration tests."""
    pytest.importorskip("psycopg2", reason="psycopg2 required for Postgres tests")

    try:
        from src.adapters.db_postgres import get_db

        db = next(get_db())
        yield db
    except Exception as e:
        pytest.skip(f"Postgres not available: {e}")


@pytest.fixture(scope="session")
def redis_connection():
    """Redis connection for integration tests."""
    pytest.importorskip("redis", reason="redis-py required for Redis tests")

    try:
        from src.adapters.cache_redis import RedisAdapter

        cache = RedisAdapter()
        # Test connection
        cache.ping()
        yield cache
    except Exception as e:
        pytest.skip(f"Redis not available: {e}")


# ── Graph fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def clean_graph(memgraph_connection):
    """Clean Memgraph graph before test."""
    db = memgraph_connection

    # Clean before
    db.query("MATCH (n) DETACH DELETE n")

    yield db

    # Clean after
    db.query("MATCH (n) DETACH DELETE n")


@pytest.fixture
def sample_graph(clean_graph):
    """Seed small synthetic graph for testing."""
    db = clean_graph

    # Create sample nodes
    nodes = [
        {"labels": ["User"], "orig_id": "user-1", "props": {"name": "Alice", "status": "active"}},
        {"labels": ["User"], "orig_id": "user-2", "props": {"name": "Bob", "status": "active"}},
        {"labels": ["User"], "orig_id": "user-3", "props": {"name": "Charlie", "status": "inactive"}},
        {"labels": ["Institution"], "orig_id": "inst-1", "props": {"name": "MIT", "city": "Boston"}},
        {"labels": ["Institution"], "orig_id": "inst-2", "props": {"name": "Stanford", "city": "Palo Alto"}},
        {"labels": ["Task"], "orig_id": "task-1", "props": {"title": "Research", "status": "done"}},
        {"labels": ["Task"], "orig_id": "task-2", "props": {"title": "Development", "status": "in_progress"}},
    ]

    for node in nodes:
        labels = ":".join(node["labels"])
        cypher = f"CREATE (n:{labels}) SET n = $props, n.orig_id = $orig_id"
        db.query(cypher, params={"orig_id": node["orig_id"], "props": node["props"]})

    # Create relationships
    relationships = [
        {"start": "user-1", "end": "inst-1", "type": "WORKS_AT", "props": {"since": "2020"}},
        {"start": "user-2", "end": "inst-2", "type": "WORKS_AT", "props": {"since": "2021"}},
        {"start": "user-1", "end": "task-1", "type": "RUNS", "props": {}},
        {"start": "user-2", "end": "task-2", "type": "RUNS", "props": {}},
    ]

    for rel in relationships:
        cypher = (
            "MATCH (a {orig_id: $start}), (b {orig_id: $end}) " f"CREATE (a)-[r:{rel['type']}]->(b) " "SET r = $props"
        )
        db.query(cypher, params={"start": rel["start"], "end": rel["end"], "props": rel["props"]})

    yield db


# ── Assertion helpers ────────────────────────────────────────────────────────


def assert_standard_response(result: Dict[str, Any], expected_ok: bool = True):
    """Assert standard tool response shape."""
    assert isinstance(result, dict), "Result must be a dict"
    assert "ok" in result, "Result must have 'ok' field"
    assert result["ok"] == expected_ok, f"Expected ok={expected_ok}, got {result.get('ok')}"

    if expected_ok:
        assert "action" in result, "Success response must have 'action' field"
    else:
        assert "code" in result, "Error response must have 'code' field"
        assert "message" in result, "Error response must have 'message' field"


def assert_error_response(
    result: Dict[str, Any],
    expected_code: Optional[str] = None,
    expected_message_contains: Optional[str] = None,
):
    """Assert error response shape and content."""
    assert_standard_response(result, expected_ok=False)

    if expected_code:
        assert result["code"] == expected_code, f"Expected code={expected_code}, got {result.get('code')}"

    if expected_message_contains:
        message = result.get("message", "")
        assert (
            expected_message_contains in message
        ), f"Expected message to contain '{expected_message_contains}', got: {message}"


def assert_audit_event_emitted(
    audit_log: List[Dict[str, Any]],
    tool: str,
    action: str,
    principal: Optional[str] = None,
    allowed: Optional[bool] = None,
):
    """Assert audit event was emitted with expected fields."""
    matching_events = [e for e in audit_log if e.get("resource", "").endswith(tool) and e.get("action") == action]

    assert len(matching_events) > 0, f"No audit event found for {tool}.{action}"

    event = matching_events[0]

    if principal is not None:
        assert event.get("principal") == principal, f"Expected principal={principal}"

    if allowed is not None:
        assert event.get("allowed") == allowed, f"Expected allowed={allowed}"


# ── Contract test utilities ──────────────────────────────────────────────────


def verify_tool_contract(
    tool_module: Any,
    expected_actions: List[str],
    sample_payloads: Dict[str, Dict[str, Any]],
):
    """
    Verify tool follows MCP contract.

    Checks:
    - Has invoke() entrypoint
    - Returns standard response shape
    - Handles invalid actions
    - Validates required fields
    """
    # Check entrypoint exists
    assert hasattr(tool_module, "invoke"), f"Tool must have 'invoke' function"
    invoke = tool_module.invoke
    assert callable(invoke), "'invoke' must be callable"

    # Check invalid action handling
    result = invoke({"action": "invalid_action_xyz"})
    assert_error_response(result, expected_code="E_VALIDATION")

    # Check each expected action
    for action in expected_actions:
        assert action in sample_payloads, f"No sample payload for action '{action}'"

        payload = sample_payloads[action]
        result = invoke(payload)

        # Should return dict with standard shape
        assert_standard_response(result)
        assert result.get("action") == action, f"Action mismatch for {action}"


# ── Payload builders ─────────────────────────────────────────────────────────


def build_payload(
    action: str,
    identity: str = "user",
    **kwargs: Any,
) -> Dict[str, Any]:
    """Build standard tool payload with identity context."""
    ident = get_identity(identity)

    payload = {
        "action": action,
        "principal": ident["principal"],
        "tenant": ident["tenant"],
        **kwargs,
    }

    return payload


# ── Mock LLM adapter ─────────────────────────────────────────────────────────


class MockLLMAdapter:
    """Mock LLM adapter for testing."""

    def __init__(self, responses: Optional[Dict[str, str]] = None):
        self.responses = responses or {}
        self.calls: List[Dict[str, Any]] = []

    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 512,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Mock completion."""
        self.calls.append(
            {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "temperature": temperature,
                "max_tokens": max_tokens,
                **kwargs,
            }
        )

        # Return pre-configured response or default
        content = self.responses.get(prompt, "MATCH (n) RETURN n LIMIT 10")

        return {
            "content": content,
            "model": "mock-model",
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }


@pytest.fixture
def mock_llm():
    """Mock LLM adapter fixture."""
    return MockLLMAdapter()
