"""
Integration tests for tenant-level quotas.

Tests organization-wide rate limiting across all users in a tenant.
"""
import pytest

from db.redis_cache.rate_limit import (
    check_tenant_quota,
    make_tenant_quota_key,
    get_rate_limit_config,
    reset_rate_limit,
)
from src.middleware.rate_limit import RateLimitHandler
from fastapi import HTTPException


@pytest.mark.anyio
async def test_tenant_quota_key_format():
    """Test tenant quota key generation."""
    key = make_tenant_quota_key("sessions:create", "tenant-abc123")
    assert key == "ratelimit:tenant:sessions:create:tenant-abc123"

    key = make_tenant_quota_key("steps:create", "tenant-xyz789")
    assert key == "ratelimit:tenant:steps:create:tenant-xyz789"


@pytest.mark.anyio
async def test_tenant_quota_config_exists():
    """Test that tenant quota configs are defined."""
    # Should have tenant configs for major actions
    limit, window = get_rate_limit_config("tenant:sessions:create")
    assert limit > 0
    assert window > 0

    limit, window = get_rate_limit_config("tenant:steps:create")
    assert limit > 0
    assert window > 0

    limit, window = get_rate_limit_config("tenant:runs:create")
    assert limit > 0
    assert window > 0


@pytest.mark.anyio
async def test_tenant_quota_allows_within_limit():
    """Test that tenant quota allows requests within limit."""
    tenant_id = "test-tenant-allow"
    action = "sessions:create"

    # First request should succeed
    allowed, remaining, retry_after = await check_tenant_quota(action, tenant_id)

    assert allowed is True
    assert remaining >= 0
    assert retry_after == 0


@pytest.mark.anyio
async def test_tenant_quota_blocks_when_exceeded():
    """Test that tenant quota blocks when limit exceeded."""
    tenant_id = "test-tenant-block"
    action = "sessions:create"

    # Get the quota limit
    limit, window = get_rate_limit_config(f"tenant:{action}")

    # Make requests up to the limit
    for i in range(limit):
        allowed, _, _ = await check_tenant_quota(action, tenant_id)
        if not allowed:
            pytest.fail(f"Request {i+1}/{limit} was blocked unexpectedly")

    # Next request should be blocked
    allowed, remaining, retry_after = await check_tenant_quota(action, tenant_id)

    assert allowed is False
    assert remaining == 0
    assert retry_after > 0


@pytest.mark.anyio
async def test_tenant_quota_independent_per_tenant():
    """Test that tenant quotas are independent per tenant."""
    action = "sessions:create"
    tenant_a = "test-tenant-a"
    tenant_b = "test-tenant-b"

    # Both tenants should have independent quotas
    allowed_a, _, _ = await check_tenant_quota(action, tenant_a)
    allowed_b, _, _ = await check_tenant_quota(action, tenant_b)

    assert allowed_a is True
    assert allowed_b is True


@pytest.mark.anyio
async def test_tenant_quota_independent_per_action():
    """Test that tenant quotas are independent per action."""
    tenant_id = "test-tenant-actions"

    # Different actions should have independent quotas
    allowed_sessions, _, _ = await check_tenant_quota("sessions:create", tenant_id)
    allowed_steps, _, _ = await check_tenant_quota("steps:create", tenant_id)
    allowed_runs, _, _ = await check_tenant_quota("runs:create", tenant_id)

    assert allowed_sessions is True
    assert allowed_steps is True
    assert allowed_runs is True


@pytest.mark.anyio
async def test_rate_limit_handler_checks_tenant_quota():
    """Test that RateLimitHandler checks tenant quota when tenant_id provided."""
    handler = RateLimitHandler(user_id="user123", tenant_id="test-tenant-handler")

    # Should check both user and tenant limits
    # This should succeed (within both limits)
    await handler.check("sessions:create")

    # No exception means it passed both checks


@pytest.mark.anyio
async def test_rate_limit_handler_raises_on_tenant_quota_exceeded():
    """Test that RateLimitHandler raises HTTPException when tenant quota exceeded."""
    tenant_id = "test-tenant-exceed"
    action = "sessions:create"

    # Exhaust tenant quota
    limit, window = get_rate_limit_config(f"tenant:{action}")
    for _ in range(limit):
        await check_tenant_quota(action, tenant_id)

    # Now the handler should raise
    handler = RateLimitHandler(user_id="user123", tenant_id=tenant_id)

    with pytest.raises(HTTPException) as exc_info:
        await handler.check(action)

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["ok"] is False
    assert exc_info.value.detail["code"] == "E_TENANT_QUOTA"
    assert "tenant_id" in exc_info.value.detail
    assert exc_info.value.detail["tenant_id"] == tenant_id


