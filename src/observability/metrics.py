"""
Prometheus metrics wiring for the Cineca Agentic Platform.

This module exposes a single public entry-point:

    setup_metrics(app: FastAPI) -> None

It creates a Prometheus registry (supporting multiprocess mode if
PROMETHEUS_MULTIPROC_DIR is set), registers default collectors, defines
a small set of application metrics, and mounts the `/metrics` endpoint.

It also exposes tiny helper functions that other parts of the app can
call to record events without having to import prometheus_client:

    record_request(method, path_template, status_code, duration_seconds)
    record_background_job(job_name, status, duration_seconds=None)

All metrics are registered against the per-app registry and are safe to
call from anywhere (they no-op until `setup_metrics` has been executed).
"""

from __future__ import annotations

import os

import structlog
from fastapi import APIRouter, FastAPI, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    GCCollector,
    Histogram,
    PlatformCollector,
    ProcessCollector,
    generate_latest,
    multiprocess,
)

MODEL_RUNTIME_COUNTER = Counter(
    "model_requests_total",
    "Count of model runtime calls",
    ["route", "provider", "instance", "status_class"],
)

MODEL_RUNTIME_HISTOGRAM = Histogram(
    "model_request_latency_ms",
    "Latency of model runtime calls (ms)",
    ["route", "provider", "instance", "status_class"],
    buckets=(5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, float("inf")),
)


log = structlog.get_logger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Per-app metric store
# ──────────────────────────────────────────────────────────────────────────────


class _MetricStore:
    """
    Lazily created set of metric objects bound to a Prometheus registry.
    """

    def __init__(self, registry: CollectorRegistry) -> None:
        # HTTP server metrics (populated by observability.middleware or routers)
        self.http_requests_total = Counter(
            "http_requests_total",
            "Total number of HTTP requests processed.",
            ["method", "path", "status"],
            registry=registry,
        )
        self.http_request_duration_seconds = Histogram(
            "http_request_duration_seconds",
            "HTTP request duration in seconds.",
            ["method", "path", "status"],
            # Reasonable default buckets for API latencies
            buckets=(
                0.005,
                0.01,
                0.025,
                0.05,
                0.1,
                0.25,
                0.5,
                1.0,
                2.5,
                5.0,
                10.0,
            ),
            registry=registry,
        )

        # Background jobs / tasks
        self.background_jobs_total = Counter(
            "background_jobs_total",
            "Background jobs executed, labeled by job name and outcome.",
            ["job", "status"],
            registry=registry,
        )
        self.background_job_duration_seconds = Histogram(
            "background_job_duration_seconds",
            "Background job duration in seconds.",
            ["job", "status"],
            buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
            registry=registry,
        )

        # Static service info (export version, set to 1)
        from src import __version__  # local import to avoid import cycles at module load

        self.service_info = Gauge(
            "service_info",
            "Static service information (value is always 1).",
            ["version"],
            registry=registry,
        )
        self.service_info.labels(version=__version__).set(1)

        # Tools metrics
        self.tools_invocations_total = Counter(
            "tools_invocations_total",
            "Total number of tool invocations.",
            ["tool_name", "status", "tenant_id"],
            registry=registry,
        )
        self.tools_invocation_duration_seconds = Histogram(
            "tools_invocation_duration_seconds",
            "Tool invocation duration in seconds.",
            ["tool_name", "status"],
            buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
            registry=registry,
        )
        self.tools_queue_depth = Gauge(
            "tools_queue_depth",
            "Current number of pending invocations in tool queue.",
            ["tool_name"],
            registry=registry,
        )
        self.tools_cache_operations_total = Counter(
            "tools_cache_operations_total",
            "Total number of Redis cache operations for tools.",
            ["operation", "result"],  # operation: get/set/delete, result: hit/miss/success/error
            registry=registry,
        )
        self.tools_idempotency_conflicts_total = Counter(
            "tools_idempotency_conflicts_total",
            "Total number of idempotency key conflicts (409 responses).",
            ["tool_name"],
            registry=registry,
        )

        # Intent classification metrics
        self.intent_classification_total = Counter(
            "intent_classification_total",
            "Total number of intent classifications performed.",
            ["mode", "source", "adjusted"],  # mode: chat/graph/etc, source: pattern/catalog/llm, adjusted: true/false
            registry=registry,
        )
        self.intent_classification_duration_seconds = Histogram(
            "intent_classification_duration_seconds",
            "Intent classification duration in seconds.",
            ["mode", "source"],
            buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
            registry=registry,
        )
        self.intent_classification_confidence = Histogram(
            "intent_classification_confidence",
            "Distribution of intent classification confidence scores.",
            ["mode", "source"],
            buckets=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
            registry=registry,
        )
        self.intent_pattern_matches_total = Counter(
            "intent_pattern_matches_total",
            "Total number of pattern matches by pattern group.",
            ["pattern_group"],  # chat, greeting, graph, security, admin, dangerous, meta
            registry=registry,
        )
        self.intent_llm_fallback_total = Counter(
            "intent_llm_fallback_total",
            "Total number of LLM fallback classifications.",
            ["success"],  # true/false
            registry=registry,
        )
        self.intent_rbac_adjustments_total = Counter(
            "intent_rbac_adjustments_total",
            "Total number of RBAC-based intent adjustments.",
            ["original_mode", "adjusted_mode", "role"],
            registry=registry,
        )


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────


