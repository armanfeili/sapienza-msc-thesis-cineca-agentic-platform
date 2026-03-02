"""Common helpers for resolving provider configuration at runtime.

These utilities are shared between the public models router and the
admin/model-management endpoints to keep provider handling consistent.
"""

from __future__ import annotations

import logging
from contextlib import suppress
from typing import Any

import httpx

from src.config import settings

DEFAULT_HTTPX_TIMEOUT = httpx.Timeout(
    connect=2.0,
    read=60.0,
    write=10.0,
    pool=5.0,
)


def _coerce_attr(obj: Any, attr: str) -> Any | None:
    with suppress(Exception):
        value = getattr(obj, attr)
        if value is not None:
            return value
    if isinstance(obj, dict):
        return obj.get(attr)
    return None


def is_ollama_provider(provider: Any) -> bool:
    """Best-effort detection whether the provider represents an Ollama endpoint."""
    if provider is None:
        return False
    candidates = [
        _coerce_attr(provider, "id"),
        _coerce_attr(provider, "name"),
        _coerce_attr(provider, "type"),
        _coerce_attr(provider, "base_url"),
    ]
    for value in candidates:
        if value and "ollama" in str(value).lower():
            return True
    config = _coerce_attr(provider, "config")
    if isinstance(config, dict):
        base = config.get("base_url")
        if base and "ollama" in str(base).lower():
            return True
    return False


def resolve_provider_base_url(provider: Any) -> str | None:
    """Return the effective base URL for a provider, applying Ollama overrides."""
    base = _coerce_attr(provider, "base_url")
    if not base:
        config = _coerce_attr(provider, "config")
        if isinstance(config, dict):
            base = config.get("base_url")
    if is_ollama_provider(provider):
        try:
            env_override = getattr(settings, "OLLAMA_BASE_URL", None)
        except Exception:
            env_override = None
        if env_override:
            base = env_override
        elif not base:
            try:
                base = settings.resolve_ollama_base_url()
            except Exception:
                base = "http://ollama:11434"
    if base:
        return str(base).rstrip("/")
    return None


def timeout_for_provider(provider: Any, default: httpx.Timeout | None = None) -> httpx.Timeout:
    """Return the appropriate timeout for a provider (Ollama-aware)."""
    if is_ollama_provider(provider):
        try:
            secs = int(getattr(settings, "OLLAMA_TIMEOUT_SECS", 60))
        except Exception:
            secs = 60
        secs = max(secs, 1)
        return httpx.Timeout(connect=secs, read=secs, write=secs, pool=5.0)
    return default or DEFAULT_HTTPX_TIMEOUT


def resolve_upstream_model_id(
    provider: Any,
    resolved_model: str | None,
    requested_model: str | None,
    instance: dict[str, Any] | None,
) -> str | None:
    """Translate logical model ids to provider-specific ids when needed."""
    candidate = None
    try:
        candidate = (instance or {}).get("model_id")
    except Exception:
        candidate = None
    if not candidate:
        candidate = resolved_model
    if is_ollama_provider(provider):
        try:
            mapping = settings.effective_ollama_model_map
        except Exception:
            mapping = {}
        for key in [candidate, resolved_model, requested_model]:
            if not key:
                continue
            mapped = mapping.get(str(key))
            if mapped:
                return mapped
    return candidate


def debug_log_provider_call(
    logger: Any,
    *,
    event: str,
    trace_meta: dict[str, Any] | None = None,
    base_url: str | None = None,
    resolved_model: str | None = None,
    mapped_model: str | None = None,
    elapsed_ms: int | None = None,
    status_code: int | None = None,
    error: str | None = None,
    attempt: int | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Best-effort debug log for upstream provider interactions."""
    if logger is None:
        return
    is_enabled = getattr(logger, "isEnabledFor", None)
    if callable(is_enabled) and not is_enabled(logging.DEBUG):
        return
    details: dict[str, Any] = {}
    if trace_meta:
        details.update(trace_meta)
    for key, value in (
        ("resolved_base_url", base_url),
        ("resolved_model", resolved_model),
        ("mapped_model", mapped_model),
        ("elapsed_ms", elapsed_ms),
        ("status_code", status_code),
        ("error", error),
        ("attempt", attempt),
    ):
        if value is not None:
            details[key] = value
    if extra:
        for key, value in extra.items():
            if value is not None:
                details[key] = value
    with suppress(Exception):
        logger.debug(event, extra={"details": details})


__all__ = [
    "DEFAULT_HTTPX_TIMEOUT",
    "debug_log_provider_call",
    "is_ollama_provider",
    "resolve_provider_base_url",
    "resolve_upstream_model_id",
    "timeout_for_provider",
]
