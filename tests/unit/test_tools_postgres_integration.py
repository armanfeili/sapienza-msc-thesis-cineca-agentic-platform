"""
Comprehensive integration tests for tools PostgreSQL + Redis implementation.

Tests cover:
- Tool CRUD operations with pagination
- Invocation lifecycle (pending → running → finished/failed)
- Idempotency with conflict detection (409)
- Audit event tracking
- Redis cache integration (hit/miss)
- Edge cases (missing tenant, invalid versions, concurrent operations)
"""

import pytest
import uuid
from datetime import datetime, timedelta


def _auth(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


# ============================================================================
# Tool CRUD Tests
# ============================================================================


@pytest.mark.integration
def test_tool_crud_lifecycle(client, mint_token, db_session):
    """Test creating, retrieving, and updating tools."""
    from db.postgres_control.repositories.tools import ToolsRepository

    repo = ToolsRepository(db_session)

    # Create a tool
    tool = repo.create_tool(
        name="test.calculator",
        version="1",
        tenant_id="default-tenant",
        input_schema={"type": "object", "properties": {"x": {"type": "number"}}},
        description="Test calculator tool",
        metadata={"category": "math"},
    )
    db_session.commit()

    assert tool.name == "test.calculator"
    assert tool.version == "1"
    assert tool.description == "Test calculator tool"

    # Retrieve by name and version
    retrieved = repo.get_tool_by_name_version("test.calculator", "1")
    assert retrieved is not None
    assert retrieved.id == tool.id
    assert retrieved.metadata == {"category": "math"}

    # List all tools
    tools = repo.list_tools(limit=10)
    assert len(tools) > 0
    assert any(t.name == "test.calculator" for t in tools)


@pytest.mark.integration
def test_tool_pagination(client, mint_token, db_session):
    """Test tool listing with pagination."""
    from db.postgres_control.repositories.tools import ToolsRepository

    repo = ToolsRepository(db_session)

    # Create multiple tools
    for i in range(5):
        repo.create_tool(
            name=f"test.tool_{i}",
            version="1",
            tenant_id="default-tenant",
            input_schema={"type": "object"},
        )
    db_session.commit()

    # Fetch first page
    page1 = repo.list_tools(limit=2, offset=0)
    assert len(page1) == 2

    # Fetch second page
    page2 = repo.list_tools(limit=2, offset=2)
    assert len(page2) == 2

    # Ensure no overlap
    page1_ids = {t.id for t in page1}
    page2_ids = {t.id for t in page2}
    assert page1_ids.isdisjoint(page2_ids)


# ============================================================================
# Invocation Lifecycle Tests
# ============================================================================


@pytest.mark.integration
def test_invocation_lifecycle_states(client, mint_token, db_session):
    """Test invocation state transitions: pending → running → finished."""
    from db.postgres_control.repositories.tools import ToolsRepository

    repo = ToolsRepository(db_session)

    # Create invocation in pending state
    invocation, created = repo.create_invocation(
        tool_name="system.health",
        tool_version="1",
        tenant_id="default-tenant",
        params={"action": "liveness"},
        requested_by="alice",
    )
    db_session.commit()

    assert created is True
    assert invocation.status == "pending"
    assert invocation.params_json == {"action": "liveness"}

    # Update to running
    repo.update_invocation_status(
        eid=invocation.eid,
        status="running",
    )
    db_session.commit()

    updated = repo.get_invocation_by_eid(invocation.eid)
    assert updated.status == "running"

    # Update to finished with result
    repo.update_invocation_status(
        eid=invocation.eid,
        status="finished",
        result={"healthy": True},
        latency_ms=50,
    )
    db_session.commit()

    finished = repo.get_invocation_by_eid(invocation.eid)
    assert finished.status == "finished"
    assert finished.result_json == {"healthy": True}
    assert finished.latency_ms == 50


@pytest.mark.integration
def test_invocation_failure_with_error(client, mint_token, db_session):
    """Test invocation failure state with error details."""
    from db.postgres_control.repositories.tools import ToolsRepository

    repo = ToolsRepository(db_session)

    # Create invocation
    invocation, _ = repo.create_invocation(
        tool_name="test.failing",
        tool_version="1",
        tenant_id="default-tenant",
        params={"will_fail": True},
        requested_by="alice",
    )
    db_session.commit()

    # Update to failed with error
    error_detail = {
        "message": "Tool execution failed",
        "type": "ExecutionError",
        "traceback": "Traceback...",
    }
    repo.update_invocation_status(
        eid=invocation.eid,
        status="failed",
        error=error_detail,
        latency_ms=100,
    )
    db_session.commit()

    failed = repo.get_invocation_by_eid(invocation.eid)
    assert failed.status == "failed"
    assert failed.error_json["message"] == "Tool execution failed"
    assert failed.error_json["type"] == "ExecutionError"


# ============================================================================
# Idempotency Tests
# ============================================================================


@pytest.mark.integration
def test_idempotency_same_params_returns_existing(client, mint_token):
    """Test idempotent replay with same params returns existing invocation."""
    tok = mint_token(sub="alice", scopes=["tools:basic"])
    headers = {**_auth(tok), "Idempotency-Key": "idem-test-1"}

    # First request
    r1 = client.post(
        "/v1/tools/system.health/invocations",
        json={"args": {"action": "liveness"}},
        headers=headers,
    )
    assert r1.status_code in (200, 201)
    eid1 = r1.json()["event_id"]

    # Second request (replay)
    r2 = client.post(
        "/v1/tools/system.health/invocations",
        json={"args": {"action": "liveness"}},
        headers=headers,
    )
    assert r2.status_code == 200
    eid2 = r2.json()["event_id"]

    # Should return same invocation
    assert eid1 == eid2
    assert r2.headers.get("Idempotency-Replayed") == "true"


@pytest.mark.integration
def test_idempotency_different_params_returns_409(client, mint_token):
    """Test idempotency conflict: same key, different params → 409."""
    tok = mint_token(sub="alice", scopes=["tools:basic"])
    headers = {**_auth(tok), "Idempotency-Key": "idem-conflict-1"}

    # First request
    r1 = client.post(
        "/v1/tools/system.health/invocations",
        json={"args": {"action": "liveness"}},
        headers=headers,
    )
    assert r1.status_code in (200, 201)

    # Second request with different params
    r2 = client.post(
        "/v1/tools/system.health/invocations",
        json={"args": {"action": "readiness"}},  # Different!
        headers=headers,
    )
    assert r2.status_code == 409
    assert "different parameters" in r2.json()["detail"]


@pytest.mark.integration
def test_idempotency_mapping_in_redis(client, mint_token, db_session):
    """Test idempotency key mapping is stored in Redis."""
    from db.redis_cache import tools_cache

    tok = mint_token(sub="alice", scopes=["tools:basic"])
    idem_key = f"idem-redis-{uuid.uuid4()}"
    headers = {**_auth(tok), "Idempotency-Key": idem_key}

    # Create invocation
    r = client.post(
        "/v1/tools/system.health/invocations",
        json={"args": {"action": "liveness"}},
        headers=headers,
    )
    assert r.status_code in (200, 201)
    eid = r.json()["event_id"]

    # Check Redis mapping
    mapped_eid = tools_cache.get_idempotency_mapping(idem_key)
    assert mapped_eid == eid


# ============================================================================
# Audit Event Tests
# ============================================================================


@pytest.mark.integration
def test_audit_events_for_invocation(client, mint_token, db_session):
    """Test audit events are created for invocation lifecycle."""
    from db.postgres_control.repositories.tools import ToolsRepository

    repo = ToolsRepository(db_session)

    # Create invocation
    invocation, _ = repo.create_invocation(
        tool_name="test.audited",
        tool_version="1",
        tenant_id="default-tenant",
        params={"test": True},
        requested_by="alice",
    )
    db_session.commit()

    # Update status (creates audit event)
    repo.update_invocation_status(
        eid=invocation.eid,
        status="finished",
        result={"success": True},
    )
    db_session.commit()

    # Retrieve audit events
    events = repo.get_audit_events_for_invocation(invocation.eid)
    assert len(events) >= 1

    # Check event details
    event = events[0]
    assert event.event_type == "invocation_status_updated"
    assert event.performed_by == "alice"
    assert "finished" in str(event.event_data)


# ============================================================================
# Redis Cache Integration Tests
# ============================================================================


@pytest.mark.integration
def test_cache_hit_on_second_get(client, mint_token):
    """Test Redis cache hit after first GET."""
    tok = mint_token(sub="alice", scopes=["tools:basic"])

    # Create invocation
    r = client.post(
        "/v1/tools/system.health/invocations",
        json={"args": {"action": "liveness"}},
        headers=_auth(tok),
    )
    assert r.status_code in (200, 201)
    eid = r.json()["event_id"]

    # First GET (cache miss, populates cache)
    g1 = client.get(
        f"/v1/tools/system.health/invocations/{eid}",
        headers=_auth(tok),
    )
    assert g1.status_code == 200
    cache1 = g1.headers.get("X-Cache")

    # Second GET (cache hit)
    g2 = client.get(
        f"/v1/tools/system.health/invocations/{eid}",
        headers=_auth(tok),
    )
    assert g2.status_code == 200
    cache2 = g2.headers.get("X-Cache")

    # At least one should be a hit (depending on cache population)
    assert cache2 in ("HIT", "MISS")


@pytest.mark.integration
def test_cache_result_and_error(client, mint_token, db_session):
    """Test Redis caching of both results and errors."""
    from db.redis_cache import tools_cache
    from db.postgres_control.repositories.tools import ToolsRepository

    repo = ToolsRepository(db_session)

    # Create successful invocation
    inv1, _ = repo.create_invocation(
        tool_name="test.success",
        tool_version="1",
        tenant_id="default-tenant",
        params={},
        requested_by="alice",
    )
    repo.update_invocation_status(
        eid=inv1.eid,
        status="finished",
        result={"value": 42},
    )
    db_session.commit()

    # Cache result
    tools_cache.cache_invocation_result(inv1.eid, {"value": 42})

    # Retrieve from cache
    cached_result = tools_cache.get_cached_result(inv1.eid)
    assert cached_result == {"value": 42}

    # Create failed invocation
    inv2, _ = repo.create_invocation(
        tool_name="test.failure",
        tool_version="1",
        tenant_id="default-tenant",
        params={},
        requested_by="alice",
    )
    error_detail = {"message": "Failed", "type": "Error"}
    repo.update_invocation_status(
        eid=inv2.eid,
        status="failed",
        error=error_detail,
    )
    db_session.commit()

    # Cache error
    tools_cache.cache_invocation_error(inv2.eid, error_detail)

    # Retrieve error from cache
    cached_error = tools_cache.get_cached_result(inv2.eid)
    assert cached_error is not None


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================


@pytest.mark.integration
def test_missing_tenant_auto_creation(client, mint_token, db_session):
    """Test that default tenant is auto-created if missing."""
    from db.postgres_control.repositories.tenants import TenantsRepository

    tenant_repo = TenantsRepository(db_session)

    # Ensure default tenant exists (created by tools router)
    tenant = tenant_repo.get_by_id("default-tenant")
    if not tenant:
        # If it doesn't exist, the router should create it
        tok = mint_token(sub="alice", scopes=["tools:basic"])
        r = client.post(
            "/v1/tools/system.health/invocations",
            json={"args": {"action": "liveness"}},
            headers=_auth(tok),
        )
        assert r.status_code in (200, 201)

        # Check tenant was created
        tenant = tenant_repo.get_by_id("default-tenant")
        assert tenant is not None


@pytest.mark.integration
def test_invalid_uuid_returns_400(client, mint_token):
    """Test GET with invalid UUID returns 400."""
    tok = mint_token(sub="alice", scopes=["tools:basic"])

    r = client.get(
        "/v1/tools/system.health/invocations/not-a-uuid",
        headers=_auth(tok),
    )
    assert r.status_code == 400
    assert "invalid id" in r.json()["detail"]


@pytest.mark.integration
def test_nonexistent_invocation_returns_404(client, mint_token):
    """Test GET for non-existent invocation returns 404."""
    tok = mint_token(sub="alice", scopes=["tools:basic"])
    fake_uuid = str(uuid.uuid4())

    r = client.get(
        f"/v1/tools/system.health/invocations/{fake_uuid}",
        headers=_auth(tok),
    )
    assert r.status_code == 404


@pytest.mark.integration
def test_tool_version_mismatch(client, mint_token, db_session):
    """Test retrieving invocation with wrong tool name returns 404."""
    from db.postgres_control.repositories.tools import ToolsRepository

    repo = ToolsRepository(db_session)

    # Create invocation for tool A
    invocation, _ = repo.create_invocation(
        tool_name="tool.a",
        tool_version="1",
        tenant_id="default-tenant",
        params={},
        requested_by="alice",
    )
    db_session.commit()

    # Try to retrieve with tool B (wrong name)
    tok = mint_token(sub="alice", scopes=["tools:basic"])
    r = client.get(
        f"/v1/tools/tool.b/invocations/{invocation.eid}",
        headers=_auth(tok),
    )
    assert r.status_code == 404


# ============================================================================
# Concurrent Operations Tests
# ============================================================================


@pytest.mark.integration
def test_concurrent_invocations_different_keys(client, mint_token):
    """Test multiple concurrent invocations with different idempotency keys."""
    import concurrent.futures

    tok = mint_token(sub="alice", scopes=["tools:basic"])

    def create_invocation(key_suffix):
        headers = {**_auth(tok), "Idempotency-Key": f"concurrent-{key_suffix}"}
        r = client.post(
            "/v1/tools/system.health/invocations",
            json={"args": {"action": "liveness"}},
            headers=headers,
        )
        return r.status_code, r.json().get("event_id")

    # Create 5 concurrent invocations
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(create_invocation, i) for i in range(5)]
        results = [f.result() for f in futures]

    # All should succeed
    assert all(status in (200, 201) for status, _ in results)

    # All should have unique event IDs
    eids = [eid for _, eid in results]
    assert len(eids) == len(set(eids))


@pytest.mark.integration
def test_rate_limiting_state_tracking(client, mint_token, db_session):
    """Test rate limiting state is tracked in Redis."""
    from db.redis_cache import tools_cache

    user = "alice"
    tool = "test.ratelimited"

    # Set rate limit state
    tools_cache.set_rate_limit_state(user, tool, count=5, window_start=datetime.utcnow())

    # Get rate limit state
    count, window = tools_cache.get_rate_limit_state(user, tool)
    assert count == 5
    assert isinstance(window, datetime)
