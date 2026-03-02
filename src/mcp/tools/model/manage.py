"""
MCP Tool: model.manage

Runtime (best-effort) management surface for the LLM adapter.

This tool does *not* persist changes to disk or environment variables.
Where supported by the adapter, updates take effect immediately for the
current process. Otherwise we fall back to soft in-memory overrides for
calls made through this tool.

Supported actions
-----------------
- info
    Payload: {}
    Returns: {
      ok, action, provider, model, temperature, max_tokens, api_base?, features
    }

- get_config
    Payload: {}
    Returns the same shape as `info`.

- set_config
    Payload: { "model"?, "temperature"?, "max_tokens"? }
    Returns updated config (same shape as `info`).
    Validates: temperature [0.0, 2.0], max_tokens [1, 32000]

- reset_config
    Payload: {}
    Clears in-memory overrides and re-reads settings from environment.

- list_models
    Payload: {}
    Returns: { ok, action, models:[...] }
    Source: settings (LLM_AVAILABLE_MODELS / LLM_MODELS) or a singleton list
            with the current model if no catalog exists.

- capabilities
    Payload: {}
    Returns: { ok, action, features:[...] }  # e.g., ["chat","embeddings","json"]

- health
    Payload: {}
    Adapter health probe.

Notes
-----
- We intentionally avoid any provider-specific SDKs here; all operations go
  through src.adapters.llm.LLMAdapter.
- Secrets (API keys, tokens) are NEVER exposed in responses or logs.
"""

from __future__ import annotations

from contextlib import suppress
from typing import Any

# ── Logging (structlog-aware if configured) ───────────────────────────────────
with suppress(Exception):
    from src.logging_setup import get_logger  # type: ignore

    logger = get_logger(__name__)  # type: ignore[assignment]
if "logger" not in globals():
    import logging

    logger = logging.getLogger(__name__)

# ── P3 Pattern: ToolContext ───────────────────────────────────────────────────
with suppress(Exception):
    from src.mcp.decorator import mcp_tool  # type: ignore
with suppress(Exception):
    from src.mcp.context import ToolContext  # type: ignore

# ── Config & Adapter ──────────────────────────────────────────────────────────
with suppress(Exception):
    from src.config import settings  # type: ignore
with suppress(Exception):
    from src.adapters.llm import LLMAdapter  # type: ignore
if "LLMAdapter" not in globals():
    raise RuntimeError("LLMAdapter is required for model.manage tool")


# ─────────────────────────────────────────────────────────────────────────────
# Validation & Secret Masking
# ─────────────────────────────────────────────────────────────────────────────

# Configuration limits
TEMPERATURE_MIN = 0.0
TEMPERATURE_MAX = 2.0
MAX_TOKENS_MIN = 1
MAX_TOKENS_MAX = 32000


def _validate_temperature(value: Any) -> float:
    """Validate temperature is within acceptable range."""
    try:
        temp = float(value)
    except (ValueError, TypeError) as e:
        raise ValueError(f"temperature must be a number, got {type(value).__name__}") from e

    if not (TEMPERATURE_MIN <= temp <= TEMPERATURE_MAX):
        raise ValueError(f"temperature must be between {TEMPERATURE_MIN} and {TEMPERATURE_MAX}, got {temp}")
    return temp


def _validate_max_tokens(value: Any) -> int:
    """Validate max_tokens is within acceptable range."""
    try:
        tokens = int(value)
    except (ValueError, TypeError) as e:
        raise ValueError(f"max_tokens must be an integer, got {type(value).__name__}") from e

    if not (MAX_TOKENS_MIN <= tokens <= MAX_TOKENS_MAX):
        raise ValueError(f"max_tokens must be between {MAX_TOKENS_MIN} and {MAX_TOKENS_MAX}, got {tokens}")
    return tokens


def _mask_secrets(data: dict[str, Any]) -> dict[str, Any]:
    """
    Mask sensitive fields in response data.
    Never expose: API keys, tokens, passwords, credentials.
    """
    masked = data.copy()

    # Fields that should never be exposed
    secret_fields = {
        "api_key",
        "apikey",
        "api_token",
        "token",
        "password",
        "secret",
        "credentials",
        "auth_token",
        "authorization",
        "bearer",
    }

    for key in list(masked.keys()):
        if key.lower() in secret_fields:
            del masked[key]  # Remove entirely, don't even show "***"
        # Also check api_base for embedded secrets
        elif key == "api_base" and masked.get(key):
            # Mask query params that might contain tokens
            url = str(masked[key])
            if "?" in url:
                base, _ = url.split("?", 1)
                masked[key] = f"{base}?<query_masked>"

    return masked


# ─────────────────────────────────────────────────────────────────────────────
# Soft in-memory overrides (used if adapter doesn't support configure-at-run)
# ─────────────────────────────────────────────────────────────────────────────
_OVERRIDES: dict[str, Any] = {}


