"""
MCP Tool: db.switch

Developer utility to inspect and (temporarily) switch the Memgraph connection
profile at runtime.

Supported actions
-----------------
- get
    → Return the *effective* connection parameters (host/port/user).
      Password is never returned (masked if present).

- set
    Payload: { "host":"memgraph", "port":7687, "user":"...", "password":"..." }
    → Persist to process env (MG_HOST, MG_PORT, MG_USER, MG_PASSWORD) and
      return the new effective config. This does not edit files; it affects
      the running process only. New adapters will pick up the change.

- switch
    Payload: { "target":"local" }   # or "docker", "default"
    → Convenience preset mapping:
        - "local"   : host=127.0.0.1, port=7687
        - "docker"  : host=memgraph,   port=7687
        - "default" : taken from current Settings / env
      You can override by also passing host/port/user/password.

- test
    Payload: (optional) same params as "set"; if omitted uses current config.
    → Attempt to connect & run a trivial query. Does NOT persist changes.

Notes
-----
- Uses src.adapters.db_memgraph.MemgraphAdapter for connectivity.
- Changes apply to *future* connections; existing adapters already holding a
  connection won't be forcibly re-opened by this tool.
"""

from __future__ import annotations

import os
from contextlib import suppress
from typing import Any

# ── P0 Infrastructure ────────────────────────────────────────────────────────
from src.mcp.runtime import ToolContext, mcp_tool
from src.mcp.schemas import DbSwitchPayload

# ── Logging (best-effort) ─────────────────────────────────────────────────────
with suppress(Exception):
    from src.logging_setup import get_logger  # type: ignore

    logger = get_logger(__name__)  # type: ignore[assignment]
if "logger" not in globals():
    import logging

    logger = logging.getLogger(__name__)

# ── Settings & adapter ───────────────────────────────────────────────────────
with suppress(Exception):
    from src.adapters.db_memgraph import MemgraphAdapter  # type: ignore
    from src.config import settings  # type: ignore
if "MemgraphAdapter" not in globals():
    raise RuntimeError("Memgraph adapter is required for db.switch tool")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _mask_pw(pw: str | None) -> str | None:
    if not pw:
        return None
    return "****" if len(pw) <= 8 else pw[:2] + "****" + pw[-2:]


def _coerce_int(val: Any, default: int | None = None) -> int | None:
    try:
        return int(val) if val is not None and val != "" else default
    except Exception:
        return default


