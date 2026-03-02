"""
MCP Tools — System package

Exports system-level tool entrypoints for health checks, status, metrics, and backups.

Registered tools
----------------
- system.health  : Liveness/readiness health checks
- system.status  : High-level service status snapshot
- system.metrics : Prometheus/OpenMetrics scrape helpers
- system.backup  : Trigger/inspect backup operations

Each submodule should expose one callable named `invoke`, `run`, or `handle`.
This package imports them lazily and exposes a simple registry.
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
_register("system.health", "src.mcp.tools.system.health")
_register("system.status", "src.mcp.tools.system.status")
_register("system.metrics", "src.mcp.tools.system.metrics")
_register("system.backup", "src.mcp.tools.system.backup")


def get_tool(name: str) -> ToolFn | None:
    """Return a registered tool by name, or None."""
    return TOOLS.get(name)


__all__ = ["TOOLS", "ToolFn", "get_tool"]