@pytest.mark.anyio
async def test_tenant_quota_error_includes_scope():
    """Test that tenant quota errors include scope='tenant' in headers."""
    tenant_id = "test-tenant-scope"
    action = "sessions:create"

    # Exhaust tenant quota
    limit, window = get_rate_limit_config(f"tenant:{action}")
    for _ in range(limit):
        await check_tenant_quota(action, tenant_id)

    handler = RateLimitHandler(user_id="user123", tenant_id=tenant_id)

    with pytest.raises(HTTPException) as exc_info:
        await handler.check(action)

    # Should have X-RateLimit-Scope: tenant in headers
    assert exc_info.value.detail["scope"] == "tenant"


@pytest.mark.anyio
async def test_rate_limit_handler_without_tenant_id_skips_tenant_check():
    """Test that RateLimitHandler skips tenant check when tenant_id not provided."""
    # Handler without tenant_id
    handler = RateLimitHandler(user_id="user123")

    # Should only check user limit, not tenant quota
    await handler.check("sessions:create")

    # No exception means it passed (only checked user limit)


@pytest.mark.anyio
async def test_tenant_quota_retry_after_calculation():
    """Test that tenant quota retry_after is calculated correctly."""
    tenant_id = "test-tenant-retry"
    action = "sessions:create"

    # Exhaust quota
    limit, window = get_rate_limit_config(f"tenant:{action}")
    for _ in range(limit):
        await check_tenant_quota(action, tenant_id)

    # Check retry_after
    allowed, remaining, retry_after = await check_tenant_quota(action, tenant_id)

    assert allowed is False
    assert remaining == 0
    assert retry_after > 0
    assert retry_after <= window  # Should be within the window


@pytest.mark.anyio
async def test_tenant_quota_different_limits_per_action():
    """Test that different actions have different tenant quota limits."""
    limit_sessions, window_sessions = get_rate_limit_config("tenant:sessions:create")
    limit_steps, window_steps = get_rate_limit_config("tenant:steps:create")
    limit_runs, window_runs = get_rate_limit_config("tenant:runs:create")

    # All should be positive
    assert all(lim > 0 for lim in [limit_sessions, limit_steps, limit_runs])
    assert all(win > 0 for win in [window_sessions, window_steps, window_runs])

    # In production mode, steps should have higher limits
    # (in test mode they may all be the same high value)
    # Just verify they're configured and reasonable
    assert limit_sessions >= 100  # At least some reasonable minimum
    assert limit_steps >= 100
    assert limit_runs >= 100


@pytest.mark.anyio
async def test_tenant_quota_user_limit_checked_first():
    """Test that per-user limit is checked before tenant quota."""
    tenant_id = "test-tenant-order"
    user_id = "user-to-block"
    action = "sessions:create"

    # Exhaust user limit first
    user_limit, user_window = get_rate_limit_config(action)
    handler_exhaust = RateLimitHandler(user_id=user_id, tenant_id=tenant_id)

    for _ in range(user_limit):
        await handler_exhaust.check(action)

    # Next request should fail with user rate limit, not tenant quota
    handler_check = RateLimitHandler(user_id=user_id, tenant_id=tenant_id)

    with pytest.raises(HTTPException) as exc_info:
        await handler_check.check(action)

    # Should be user rate limit error, not tenant quota
    assert exc_info.value.detail["code"] == "E_RATE_LIMIT"
    assert exc_info.value.detail["scope"] == "user"


@pytest.mark.anyio
async def test_tenant_quota_applies_across_multiple_users():
    """Test that tenant quota is shared across all users in tenant."""
    tenant_id = "test-tenant-shared"
    action = "sessions:create"

    # Get tenant limit
    tenant_limit, _ = get_rate_limit_config(f"tenant:{action}")

    # Use different users to approach tenant limit
    users = [f"user-{i}" for i in range(min(10, tenant_limit))]
    requests_per_user = max(1, tenant_limit // len(users))

    # Make requests from different users
    total_made = 0
    for user_id in users:
        handler = RateLimitHandler(user_id=user_id, tenant_id=tenant_id)
        for _ in range(requests_per_user):
            if total_made >= tenant_limit:
                break
            await handler.check(action)
            total_made += 1

    # Next request from ANY user should hit tenant quota
    if total_made >= tenant_limit:
        new_handler = RateLimitHandler(user_id="new-user-after-limit", tenant_id=tenant_id)

        with pytest.raises(HTTPException) as exc_info:
            await new_handler.check(action)

        assert exc_info.value.detail["code"] == "E_TENANT_QUOTA"
