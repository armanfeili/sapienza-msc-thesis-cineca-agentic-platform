"""
Job Store Metrics

Prometheus instrumentation for job storage operations.
Tracks create/get/list latencies, SSE connections, and backend health.
"""

import asyncio
import time
from collections.abc import Callable
from functools import wraps
from typing import Any

from prometheus_client import Counter, Gauge, Histogram, Info

# Job operation counters
job_create_total = Counter(
    "job_create_total", "Total job creations", ["backend", "status"]  # status: success, idempotent_replay, failed
)

job_get_total = Counter("job_get_total", "Total job retrievals", ["backend", "status"])  # status: hit, miss

job_list_total = Counter("job_list_total", "Total job list queries", ["backend", "scope"])  # scope: user, admin

job_cancel_total = Counter(
    "job_cancel_total", "Total job cancellations", ["backend", "first_time"]  # first_time: true (202), false (200)
)

# Latency histograms
job_create_duration_seconds = Histogram(
    "job_create_duration_seconds",
    "Job creation latency",
    ["backend"],
    buckets=(0.001, 0.005, 0.010, 0.025, 0.050, 0.100, 0.250, 0.500, 1.0, 2.5, 5.0),
)

job_get_duration_seconds = Histogram(
    "job_get_duration_seconds",
    "Job retrieval latency",
    ["backend"],
    buckets=(0.001, 0.005, 0.010, 0.025, 0.050, 0.100, 0.250, 0.500, 1.0),
)

job_list_duration_seconds = Histogram(
    "job_list_duration_seconds",
    "Job list query latency",
    ["backend", "scope"],
    buckets=(0.001, 0.005, 0.010, 0.025, 0.050, 0.100, 0.250, 0.500, 1.0, 2.5),
)

job_cancel_duration_seconds = Histogram(
    "job_cancel_duration_seconds",
    "Job cancellation latency",
    ["backend"],
    buckets=(0.001, 0.005, 0.010, 0.025, 0.050, 0.100, 0.250, 0.500, 1.0),
)

# SSE metrics
sse_connections_active = Gauge("sse_connections_active", "Active SSE connections", ["backend"])

sse_resume_hits_total = Counter("sse_resume_hits_total", "Successful Last-Event-ID resumes", ["backend"])

sse_gap_events_total = Counter("sse_gap_events_total", "SSE ring buffer gaps (no backlog)", ["backend"])

sse_heartbeat_total = Counter("sse_heartbeat_total", "SSE heartbeats sent", ["backend"])

sse_terminal_events_total = Counter(
    "sse_terminal_events_total",
    "SSE terminal end events",
    ["backend", "status"],  # status: finished, failed, cancelled, disappeared
)

# Backend health
job_backend_info = Info("job_backend", "Current job storage backend")

redis_operations_total = Counter(
    "redis_operations_total",
    "Total Redis operations",
    ["operation", "status"],  # operation: get, set, delete, etc.; status: success, error
)

redis_connection_errors_total = Counter("redis_connection_errors_total", "Redis connection errors", ["error_type"])

# Store-level metrics
idempotency_checks_total = Counter(
    "idempotency_checks_total", "Idempotency key checks", ["backend", "result"]  # result: hit, miss
)

index_orphans_cleaned_total = Counter(
    "index_orphans_cleaned_total", "Orphaned ZSET members cleaned", ["index_type"]  # index_type: all, owner, status
)


def track_job_create(backend: str):
    """Decorator to track job creation metrics."""

    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args, **kwargs) -> Any:
                start = time.time()
                status = "failed"
                try:
                    result = await func(*args, **kwargs)
                    status = "success"
                    return result
                finally:
                    duration = time.time() - start
                    job_create_duration_seconds.labels(backend=backend).observe(duration)
                    job_create_total.labels(backend=backend, status=status).inc()

            return async_wrapper
        else:

            @wraps(func)
            def sync_wrapper(*args, **kwargs) -> Any:
                start = time.time()
                status = "failed"
                try:
                    result = func(*args, **kwargs)
                    status = "success"
                    return result
                finally:
                    duration = time.time() - start
                    job_create_duration_seconds.labels(backend=backend).observe(duration)
                    job_create_total.labels(backend=backend, status=status).inc()

            return sync_wrapper

    return decorator