def setup_metrics(app: FastAPI) -> None:
    """
    Initialize Prometheus metrics for the provided FastAPI app.

    - Creates/attaches `app.state.prometheus_registry`
    - Registers default collectors (Process/Platform/GC)
    - Creates/attaches `app.state.metrics` (an instance of `_MetricStore`)
    - Mounts `/metrics` endpoint (GET), excluded from OpenAPI schema
    """
    if getattr(app.state, "prometheus_registry", None) is not None:
        # Already configured for this app
        log.debug("observability.metrics.already_configured")
        return

    registry = _build_registry()
    _register_default_collectors(registry)

    # Create metric store bound to this registry
    store = _MetricStore(registry=registry)

    # Expose endpoint
    router = APIRouter()

    @router.get("/metrics", include_in_schema=False)
    async def metrics_endpoint() -> Response:  # pragma: no cover - trivial glue
        data = generate_latest(registry)
        return Response(content=data, media_type=CONTENT_TYPE_LATEST)

    app.include_router(router)

    # Attach to app state for later access
    app.state.prometheus_registry = registry
    app.state.metrics = store

    log.info(
        "observability.metrics.configured",
        multiprocess=bool(os.getenv("PROMETHEUS_MULTIPROC_DIR")),
    )


def record_request(
    method: str,
    path_template: str,
    status_code: int | str,
    duration_seconds: float,
    app: FastAPI | None = None,
) -> None:
    """
    Update request counters/histograms if metrics were set up.

    `path_template` should be the parameterized route path
    (e.g. `/items/{item_id}`) to avoid high-cardinality labels.
    """
    store = _get_store(app)
    if not store:
        log.debug("observability.metrics.record_request_skipped", app_provided=bool(app))
        return
    status = str(status_code)
    try:
        log.debug("observability.metrics.recording", method=method, path=path_template, status=status)
        store.http_requests_total.labels(method, path_template, status).inc()
        store.http_request_duration_seconds.labels(method, path_template, status).observe(
            max(0.0, float(duration_seconds))
        )
        log.debug("observability.metrics.recorded", method=method, path=path_template, status=status)
    except Exception as e:  # pragma: no cover
        log.warning("observability.metrics.record_request_failed", error=str(e))


def record_background_job(
    job_name: str,
    status: str,
    duration_seconds: float | None = None,
    app: FastAPI | None = None,
) -> None:
    """
    Update background job counters/histograms if metrics were set up.
    """
    store = _get_store(app)
    if not store:
        return
    try:
        store.background_jobs_total.labels(job_name, status).inc()
        if duration_seconds is not None:
            store.background_job_duration_seconds.labels(job_name, status).observe(max(0.0, float(duration_seconds)))
    except Exception as e:  # pragma: no cover
        log.warning("observability.metrics.record_job_failed", error=str(e))