def _adapter() -> LLMAdapter:
    """Construct a fresh adapter each call to pick up latest overrides/env."""
    try:
        return LLMAdapter(
            model=_OVERRIDES.get("model"),
            temperature=_OVERRIDES.get("temperature"),
            max_tokens=_OVERRIDES.get("max_tokens"),
        )
    except TypeError:
        # Older adapters might not accept keyword overrides; fall back.
        return LLMAdapter()  # type: ignore[call-arg]


def _safe_info_from_adapter(adapter: LLMAdapter) -> dict[str, Any]:
    """Extract info from adapter, trying multiple approaches."""
    # Try a first-class info method
    with suppress(Exception):
        info = adapter.info()  # type: ignore[attr-defined]
        if isinstance(info, dict):
            return info

    # Heuristics if info() is not available
    out: dict[str, Any] = {}
    for key in ("provider", "model", "temperature", "max_tokens", "api_base"):
        with suppress(Exception):
            val = getattr(adapter, key)  # type: ignore[attr-defined]
            if val is not None:
                out[key] = val

    # Fallbacks from settings if missing
    with suppress(Exception):
        out.setdefault("provider", getattr(settings, "LLM_PROVIDER", None))
        out.setdefault("model", getattr(settings, "LLM_MODEL", None) or getattr(settings, "MODEL_NAME", None))
        out.setdefault("temperature", getattr(settings, "LLM_TEMPERATURE", None))
        out.setdefault("max_tokens", getattr(settings, "LLM_MAX_TOKENS", None))
        out.setdefault("api_base", getattr(settings, "LLM_API_BASE", None))

    # Feature discovery
    features = []
    with suppress(Exception):
        feats = adapter.features()  # type: ignore[attr-defined]
        if isinstance(feats, (list, tuple)):
            features = list(feats)
    if not features:
        # Probe methods
        if hasattr(adapter, "chat"):  # type: ignore[attr-defined]
            features.append("chat")
        if hasattr(adapter, "embeddings"):  # type: ignore[attr-defined]
            features.append("embeddings")
        if hasattr(adapter, "json"):  # type: ignore[attr-defined]
            features.append("json")
    out["features"] = features

    return out


def _current_config() -> dict[str, Any]:
    """Get current configuration with overrides applied."""
    a = _adapter()
    info = _safe_info_from_adapter(a)
    # Apply visible overrides on top (so response reflects pending runtime state)
    for k, v in _OVERRIDES.items():
        if v is not None:
            info[k] = v
    return info


def _set_runtime(adapter: LLMAdapter, *, model: Any = None, temperature: Any = None, max_tokens: Any = None) -> None:
    """
    Best-effort apply configuration at runtime. If adapter exposes a
    `configure` method, use it; otherwise record overrides.
    """
    applied = False
    with suppress(Exception):
        cfg = {}
        if model is not None:
            cfg["model"] = model
        if temperature is not None:
            cfg["temperature"] = float(temperature)
        if max_tokens is not None:
            cfg["max_tokens"] = int(max_tokens)
        if cfg:
            adapter.configure(**cfg)  # type: ignore[attr-defined]
            applied = True

    if not applied:
        if model is not None:
            _OVERRIDES["model"] = model
        if temperature is not None:
            _OVERRIDES["temperature"] = float(temperature)
        if max_tokens is not None:
            _OVERRIDES["max_tokens"] = int(max_tokens)


def _list_models_catalog() -> list[str]:
    """Retrieve list of available models from adapter or settings."""
    # Try adapter first
    with suppress(Exception):
        a = _adapter()
        models = a.available_models()  # type: ignore[attr-defined]
        if isinstance(models, (list, tuple)) and models:
            return [str(m) for m in models]

    # Try settings env shapes
    for attr in ("LLM_AVAILABLE_MODELS", "LLM_MODELS", "AVAILABLE_MODELS"):
        with suppress(Exception):
            val = getattr(settings, attr)
            if isinstance(val, (list, tuple)) and val:
                return [str(m) for m in val]
            if isinstance(val, str) and val.strip():
                # comma/space separated
                parts = [p.strip() for p in val.replace(";", ",").split(",") if p.strip()]
                if parts:
                    return parts

    # Fallback: the current model only
    cfg = _current_config()
    model = cfg.get("model") or "unknown"
    return [str(model)]


# ─────────────────────────────────────────────────────────────────────────────
# P3 Internal Action Handlers
# ─────────────────────────────────────────────────────────────────────────────


