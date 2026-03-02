"""
MCP Tool: model.test

Lightweight testing surface for the LLM adapter.

By default, all tests run in **simulate** mode (no actual LLM calls).
For each test, pass `simulate: false` to call a live provider (opt-in).

Supported actions
-----------------
- ping
    Payload: {}
    Minimal health check. Always succeeds in simulate mode.

- canary
    Payload: { "prompt"?, "simulate"? }
    Single-turn request/response test. Defaults to "ping" prompt and simulate=true.

- tokens
    Payload: { "text", "exact"? }
    Estimates or counts tokens in `text`.  If `exact=true`, attempts to get
    the exact token count from the adapter. Otherwise uses a heuristic approximation.

- embeddings
    Payload: { "text", "simulate"? }
    Generate embedding for `text`. Defaults to simulate=true.

- latency
    Payload: { "trials"?, "prompt"?, "simulate"? }
    Measures round-trip latency for completion calls.  Returns avg, min, max,
    p50, p90, p99. Defaults to trials=5, simulate=true.

Notes
-----
- simulate=true (default) ensures safe, deterministic, no-cost testing
- simulate=false opts in to live provider calls
- We intentionally avoid any provider-specific SDKs; all operations go
  through src.adapters.llm.LLMAdapter.
"""

from __future__ import annotations

import hashlib
import random
import statistics
import time
from collections.abc import Sequence
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
    raise RuntimeError("LLMAdapter is required for model.test tool")


# ─────────────────────────────────────────────────────────────────────────────
# Soft in-memory overrides (same pattern as model.manage)
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
        return LLMAdapter()  # type: ignore[call-arg]


def _info_from_adapter(adapter: LLMAdapter) -> dict[str, Any]:
    """Extract basic info from adapter."""
    out: dict[str, Any] = {}
    with suppress(Exception):
        info = adapter.info()  # type: ignore[attr-defined]
        if isinstance(info, dict):
            return info
    # Heuristics
    for key in ("provider", "model"):
        with suppress(Exception):
            val = getattr(adapter, key)  # type: ignore[attr-defined]
            if val is not None:
                out[key] = val
    # Fallbacks from settings
    with suppress(Exception):
        out.setdefault("provider", getattr(settings, "LLM_PROVIDER", None))
        out.setdefault("model", getattr(settings, "LLM_MODEL", None) or getattr(settings, "MODEL_NAME", None))
    return out


def _call_chat(adapter: LLMAdapter, prompt: str, **kwargs: Any) -> str:
    """
    Signature-agnostic wrapper around adapter.chat() or adapter.complete().
    Tries multiple method signatures to maximize compatibility.
    """
    for method_name in ("chat", "complete", "generate"):
        if not hasattr(adapter, method_name):  # type: ignore[attr-defined]
            continue
        method = getattr(adapter, method_name)  # type: ignore[attr-defined]
        try:
            # Try messages format
            result = method(messages=[{"role": "user", "content": prompt}], **kwargs)
            if isinstance(result, str):
                return result
            if isinstance(result, dict) and "content" in result:
                return str(result["content"])
            if isinstance(result, dict) and "text" in result:
                return str(result["text"])
        except (TypeError, KeyError):
            pass
        try:
            # Try plain prompt format
            result = method(prompt=prompt, **kwargs)
            if isinstance(result, str):
                return result
            if isinstance(result, dict) and "content" in result:
                return str(result["content"])
            if isinstance(result, dict) and "text" in result:
                return str(result["text"])
        except (TypeError, KeyError):
            pass
        try:
            # Try positional arg
            result = method(prompt, **kwargs)
            if isinstance(result, str):
                return result
            if isinstance(result, dict) and "content" in result:
                return str(result["content"])
            if isinstance(result, dict) and "text" in result:
                return str(result["text"])
        except (TypeError, KeyError):
            pass
    raise RuntimeError(f"Could not find compatible chat/complete method on {adapter}")


