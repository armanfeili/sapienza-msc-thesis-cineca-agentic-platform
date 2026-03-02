"""
OpenTelemetry tracing setup for the Cineca Agentic Platform.

This module provides a small, defensive wrapper around OpenTelemetry so the
application can run even when OTel libs are not installed or tracing is
disabled via configuration.

Key features
- Idempotent initialization (safe to call multiple times)
- OTLP exporter over gRPC (4317) or HTTP/protobuf (4318)
- Environment/resource attributes (service name, version, environment)
- FastAPI + Requests + Logging instrumentation (when available)
- Graceful no-op if OTEL is disabled or dependencies are missing
"""

from __future__ import annotations

import os
import socket
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from opentelemetry.trace import TracerProvider

try:
    # Core SDK & API
    from opentelemetry import trace as otel_trace  # type: ignore
    from opentelemetry.sdk.resources import Resource  # type: ignore
    from opentelemetry.sdk.trace import TracerProvider  # type: ignore
    from opentelemetry.sdk.trace.export import (  # type: ignore
        BatchSpanProcessor,
        ConsoleSpanExporter,
        SimpleSpanProcessor,
    )
    from opentelemetry.sdk.trace.sampling import (  # type: ignore
        AlwaysOnSampler,
        ParentBased,
        TraceIdRatioBased,
    )

    # Exporters
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # type: ignore
            OTLPSpanExporter as OTLPGrpcSpanExporter,
        )
    except Exception:  # pragma: no cover - optional
        OTLPGrpcSpanExporter = None  # type: ignore

    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # type: ignore
            OTLPSpanExporter as OTLPHttpSpanExporter,
        )
    except Exception:  # pragma: no cover - optional
        OTLPHttpSpanExporter = None  # type: ignore

    # Instrumentations (optional)
    try:
        from opentelemetry.instrumentation.fastapi import (  # type: ignore
            FastAPIInstrumentor,
        )
    except Exception:  # pragma: no cover - optional
        FastAPIInstrumentor = None  # type: ignore

    try:
        from opentelemetry.instrumentation.requests import (  # type: ignore
            RequestsInstrumentor,
        )
    except Exception:  # pragma: no cover - optional
        RequestsInstrumentor = None  # type: ignore

    try:
        from opentelemetry.instrumentation.logging import (  # type: ignore
            LoggingInstrumentor,
        )
    except Exception:  # pragma: no cover - optional
        LoggingInstrumentor = None  # type: ignore

    _OTEL_AVAILABLE = True
except Exception:  # pragma: no cover - if OTel not installed
    _OTEL_AVAILABLE = False

# Local config/version (both optional for loose coupling)
try:
    from src.config import settings  # type: ignore
except Exception:  # pragma: no cover - fallback defaults

    class _FallbackSettings:  # minimal shim
        APP_NAME = "cineca-agentic-platform"
        APP_ENV = os.getenv("APP_ENV", "dev")
        OTEL_ENABLED = os.getenv("OTEL_ENABLED", "false").lower() == "true"
        OTEL_EXPORTER_OTLP_PROTOCOL = os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")
        # Default gRPC: 4317; HTTP/protobuf: 4318
        OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv(
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "http://otel-collector:4317",
        )
        OTEL_CONSOLE_EXPORTER = os.getenv("OTEL_CONSOLE_EXPORTER", "false").lower() == "true"
        OTEL_SAMPLER_RATIO = float(os.getenv("OTEL_SAMPLER_RATIO", "1.0"))

    settings = _FallbackSettings()  # type: ignore

try:
    from src import __version__  # type: ignore
except Exception:  # pragma: no cover - fallback version
    __version__ = "0.1.0"

log = structlog.get_logger(__name__)

_INITIALIZED: bool = False
_PROVIDER: TracerProvider | None = None


def _build_resource() -> Resource:
    """
    Construct a Resource with standard semantic attributes.
    """
    hostname = socket.gethostname()
    attrs = {
        "service.name": getattr(settings, "APP_NAME", "cineca-agentic-platform"),
        "service.version": __version__,
        "service.instance.id": hostname,
        "deployment.environment": getattr(settings, "APP_ENV", "dev"),
        "host.name": hostname,
    }
    return Resource.create(attrs)


def _select_sampler() -> ParentBased:
    """
    Choose a sampler:
    - prod: ParentBased(TraceIdRatioBased(X)) where X from OTEL_SAMPLER_RATIO (default 0.2)
    - non-prod: ParentBased(AlwaysOn)
    """
    env = getattr(settings, "APP_ENV", "dev").lower()
    if env in {"prod", "production"}:
        ratio = float(getattr(settings, "OTEL_SAMPLER_RATIO", 0.2))
        ratio = max(0.0, min(1.0, ratio))
        return ParentBased(TraceIdRatioBased(ratio))
    return ParentBased(AlwaysOnSampler())