def _act_info(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return current adapter configuration info."""
    info = _current_config()
    masked = _mask_secrets(info)
    return {"ok": True, "action": "info", **masked}


def _act_get_config(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Get current configuration (same as info)."""
    info = _current_config()
    masked = _mask_secrets(info)
    return {"ok": True, "action": "get_config", **masked}


def _act_set_config(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Set configuration with validation.

    Validates:
    - temperature: must be float in [0.0, 2.0]
    - max_tokens: must be int in [1, 32000]
    - model: string (no validation, adapter-specific)
    """
    model = payload.get("model")
    temperature = payload.get("temperature")
    max_tokens = payload.get("max_tokens")

    # Validate before applying
    if temperature is not None:
        temperature = _validate_temperature(temperature)
    if max_tokens is not None:
        max_tokens = _validate_max_tokens(max_tokens)

    a = _adapter()
    _set_runtime(a, model=model, temperature=temperature, max_tokens=max_tokens)
    info = _current_config()
    masked = _mask_secrets(info)
    return {"ok": True, "action": "set_config", **masked}


def _act_reset_config(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Clear in-memory overrides and re-read from environment."""
    _OVERRIDES.clear()
    info = _current_config()
    masked = _mask_secrets(info)
    return {"ok": True, "action": "reset_config", **masked}


def _act_list_models(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """List available models from adapter or settings."""
    models = _list_models_catalog()
    return {"ok": True, "action": "list_models", "models": models}


def _act_capabilities(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return adapter capabilities/features."""
    feats = _current_config().get("features") or []
    return {"ok": True, "action": "capabilities", "features": feats}


def _act_health(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Check adapter health status."""
    a = _adapter()
    healthy = True
    detail: dict[str, Any] | None = None
    with suppress(Exception):
        # Prefer adapter.health() → bool | dict
        res = a.health()  # type: ignore[attr-defined]
        if isinstance(res, dict):
            detail = res
            healthy = bool(res.get("ok", True))
        elif isinstance(res, bool):
            healthy = res
    return {"ok": True, "action": "health", "healthy": bool(healthy), "detail": detail}


# ─────────────────────────────────────────────────────────────────────────────
# P3 Decorated Entry Point
# ─────────────────────────────────────────────────────────────────────────────

if "mcp_tool" in globals():

    @mcp_tool(tool_name="model.manage", required_scope="tools:admin")
    def model_manage(
        ctx: ToolContext, payload: dict[str, Any] | None = None, **kwargs: Any  # type: ignore
    ) -> dict[str, Any]:
        """
        Entry function for model.manage tool (P3 pattern).

        Args:
            ctx: Tool execution context with principal, tenant, trace_id
            payload: Optional dict with "action" and action-specific params
            **kwargs: Additional arguments (ignored)

        Returns:
            Action result dict with ok, action, and action-specific data
        """
        payload = payload or {}
        action = str(payload.get("action", "info")).strip().lower()

        if action not in {"info", "get_config", "set_config", "reset_config", "list_models", "capabilities", "health"}:
            raise ValueError(
                "action must be one of: info, get_config, set_config, reset_config, "
                "list_models, capabilities, health"
            )

        try:
            if action == "info":
                return _act_info(ctx, payload)
            elif action == "get_config":
                return _act_get_config(ctx, payload)
            elif action == "set_config":
                return _act_set_config(ctx, payload)
            elif action == "reset_config":
                return _act_reset_config(ctx, payload)
            elif action == "list_models":
                return _act_list_models(ctx, payload)
            elif action == "capabilities":
                return _act_capabilities(ctx, payload)
            else:  # health
                return _act_health(ctx, payload)
        except ValueError as e:
            # Validation errors
            logger.warning(f"model.manage validation error: {e}", extra={"action": action})
            return {
                "ok": False,
                "action": action,
                "error": str(e),
            }
        except Exception as e:
            logger.exception("model.manage action failed", extra={"action": action})
            return {
                "ok": False,
                "action": action,
                "error": str(e),
            }


# ─────────────────────────────────────────────────────────────────────────────
# Fallback Entry Point (when decorator not available)
# ─────────────────────────────────────────────────────────────────────────────

if "mcp_tool" not in globals():

    def model_manage(ctx: Any = None, payload: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        """
        Fallback entry function for model.manage tool (no decorator).
        """
        payload = payload or {}
        action = str(payload.get("action", "info")).strip().lower()

        if action not in {"info", "get_config", "set_config", "reset_config", "list_models", "capabilities", "health"}:
            raise ValueError(
                "action must be one of: info, get_config, set_config, reset_config, "
                "list_models, capabilities, health"
            )

        try:
            if action == "info":
                return _act_info(ctx, payload)
            elif action == "get_config":
                return _act_get_config(ctx, payload)
            elif action == "set_config":
                return _act_set_config(ctx, payload)
            elif action == "reset_config":
                return _act_reset_config(ctx, payload)
            elif action == "list_models":
                return _act_list_models(ctx, payload)
            elif action == "capabilities":
                return _act_capabilities(ctx, payload)
            else:  # health
                return _act_health(ctx, payload)
        except ValueError as e:
            logger.warning(f"model.manage validation error: {e}", extra={"action": action})
            return {
                "ok": False,
                "action": action,
                "error": str(e),
            }
        except Exception as e:
            logger.exception("model.manage action failed", extra={"action": action})
            return {
                "ok": False,
                "action": action,
                "error": str(e),
            }


# ── Backward compatibility aliases ───────────────────────────────────────────
invoke = model_manage
run = model_manage
handle = model_manage
