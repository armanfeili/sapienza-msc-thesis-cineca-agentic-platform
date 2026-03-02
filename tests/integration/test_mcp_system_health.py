import asyncio
import importlib
from typing import Any, Callable, Optional

import pytest


async def _maybe_await(value: Any) -> Any:
    if asyncio.iscoroutine(value):
        return await value
    if asyncio.isfuture(value):
        return await value
    return value


def _find_callable(mod) -> Optional[Callable[..., Any]]:
    """
    Try common entrypoint names used by MCP tools. Return the first callable found.
    """
    for name in ("health", "run", "execute", "tool", "main"):
        fn = getattr(mod, name, None)
        if callable(fn):
            return fn
    return None


@pytest.mark.asyncio
async def test_mcp_system_health_tool_smoke():
    """
    Import the MCP system.health tool module and execute its entrypoint.
    Accept both sync/async styles and multiple common function names.

    The result should be a dict-like payload that at least contains either:
      - {"status": "ok"}  (simple success), or
      - {"checks": {...}} (expanded health details)
    """
    mod = importlib.import_module("src.mcp.tools.system.health")
    fn = _find_callable(mod)
    assert fn is not None, "system.health tool does not expose a callable entrypoint"

    # Call with no args; MCP tools are expected to be self-contained for health.
    result = await _maybe_await(fn())

    assert isinstance(result, (dict,)), "health tool should return a dict-like payload"

    # Be flexible about shape; accept either a top-level status or nested checks.
    status = result.get("status")
    checks = result.get("checks")

    assert status == "ok" or isinstance(checks, dict), f"unexpected health payload shape: {result}"

    # If checks are present, they should be a mapping of probe results.
    if isinstance(checks, dict):
        # Common probes: allow any subset, but ensure items have a 'status' key.
        for name, probe in checks.items():
            assert isinstance(probe, dict), f"probe {name} should be a dict"
            assert "status" in probe, f"probe {name} missing 'status'"
            # status typically is one of ok|error|unknown
            assert probe["status"] in {"ok", "error", "unknown"}
