"""
Observability package bootstrap.

This module provides a single convenience entry point to wire up
metrics, tracing, and HTTP middleware without forcing hard
dependencies between submodules.

Usage (typically in `src.app:create_app` or lifespan handler):

    from src.observability import configure as configure_observability

    app = FastAPI(...)
    configure_observability(app, enable_metrics=True, enable_tracing=True, enable_middleware=True)

Each sub-component is imported lazily and called only if present.
Missing pieces are simply skipped with a log message.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Dict

import structlog

if TYPE_CHECKING:  # pragma: no cover
    from fastapi import FastAPI

log = structlog.get_logger(__name__)

# Try to import optional components, but don't fail package import if they are absent.
with contextlib.suppress(Exception):
    from .metrics import setup_metrics as _setup_metrics  # type: ignore[attr-defined]
with contextlib.suppress(Exception):
    from .tracing import setup_tracing as _setup_tracing  # type: ignore[attr-defined]
with contextlib.suppress(Exception):
    from .middleware import (
        install_observability_middleware as _add_middleware,  # type: ignore[attr-defined]
    )


def configure(
    app: FastAPI,
    *,
    enable_metrics: bool = True,
    enable_tracing: bool = True,
    enable_middleware: bool = True,
) -> dict[str, bool]:
    """
    Initialize observability subsystems for the given FastAPI app.

    Returns a dict of which subsystems were successfully configured:
        {"metrics": bool, "tracing": bool, "middleware": bool}
    """
    results = {"metrics": False, "tracing": False, "middleware": False}

    if enable_metrics:
        if "_setup_metrics" in globals():
            try:
                _setup_metrics(app)  # type: ignore[misc]
                results["metrics"] = True
                log.info("observability.metrics.configured")
            except Exception as e:  # pragma: no cover
                log.warning("observability.metrics.failed", error=str(e))
        else:
            log.info("observability.metrics.skipped", reason="module_not_available")

    if enable_tracing:
        if "_setup_tracing" in globals():
            try:
                _setup_tracing(app)  # type: ignore[misc]
                results["tracing"] = True
                log.info("observability.tracing.configured")
            except Exception as e:  # pragma: no cover
                log.warning("observability.tracing.failed", error=str(e))
        else:
            log.info("observability.tracing.skipped", reason="module_not_available")

    if enable_middleware:
        if "_add_middleware" in globals():
            try:
                _add_middleware(app)  # type: ignore[misc]
                results["middleware"] = True
                log.info("observability.middleware.configured")
            except Exception as e:  # pragma: no cover
                log.warning("observability.middleware.failed", error=str(e))
        else:
            log.info("observability.middleware.skipped", reason="module_not_available")

    return results


__all__ = ["configure"]
