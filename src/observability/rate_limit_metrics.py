"""Prometheus metrics for rate limiting."""

from contextlib import suppress

# Try to import prometheus client, gracefully degrade if unavailable
try:
    from prometheus_client import Counter, Histogram

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

    # Stub classes for when prometheus_client is not installed
    class Counter:
        def __init__(self, *args, **kwargs):
            pass

        def labels(self, **kwargs):
            return self

        def inc(self, *args, **kwargs):
            pass

    class Histogram:
        def __init__(self, *args, **kwargs):
            pass

        def labels(self, **kwargs):
            return self

        def observe(self, *args, **kwargs):
            pass


# Rate limit counters
rate_limit_requests_total = Counter(
    "rate_limit_requests_total",
    "Total number of rate limit checks",
    ["action", "scope", "result"],  # scope: user/tenant, result: allowed/blocked
)

rate_limit_exceeded_total = Counter(
    "rate_limit_exceeded_total",
    "Total number of rate limit violations",
    ["action", "scope"],  # scope: user/tenant
)

tenant_quota_exceeded_total = Counter(
    "tenant_quota_exceeded_total",
    "Total number of tenant quota violations",
    ["action", "tenant_id"],
)

# Rate limit histogram for tracking limits
rate_limit_usage = Histogram(
    "rate_limit_usage_ratio",
    "Rate limit usage as ratio (current/limit)",
    ["action", "scope"],
    buckets=[0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99, 1.0],
)


def record_rate_limit_check(
    action: str,
    scope: str,
    allowed: bool,
    current: int = 0,
    limit: int = 1,
) -> None:
    """
    Record rate limit check metrics.

    Args:
        action: Action being rate limited (e.g., "sessions:create")
        scope: Scope of the limit ("user" or "tenant")
        allowed: Whether request was allowed
        current: Current count in window
        limit: Maximum allowed in window
    """
    if not PROMETHEUS_AVAILABLE:
        return

    with suppress(Exception):
        result = "allowed" if allowed else "blocked"
        rate_limit_requests_total.labels(
            action=action,
            scope=scope,
            result=result,
        ).inc()

        if not allowed:
            rate_limit_exceeded_total.labels(
                action=action,
                scope=scope,
            ).inc()

        # Record usage ratio
        if limit > 0:
            usage_ratio = min(current / limit, 1.0)
            rate_limit_usage.labels(
                action=action,
                scope=scope,
            ).observe(usage_ratio)


def record_tenant_quota_exceeded(action: str, tenant_id: str) -> None:
    """
    Record tenant quota violation.

    Args:
        action: Action that exceeded quota
        tenant_id: Tenant that exceeded quota
    """
    if not PROMETHEUS_AVAILABLE:
        return

    with suppress(Exception):
        tenant_quota_exceeded_total.labels(
            action=action,
            tenant_id=tenant_id,
        ).inc()