def track_job_get(backend: str):
    """Decorator to track job retrieval metrics."""

    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args, **kwargs) -> Any:
                start = time.time()
                status = "miss"
                try:
                    result = await func(*args, **kwargs)
                    status = "hit" if result else "miss"
                    return result
                finally:
                    duration = time.time() - start
                    job_get_duration_seconds.labels(backend=backend).observe(duration)
                    job_get_total.labels(backend=backend, status=status).inc()

            return async_wrapper
        else:

            @wraps(func)
            def sync_wrapper(*args, **kwargs) -> Any:
                start = time.time()
                status = "miss"
                try:
                    result = func(*args, **kwargs)
                    status = "hit" if result else "miss"
                    return result
                finally:
                    duration = time.time() - start
                    job_get_duration_seconds.labels(backend=backend).observe(duration)
                    job_get_total.labels(backend=backend, status=status).inc()

            return sync_wrapper

    return decorator


def track_job_list(backend: str, scope: str):
    """Decorator to track job list metrics."""

    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args, **kwargs) -> Any:
                start = time.time()
                try:
                    return await func(*args, **kwargs)
                finally:
                    duration = time.time() - start
                    job_list_duration_seconds.labels(backend=backend, scope=scope).observe(duration)
                    job_list_total.labels(backend=backend, scope=scope).inc()

            return async_wrapper
        else:

            @wraps(func)
            def sync_wrapper(*args, **kwargs) -> Any:
                start = time.time()
                try:
                    return func(*args, **kwargs)
                finally:
                    duration = time.time() - start
                    job_list_duration_seconds.labels(backend=backend, scope=scope).observe(duration)
                    job_list_total.labels(backend=backend, scope=scope).inc()

            return sync_wrapper

    return decorator


def track_sse_connection(backend: str):
    """Context manager to track SSE connection lifecycle."""

    class SSEConnectionTracker:
        def __enter__(self):
            sse_connections_active.labels(backend=backend).inc()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            sse_connections_active.labels(backend=backend).dec()

    return SSEConnectionTracker()


def record_sse_resume(backend: str):
    """Record successful SSE resume from Last-Event-ID."""
    sse_resume_hits_total.labels(backend=backend).inc()


def record_sse_gap(backend: str):
    """Record SSE gap (no backlog available)."""
    sse_gap_events_total.labels(backend=backend).inc()


def record_sse_heartbeat(backend: str):
    """Record SSE heartbeat sent."""
    sse_heartbeat_total.labels(backend=backend).inc()


def record_sse_terminal(backend: str, status: str):
    """Record SSE terminal end event."""
    sse_terminal_events_total.labels(backend=backend, status=status).inc()


def record_idempotency_check(backend: str, hit: bool):
    """Record idempotency key check result."""
    result = "hit" if hit else "miss"
    idempotency_checks_total.labels(backend=backend, result=result).inc()


def record_redis_operation(operation: str, success: bool = True):
    """Record Redis operation."""
    status = "success" if success else "error"
    redis_operations_total.labels(operation=operation, status=status).inc()


def record_redis_error(error_type: str):
    """Record Redis connection error."""
    redis_connection_errors_total.labels(error_type=error_type).inc()


def record_index_cleanup(index_type: str, count: int):
    """Record orphaned index cleanup."""
    index_orphans_cleaned_total.labels(index_type=index_type).inc(count)


def set_backend_info(backend: str, redis_url: str | None = None):
    """Set current backend info metric."""
    info = {"backend": backend}
    if redis_url:
        # Sanitize URL (remove credentials)
        sanitized_url = redis_url.split("@")[-1] if "@" in redis_url else redis_url
        info["redis_url"] = sanitized_url
    job_backend_info.info(info)