def _effective_config(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Return the effective configuration, applying optional overrides.
    """
    cfg = {
        "host": getattr(settings, "MG_HOST", os.getenv("MG_HOST", "memgraph")),
        "port": getattr(settings, "MG_PORT", int(os.getenv("MG_PORT", "7687"))),
        "user": getattr(settings, "MG_USER", os.getenv("MG_USER", "")),
        "password": getattr(settings, "MG_PASSWORD", os.getenv("MG_PASSWORD", "")),
    }
    overrides = overrides or {}
    if overrides.get("host"):
        cfg["host"] = str(overrides["host"])
    if "port" in overrides and overrides["port"] is not None:
        cfg["port"] = _coerce_int(overrides["port"], cfg["port"])
    if "user" in overrides and overrides["user"] is not None:
        cfg["user"] = str(overrides["user"])
    if "password" in overrides and overrides["password"] is not None:
        cfg["password"] = str(overrides["password"])
    return cfg


def _persist_env(cfg: dict[str, Any]) -> None:
    """
    Persist to process environment variables so new adapter instances pick them up.
    """
    os.environ["MG_HOST"] = str(cfg["host"])
    os.environ["MG_PORT"] = str(cfg["port"])
    # Empty strings are acceptable (disables auth)
    os.environ["MG_USER"] = str(cfg.get("user") or "")
    os.environ["MG_PASSWORD"] = str(cfg.get("password") or "")


def _preset(target: str) -> dict[str, Any]:
    target = target.strip().lower()
    if target == "local":
        return {"host": "127.0.0.1", "port": 7687}
    if target in {"docker", "compose"}:
        return {"host": "memgraph", "port": 7687}
    if target in {"default", "current"}:
        # "default" means what settings currently provide
        return {}
    raise ValueError(f"unknown target preset: {target!r}")


def _test_connection(cfg: dict[str, Any]) -> dict[str, Any]:
    """
    Attempt to connect using cfg and run a trivial query.
    """
    adapter = MemgraphAdapter(
        host=cfg["host"],
        port=int(cfg["port"]),
        user=cfg.get("user") or None,
        password=cfg.get("password") or None,
    )
    ok = False
    error = None
    try:
        rows = adapter.query("RETURN 1 AS ok")
        ok = bool(rows and int(rows[0].get("ok", 0)) == 1)
    except Exception as e:  # pragma: no cover
        error = str(e)
        ok = False
    return {"ok": ok, "error": error}


# ─────────────────────────────────────────────────────────────────────────────
# Public entrypoint
# ─────────────────────────────────────────────────────────────────────────────
@mcp_tool(tool_name="db.switch", required_scope="tools:admin")
def invoke(ctx: ToolContext, payload: dict[str, Any] | None = None, **kwargs) -> dict[str, Any]:
    """
    Entry for db.switch tool. See module docstring for payload formats.

    This tool is wrapped with @mcp_tool which provides:
    - Automatic RBAC enforcement (requires tools:admin scope)
    - Audit logging (all invocations tracked)
    - Metrics collection (Prometheus counters/histograms)
    - Structured error handling
    """
    payload = payload or {}

    # Pydantic validation
    validated = DbSwitchPayload(**payload)

    # Merge validated payload back
    payload = {**payload, **validated.model_dump(exclude_none=True)}

    action = validated.action
    result: dict[str, Any] = {"ok": True, "action": action}

    if action == "get":
        cfg = _effective_config()
        result.update(
            {
                "host": cfg["host"],
                "port": int(cfg["port"]),
                "user": cfg.get("user") or "",
                "password": _mask_pw(cfg.get("password")),
            }
        )

    elif action == "set":
        overrides = {
            "host": payload.get("host"),
            "port": payload.get("port"),
            "user": payload.get("user"),
            "password": payload.get("password"),
        }
        cfg = _effective_config(overrides)
        _persist_env(cfg)
        # Optionally test?
        test = bool(payload.get("test", False))
        test_out = _test_connection(cfg) if test else None
        result.update(
            {
                "host": cfg["host"],
                "port": int(cfg["port"]),
                "user": cfg.get("user") or "",
                "password": _mask_pw(cfg.get("password")),
                "tested": bool(test),
                "test_result": test_out if test else None,
            }
        )

    elif action == "switch":
        target = str(payload.get("target") or "").strip().lower()
        if not target:
            raise ValueError("switch requires 'target'")
        cfg = _preset(target)
        # Allow overrides (e.g., switch:local + custom user/pass)
        cfg = _effective_config(
            {**cfg, **{k: v for k, v in payload.items() if k in {"host", "port", "user", "password"}}}
        )
        _persist_env(cfg)
        result.update(
            {
                "target": target,
                "host": cfg["host"],
                "port": int(cfg["port"]),
                "user": cfg.get("user") or "",
                "password": _mask_pw(cfg.get("password")),
            }
        )

    else:  # test
        overrides = {
            "host": payload.get("host"),
            "port": payload.get("port"),
            "user": payload.get("user"),
            "password": payload.get("password"),
        }
        cfg = _effective_config(overrides)
        test_out = _test_connection(cfg)
        result.update(
            {
                "host": cfg["host"],
                "port": int(cfg["port"]),
                "user": cfg.get("user") or "",
                "password": _mask_pw(cfg.get("password")),
                "tested": True,
                "test_result": test_out,
            }
        )

    return result


# Back-compat aliases
run = invoke
handle = invoke
