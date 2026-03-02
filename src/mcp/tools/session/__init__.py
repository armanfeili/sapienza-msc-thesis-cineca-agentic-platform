"""
MCP Tools — Session package

Exports tool entrypoints under this namespace.

Included tools
--------------
- session.manage : Manage conversational/session state (create/read/update/delete),
                   set preferences, and attach arbitrary key/value context.

Each submodule is expected to expose one of: `invoke`, `run`, or `handle`.
This package simply wires those into a local registry for discovery.
"""

from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
from typing import Any, Dict, Optional

ToolFn = Callable[..., dict[str, Any]]

TOOLS: dict[str, ToolFn] = {}


def _register(name: str, module_path: str) -> None:
    """Import a tool module and register its callable entrypoint."""
    mod = import_module(module_path)
    handler = getattr(mod, "invoke", None) or getattr(mod, "run", None) or getattr(mod, "handle", None)
    if not callable(handler):
        raise AttributeError(f"{module_path} has no callable invoke/run/handle")
    TOOLS[name] = handler  # type: ignore[assignment]


# Register tools in this package
_register("session.manage", "src.mcp.tools.session.manage")


def get_tool(name: str) -> ToolFn | None:
    """Return a registered tool by name, or None."""
    return TOOLS.get(name)


__all__ = ["TOOLS", "ToolFn", "get_tool"]