def _approx_token_count(text: str) -> int:
    """Heuristic token estimation (~4 chars per token for English)."""
    return max(1, len(text) // 4)


def _percentiles(values: Sequence[float], percentiles: Sequence[int] = (50, 90, 99)) -> dict[str, float]:
    """Calculate percentiles from a list of values."""
    if not values:
        return {f"p{p}": 0.0 for p in percentiles}
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    result = {}
    for p in percentiles:
        idx = int((p / 100.0) * (n - 1))
        result[f"p{p}"] = sorted_vals[idx]
    return result


def _deterministic_text_from_seed(seed: str) -> str:
    """Generate deterministic text based on seed for simulate mode."""
    # Use hash to generate deterministic but varied responses
    h = hashlib.sha256(seed.encode()).hexdigest()
    templates = [
        f"This is a simulated response with hash prefix {h[:8]}.",
        f"Simulated completion for seed {h[:12]}. This is deterministic.",
        f"Test response generated from seed. Hash: {h[:16]}",
    ]
    # Select template based on hash
    idx = int(h[:8], 16) % len(templates)
    return templates[idx]


def _deterministic_embedding_from_seed(seed: str, dimensions: int = 384) -> list[float]:
    """Generate deterministic embedding vector from seed."""
    # Use seed to initialize random generator for reproducibility
    h = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
    rng = random.Random(h)
    # Generate normalized random vector
    vec = [rng.gauss(0, 1) for _ in range(dimensions)]
    # Normalize to unit vector
    magnitude = sum(x * x for x in vec) ** 0.5
    if magnitude > 0:
        vec = [x / magnitude for x in vec]
    return vec


# ─────────────────────────────────────────────────────────────────────────────
# P3 Internal Action Handlers
# ─────────────────────────────────────────────────────────────────────────────


def _act_ping(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Minimal health check. Always succeeds."""
    a = _adapter()
    info = _info_from_adapter(a)
    return {
        "ok": True,
        "action": "ping",
        "provider": info.get("provider", "unknown"),
        "model": info.get("model", "unknown"),
    }


def _act_canary(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Single-turn completion test.

    Simulate mode (default): Returns deterministic response based on prompt.
    Live mode (simulate=false): Calls actual LLM adapter.
    """
    prompt = payload.get("prompt", "ping")
    simulate = payload.get("simulate", True)

    if simulate:
        # Deterministic simulate mode
        response = _deterministic_text_from_seed(f"canary:{prompt}")
        return {
            "ok": True,
            "action": "canary",
            "mode": "simulate",
            "prompt": prompt,
            "response": response,
        }
    else:
        # Live mode - actual LLM call
        a = _adapter()
        try:
            response = _call_chat(a, prompt)
            return {
                "ok": True,
                "action": "canary",
                "mode": "live",
                "prompt": prompt,
                "response": response,
            }
        except Exception as e:
            logger.exception("canary live call failed")
            return {
                "ok": False,
                "action": "canary",
                "mode": "live",
                "error": str(e),
            }


def _act_tokens(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Token counting for given text.

    exact=false (default): Uses heuristic approximation (~4 chars per token).
    exact=true: Attempts to get exact count from adapter tokenizer.
    """
    text = payload.get("text", "")
    exact = payload.get("exact", False)

    if not exact:
        # Approximate count
        count = _approx_token_count(text)
        return {
            "ok": True,
            "action": "tokens",
            "mode": "approximate",
            "count": count,
        }
    else:
        # Exact count via adapter
        a = _adapter()
        try:
            # Try tokenizer methods
            for method_name in ("count_tokens", "tokenize", "encode"):
                if not hasattr(a, method_name):  # type: ignore[attr-defined]
                    continue
                method = getattr(a, method_name)  # type: ignore[attr-defined]
                result = method(text)  # type: ignore[operator]
                if isinstance(result, int):
                    count = result
                elif isinstance(result, (list, tuple)):
                    count = len(result)
                else:
                    continue
                return {
                    "ok": True,
                    "action": "tokens",
                    "mode": "exact",
                    "count": count,
                }
            # Fallback to approximate if no tokenizer found
            count = _approx_token_count(text)
            return {
                "ok": True,
                "action": "tokens",
                "mode": "approximate",
                "count": count,
                "note": "Adapter does not provide tokenizer, using approximation",
            }
        except Exception as e:
            logger.warning(f"token counting failed: {e}")
            # Fallback to approximate
            count = _approx_token_count(text)
            return {
                "ok": True,
                "action": "tokens",
                "mode": "approximate",
                "count": count,
                "note": f"Exact counting failed ({e}), using approximation",
            }


def _act_embeddings(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Generate embeddings for text.

    Simulate mode (default): Returns deterministic embedding based on text.
    Live mode (simulate=false): Calls actual adapter.embeddings().
    """
    text = payload.get("text", "")
    simulate = payload.get("simulate", True)

    if simulate:
        # Deterministic simulate mode
        vec = _deterministic_embedding_from_seed(f"embed:{text}")
        return {
            "ok": True,
            "action": "embeddings",
            "mode": "simulate",
            "dimensions": len(vec),
            "embedding": vec,
        }
    else:
        # Live mode
        a = _adapter()
        try:
            if not hasattr(a, "embeddings"):  # type: ignore[attr-defined]
                return {
                    "ok": False,
                    "action": "embeddings",
                    "error": "Adapter does not support embeddings",
                }
            vec = a.embeddings(text)  # type: ignore[attr-defined]
            if not isinstance(vec, (list, tuple)):
                return {
                    "ok": False,
                    "action": "embeddings",
                    "error": f"Unexpected embedding format: {type(vec)}",
                }
            return {
                "ok": True,
                "action": "embeddings",
                "mode": "live",
                "dimensions": len(vec),
                "embedding": list(vec),
            }
        except Exception as e:
            logger.exception("embeddings call failed")
            return {
                "ok": False,
                "action": "embeddings",
                "mode": "live",
                "error": str(e),
            }


def _act_latency(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Measure round-trip latency for completion calls.

    Runs multiple trials and returns statistics (avg, min, max, p50, p90, p99).

    Simulate mode (default): Simulates realistic latency (50-150ms).
    Live mode (simulate=false): Measures actual LLM latency.
    """
    trials = max(1, payload.get("trials", 5))
    prompt = payload.get("prompt", "ping")
    simulate = payload.get("simulate", True)

    latencies: list[float] = []

    if simulate:
        # Simulate realistic latency variance
        h = int(hashlib.sha256(prompt.encode()).hexdigest(), 16)
        rng = random.Random(h)
        for _ in range(trials):
            # Simulated latency: 50-150ms with some variance
            latency_ms = rng.uniform(50, 150)
            latencies.append(latency_ms)
    else:
        # Live mode - actual timing
        a = _adapter()
        for _ in range(trials):
            try:
                start = time.perf_counter()
                _call_chat(a, prompt)
                elapsed = (time.perf_counter() - start) * 1000.0  # ms
                latencies.append(elapsed)
            except Exception as e:
                logger.warning(f"latency trial failed: {e}")
                # Skip failed trials
                continue

    if not latencies:
        return {
            "ok": False,
            "action": "latency",
            "error": "All trials failed",
        }

    stats = _percentiles(latencies, percentiles=(50, 90, 99))
    return {
        "ok": True,
        "action": "latency",
        "mode": "simulate" if simulate else "live",
        "trials": len(latencies),
        "avg_ms": statistics.mean(latencies),
        "min_ms": min(latencies),
        "max_ms": max(latencies),
        **stats,
    }


# ─────────────────────────────────────────────────────────────────────────────
# P3 Decorated Entry Point
# ─────────────────────────────────────────────────────────────────────────────

if "mcp_tool" in globals():

    @mcp_tool(tool_name="model.test", required_scope="tools:read")
    def model_test(
        ctx: ToolContext, payload: dict[str, Any] | None = None, **kwargs: Any  # type: ignore
    ) -> dict[str, Any]:
        """
        Entry function for model.test tool (P3 pattern).

        Args:
            ctx: Tool execution context with principal, tenant, trace_id
            payload: Optional dict with "action" and action-specific params
            **kwargs: Additional arguments (ignored)

        Returns:
            Action result dict with ok, action, and action-specific data
        """
        payload = payload or {}
        action = str(payload.get("action", "ping")).strip().lower()

        if action not in {"ping", "canary", "tokens", "embeddings", "latency"}:
            raise ValueError("action must be one of: ping, canary, tokens, embeddings, latency")

        try:
            if action == "ping":
                return _act_ping(ctx, payload)
            elif action == "canary":
                return _act_canary(ctx, payload)
            elif action == "tokens":
                return _act_tokens(ctx, payload)
            elif action == "embeddings":
                return _act_embeddings(ctx, payload)
            else:  # latency
                return _act_latency(ctx, payload)
        except Exception as e:
            logger.exception("model.test action failed", extra={"action": action})
            return {
                "ok": False,
                "action": action,
                "error": str(e),
            }


# ─────────────────────────────────────────────────────────────────────────────
# Fallback Entry Point (when decorator not available)
# ─────────────────────────────────────────────────────────────────────────────

if "mcp_tool" not in globals():

    def model_test(ctx: Any = None, payload: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        """
        Fallback entry function for model.test tool (no decorator).
        """
        payload = payload or {}
        action = str(payload.get("action", "ping")).strip().lower()

        if action not in {"ping", "canary", "tokens", "embeddings", "latency"}:
            raise ValueError("action must be one of: ping, canary, tokens, embeddings, latency")

        try:
            if action == "ping":
                return _act_ping(ctx, payload)
            elif action == "canary":
                return _act_canary(ctx, payload)
            elif action == "tokens":
                return _act_tokens(ctx, payload)
            elif action == "embeddings":
                return _act_embeddings(ctx, payload)
            else:  # latency
                return _act_latency(ctx, payload)
        except Exception as e:
            logger.exception("model.test action failed", extra={"action": action})
            return {
                "ok": False,
                "action": action,
                "error": str(e),
            }


# ── Backward compatibility aliases ───────────────────────────────────────────
invoke = model_test
run = model_test
handle = model_test