def record_tool_invocation(
    tool_name: str,
    status: str,
    duration_seconds: float | None = None,
    tenant_id: str = "default-tenant",
    app: FastAPI | None = None,
) -> None:
    """
    Update tool invocation counters/histograms if metrics were set up.

    Args:
        tool_name: Name of the tool being invoked
        status: Status of the invocation (pending, running, finished, failed)
        duration_seconds: Duration in seconds (optional, for histograms)
        tenant_id: Tenant identifier (default: "default-tenant")
        app: FastAPI app instance (optional)
    """
    store = _get_store(app)
    if not store:
        return
    try:
        store.tools_invocations_total.labels(tool_name, status, tenant_id).inc()
        if duration_seconds is not None:
            store.tools_invocation_duration_seconds.labels(tool_name, status).observe(max(0.0, float(duration_seconds)))
    except Exception as e:  # pragma: no cover
        log.warning("observability.metrics.record_tool_invocation_failed", error=str(e))


def record_tool_cache_operation(
    operation: str,
    result: str,
    app: FastAPI | None = None,
) -> None:
    """
    Update tool cache operation counters.

    Args:
        operation: Type of cache operation (get, set, delete)
        result: Result of the operation (hit, miss, success, error)
        app: FastAPI app instance (optional)
    """
    store = _get_store(app)
    if not store:
        return
    try:
        store.tools_cache_operations_total.labels(operation, result).inc()
    except Exception as e:  # pragma: no cover
        log.warning("observability.metrics.record_cache_op_failed", error=str(e))


def record_tool_idempotency_conflict(
    tool_name: str,
    app: FastAPI | None = None,
) -> None:
    """
    Update idempotency conflict counter (409 responses).

    Args:
        tool_name: Name of the tool with conflict
        app: FastAPI app instance (optional)
    """
    store = _get_store(app)
    if not store:
        return
    try:
        store.tools_idempotency_conflicts_total.labels(tool_name).inc()
    except Exception as e:  # pragma: no cover
        log.warning("observability.metrics.record_idempotency_conflict_failed", error=str(e))


def update_tool_queue_depth(
    tool_name: str,
    depth: int,
    app: FastAPI | None = None,
) -> None:
    """
    Set the current queue depth gauge for a tool.

    Args:
        tool_name: Name of the tool
        depth: Number of pending invocations
        app: FastAPI app instance (optional)
    """
    store = _get_store(app)
    if not store:
        return
    try:
        store.tools_queue_depth.labels(tool_name).set(max(0, int(depth)))
    except Exception as e:  # pragma: no cover
        log.warning("observability.metrics.update_queue_depth_failed", error=str(e))


def record_intent_classification(
    mode: str,
    source: str,
    confidence: float,
    duration_seconds: float | None = None,
    adjusted: bool = False,
    app: FastAPI | None = None,
) -> None:
    """
    Record an intent classification event.

    Args:
        mode: The classified intent mode (chat, graph, security, admin, etc.)
        source: Classification source (pattern, catalog, llm, default)
        confidence: Confidence score (0.0 to 1.0)
        duration_seconds: Classification duration in seconds (optional)
        adjusted: Whether the classification was adjusted by RBAC
        app: FastAPI app instance (optional)
    """
    store = _get_store(app)
    if not store:
        return
    try:
        adjusted_str = "true" if adjusted else "false"
        store.intent_classification_total.labels(mode, source, adjusted_str).inc()
        store.intent_classification_confidence.labels(mode, source).observe(
            max(0.0, min(1.0, float(confidence)))
        )
        if duration_seconds is not None:
            store.intent_classification_duration_seconds.labels(mode, source).observe(
                max(0.0, float(duration_seconds))
            )
    except Exception as e:  # pragma: no cover
        log.warning("observability.metrics.record_intent_classification_failed", error=str(e))


def record_intent_pattern_match(
    pattern_group: str,
    app: FastAPI | None = None,
) -> None:
    """
    Record a pattern match event during intent classification.

    Args:
        pattern_group: Name of the pattern group that matched (chat, greeting, graph, etc.)
        app: FastAPI app instance (optional)
    """
    store = _get_store(app)
    if not store:
        return
    try:
        store.intent_pattern_matches_total.labels(pattern_group).inc()
    except Exception as e:  # pragma: no cover
        log.warning("observability.metrics.record_pattern_match_failed", error=str(e))


