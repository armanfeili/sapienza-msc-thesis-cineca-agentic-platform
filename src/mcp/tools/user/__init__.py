"""
MCP User Tools Package

Exports a small registry of "user.*" tools. Each tool module should expose:
- `invoke(payload: dict | None = None, **kwargs) -> dict`
- optional `describe() -> dict` returning a static schema/metadata block.

Tools included:
- user.profile  → manage or fetch the current user's profile/preferences
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from contextlib import suppress
from typing import Any, Dict, Optional

# ── Logging (best-effort) ─────────────────────────────────────────────────────
with suppress(Exception):
    from src.logging_setup import get_logger  # type: ignore

    logger = get_logger(__name__)  # type: ignore[assignment]
if "logger" not in globals():
    import logging

    logger = logging.getLogger(__name__)
    if not logger.handlers:
        logging.basicConfig(level=logging.INFO)


# ── Import tool modules (lazy-safe) ───────────────────────────────────────────
with suppress(Exception):
    from . import profile as _profile  # type: ignore
if "_profile" not in globals():
    _profile = None  # type: ignore


# ── Registry ──────────────────────────────────────────────────────────────────
TOOLS: dict[str, Callable[..., dict[str, Any]]] = {}

if _profile and hasattr(_profile, "invoke"):
    TOOLS["user.profile"] = _profile.invoke  # type: ignore[assignment]
else:  # pragma: no cover - only used if module missing

    def _missing(*args, **kwargs) -> dict[str, Any]:
        return {"ok": False, "error": "user.profile tool not available"}

    TOOLS["user.profile"] = _missing


# ── Helpers ───────────────────────────────────────────────────────────────────
def get_tool(name: str) -> Callable[..., dict[str, Any]]:
    """
    Return a callable handle for the given tool name.

    Raises:
        KeyError: if the tool is not registered.
    """
    try:
        return TOOLS[name]
    except KeyError:
        raise KeyError(f"unknown user tool '{name}'")


def list_tool_names() -> Iterable[str]:
    """List registered user.* tool names."""
    return sorted(TOOLS.keys())


def describe_tools() -> dict[str, Any]:
    """
    Introspect tool schemas/metadata where available.
    """
    out: dict[str, Any] = {"namespace": "user", "tools": {}}
    # user.profile
    if _profile and hasattr(_profile, "describe"):
        with suppress(Exception):
            out["tools"]["user.profile"] = _profile.describe()  # type: ignore
    else:
        out["tools"]["user.profile"] = {
            "name": "user.profile",
            "summary": "Manage or fetch the current user's profile/preferences.",
            "schema": {"type": "object", "properties": {"action": {"type": "string"}}, "required": []},
        }
    return out


__all__ = [
    "TOOLS",
    "describe_tools",
    "get_tool",
    "list_tool_names",
]