def _make_exporter() -> object | None:
    """
    Create an OTLP exporter according to protocol and endpoint.
    Returns None if exporter cannot be constructed.
    """
    protocol = str(getattr(settings, "OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")).lower()
    endpoint = str(getattr(settings, "OTEL_EXPORTER_OTLP_ENDPOINT", "")).strip() or (
        "http://otel-collector:4317" if protocol == "grpc" else "http://otel-collector:4318/v1/traces"
    )

    if protocol in {"grpc", "otlp", "otlp_grpc"}:
        if OTLPGrpcSpanExporter is None:  # pragma: no cover
            log.warning("opentelemetry OTLP gRPC exporter not available")
            return None
        # Determine TLS from scheme
        insecure = endpoint.startswith("http://")
        return OTLPGrpcSpanExporter(endpoint=endpoint, insecure=insecure)

    # Default to HTTP/protobuf
    if OTLPHttpSpanExporter is None:  # pragma: no cover
        log.warning("opentelemetry OTLP HTTP exporter not available")
        return None
    return OTLPHttpSpanExporter(endpoint=endpoint)


def setup_tracing(app=None) -> bool:
    """
    Initialize OpenTelemetry tracing if enabled in configuration.

    Returns:
        bool: True if tracing is active, False if no-op (disabled or unavailable).
    """
    global _INITIALIZED, _PROVIDER

    if _INITIALIZED:
        return _PROVIDER is not None

    if not getattr(settings, "OTEL_ENABLED", False):
        log.info("otel.tracing.disabled")
        _INITIALIZED = True
        _PROVIDER = None
        return False

    if not _OTEL_AVAILABLE:  # pragma: no cover
        log.warning("otel.tracing.requested_but_unavailable")
        _INITIALIZED = True
        _PROVIDER = None
        return False

    try:
        resource = _build_resource()
        sampler = _select_sampler()
        provider = TracerProvider(resource=resource, sampler=sampler)

        # Primary OTLP exporter
        exporter = _make_exporter()
        if exporter is not None:
            provider.add_span_processor(BatchSpanProcessor(exporter))
            log.info(
                "otel.tracing.exporter.enabled",
                protocol=getattr(settings, "OTEL_EXPORTER_OTLP_PROTOCOL", "grpc"),
                endpoint=getattr(settings, "OTEL_EXPORTER_OTLP_ENDPOINT", None),
            )
        else:
            log.warning("otel.tracing.no_exporter_configured")

        # Optional console exporter for local debugging
        if getattr(settings, "OTEL_CONSOLE_EXPORTER", False):
            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
            log.info("otel.tracing.console_exporter.enabled")

        # Install provider globally
        otel_trace.set_tracer_provider(provider)
        _PROVIDER = provider

        # Instrumentations (all optional)
        if FastAPIInstrumentor is not None and app is not None:
            try:
                FastAPIInstrumentor().instrument_app(app, tracer_provider=provider)
                log.info("otel.tracing.fastapi.instrumented")
            except Exception:  # pragma: no cover - defensive
                log.exception("otel.tracing.fastapi.instrument_failed")

        if RequestsInstrumentor is not None:
            try:
                RequestsInstrumentor().instrument()
                log.info("otel.tracing.requests.instrumented")
            except Exception:  # pragma: no cover
                log.exception("otel.tracing.requests.instrument_failed")

        if LoggingInstrumentor is not None:
            try:
                LoggingInstrumentor().instrument(set_logging_format=True)
                log.info("otel.tracing.logging.instrumented")
            except Exception:  # pragma: no cover
                log.exception("otel.tracing.logging.instrument_failed")

        _INITIALIZED = True
        return True
    except Exception:  # pragma: no cover - defensive
        log.exception("otel.tracing.init_failed")
        _INITIALIZED = True
        _PROVIDER = None
        return False


def get_tracer(name: str) -> otel_trace.Tracer:
    """
    Return a tracer. If tracing is disabled/unavailable, a no-op tracer is returned.
    """
    if not _OTEL_AVAILABLE:

        class _NoopTracer:  # pragma: no cover - simple shim
            def start_as_current_span(self, *_, **__):
                from contextlib import nullcontext

                return nullcontext()

        return _NoopTracer()  # type: ignore

    return otel_trace.get_tracer(name, __version__)


def shutdown_tracing() -> None:
    """
    Flush and shutdown the tracer provider (useful on graceful shutdown).
    """
    global _PROVIDER
    if _PROVIDER is not None:
        try:
            _PROVIDER.shutdown()
            log.info("otel.tracing.shutdown.complete")
        except Exception:  # pragma: no cover
            log.exception("otel.tracing.shutdown.failed")
        finally:
            _PROVIDER = None


__all__ = ["get_tracer", "setup_tracing", "shutdown_tracing"]