def record_intent_llm_fallback(
    success: bool,
    app: FastAPI | None = None,
) -> None:
    """
    Record an LLM fallback classification attempt.

    Args:
        success: Whether the LLM fallback was successful
        app: FastAPI app instance (optional)
    """
    store = _get_store(app)
    if not store:
        return
    try:
        success_str = "true" if success else "false"
        store.intent_llm_fallback_total.labels(success_str).inc()
    except Exception as e:  # pragma: no cover
        log.warning("observability.metrics.record_llm_fallback_failed", error=str(e))


def record_intent_rbac_adjustment(
    original_mode: str,
    adjusted_mode: str,
    role: str,
    app: FastAPI | None = None,
) -> None:
    """
    Record an RBAC-based intent adjustment.

    Args:
        original_mode: The original classified mode before adjustment
        adjusted_mode: The adjusted mode after RBAC check
        role: The user's role that triggered the adjustment
        app: FastAPI app instance (optional)
    """
    store = _get_store(app)
    if not store:
        return
    try:
        store.intent_rbac_adjustments_total.labels(original_mode, adjusted_mode, role).inc()
    except Exception as e:  # pragma: no cover
        log.warning("observability.metrics.record_rbac_adjustment_failed", error=str(e))


# ──────────────────────────────────────────────────────────────────────────────
# Internals
# ──────────────────────────────────────────────────────────────────────────────


def _build_registry() -> CollectorRegistry:
    """
    Create a CollectorRegistry. If PROMETHEUS_MULTIPROC_DIR is set, configure
    the multiprocess collector. This registry is *not* the global default so
    tests and local runs remain isolated.
    """
    registry = CollectorRegistry()

    multiproc_dir = os.getenv("PROMETHEUS_MULTIPROC_DIR")
    if multiproc_dir:
        # In multiprocess mode, the MultiProcessCollector will read from the
        # shared dir and expose consolidated metrics.
        multiprocess.MultiProcessCollector(registry)
        log.info("observability.metrics.multiprocess_enabled", dir=multiproc_dir)

    return registry


def _register_default_collectors(registry: CollectorRegistry) -> None:
    """
    Register default process/platform/gc collectors unless in multiprocess mode,
    where process/platform metrics are provided by MultiProcessCollector.
    """
    if os.getenv("PROMETHEUS_MULTIPROC_DIR"):
        # MultiProcessCollector handles process/platform metrics.
        GCCollector(registry=registry)
    else:
        ProcessCollector(registry=registry)
        PlatformCollector(registry=registry)
        GCCollector(registry=registry)


def _get_store(app: FastAPI | None) -> _MetricStore | None:
    """
    Retrieve the metric store from the provided app or from the most recent
    configured FastAPI app via a weak reference (only if available).

    We intentionally avoid a global singleton of the store to keep metrics
    registries per-app. If `app` is not provided, we do a best-effort lookup.
    """
    # Preferred: explicit app
    if app is not None:
        return getattr(app.state, "metrics", None)

    # Best-effort implicit: last configured store (cached on this module)
    return globals().get("_last_metric_store")  # type: ignore[return-value]


# Keep a weak-ish handle to the last configured store for convenience when an
# explicit app isn't provided — we update it during setup.
def _remember_store(store: _MetricStore) -> None:
    globals()["_last_metric_store"] = store


# Patch setup_metrics to remember a store reference (without changing signature)
_orig_setup_metrics = setup_metrics


def setup_metrics(app: FastAPI) -> None:  # type: ignore[override]
    _orig_setup_metrics(app)
    store = getattr(app.state, "metrics", None)
    if isinstance(store, _MetricStore):
        _remember_store(store)


__all__ = [
    "MODEL_RUNTIME_COUNTER",
    "MODEL_RUNTIME_HISTOGRAM",
    "record_background_job",
    "record_intent_classification",
    "record_intent_llm_fallback",
    "record_intent_pattern_match",
    "record_intent_rbac_adjustment",
    "record_request",
    "record_tool_cache_operation",
    "record_tool_idempotency_conflict",
    "record_tool_invocation",
    "setup_metrics",
    "update_tool_queue_depth",
]
