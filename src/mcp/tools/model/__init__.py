"""
MCP Namespace: model

Lightweight registry for model-management tools.

Exposed tools
-------------
- manage : lifecycle/configuration surface for models (enable/disable, set defaults, etc.)
- test   : quick canary/eval pings against the active model adapter

Each tool module must expose an `invoke(payload: dict | None, **kwargs) -> dict`
(callables named `run` or `handle` are also accepted for convenience).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from importlib import import_module
from typing import Any, Dict

NAMESPACE = "model"

# Map tool name → module path
TOOLS: dict[str, str] = {
    "manage": "src.mcp.tools.model.manage",
    "test": "src.mcp.tools.model.test",
}


def list_tools() -> Iterable[str]:
    """Return available tool names in this namespace."""
    return TOOLS.keys()


def _load_callable(module_path: str) -> Callable[..., Any]:
    mod = import_module(module_path)
    func = getattr(mod, "invoke", None) or getattr(mod, "run", None) or getattr(mod, "handle", None)
    if not callable(func):
        raise TypeError(f"Module {module_path} does not expose an invoke/run/handle callable")
    return func


def get_tool(name: str) -> Callable[..., Any]:
    """Resolve a tool callable by name."""
    try:
        module_path = TOOLS[name]
    except KeyError as e:
        raise KeyError(f"Unknown model tool: {name}") from e
    return _load_callable(module_path)


def invoke(tool: str, payload: dict[str, Any] | None = None, **kwargs) -> dict[str, Any]:
    """Dispatch to a tool by name with the given payload."""
    handler = get_tool(tool)
    return handler(payload or {}, **kwargs)


__all__ = ["NAMESPACE", "TOOLS", "get_tool", "invoke", "list_tools"]
