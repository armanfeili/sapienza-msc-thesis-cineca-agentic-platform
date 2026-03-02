"""
MCP Tools package

Lightweight helpers to resolve, discover, and lazily import tool modules based on
their dotted MCP names (e.g., "graph.query" → src.mcp.tools.graph.query).

Conventions (soft)
------------------
Each concrete tool module (e.g., src/mcp/tools/system/health.py) may expose:
- `invoke(payload: dict, **kwargs) -> dict`   # preferred
- or `run(payload: dict, **kwargs) -> dict`
- or `handle(payload: dict, **kwargs) -> dict`

This package does **not** enforce an interface; it only helps you locate and
import the module/callable given a tool name from the manifest.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from types import ModuleType
from typing import Dict, List, Optional, Tuple

PACKAGE_ROOT = "src.mcp.tools"


# ──────────────────────────────────────────────────────────────────────────────
# Datamodel
# ──────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ToolSpec:
    name: str  # e.g., "graph.query"
    module: str  # e.g., "src.mcp.tools.graph.query"
    callable_name: str | None = None  # "invoke" | "run" | "handle" | None


# ──────────────────────────────────────────────────────────────────────────────
# Resolution helpers
# ──────────────────────────────────────────────────────────────────────────────
def module_name_for_tool(tool_name: str) -> str:
    """
    Translate MCP tool name ("graph.query") into Python module path
    ("src.mcp.tools.graph.query").
    """
    safe = tool_name.strip().strip(".")
    return f"{PACKAGE_ROOT}.{safe}"


def tool_name_for_module(module_name: str) -> str:
    """
    Inverse of `module_name_for_tool` for modules under src.mcp.tools.*.
    """
    prefix = PACKAGE_ROOT + "."
    if not module_name.startswith(prefix):
        raise ValueError(f"module {module_name!r} not under {PACKAGE_ROOT!r}")
    return module_name[len(prefix) :]


def import_module_for_tool(tool_name: str) -> ModuleType:
    """Import and return the Python module that implements the tool."""
    return importlib.import_module(module_name_for_tool(tool_name))


def find_callable_in_module(mod: ModuleType) -> tuple[str | None, Callable | None]:
    """
    Best-effort resolution of a callable within a tool module.
    Preference order: invoke → run → handle.
    """
    for attr in ("invoke", "run", "handle"):
        if hasattr(mod, attr):
            fn = getattr(mod, attr)
            if callable(fn):
                return attr, fn
    return None, None


def load(tool_name: str) -> tuple[ModuleType, Callable | None]:
    """
    Import a tool module and return (module, callable_or_none).
    """
    mod = import_module_for_tool(tool_name)
    _, fn = find_callable_in_module(mod)
    return mod, fn


# ──────────────────────────────────────────────────────────────────────────────
# Discovery
# ──────────────────────────────────────────────────────────────────────────────
def iter_tool_modules(package: str = PACKAGE_ROOT) -> Iterable[str]:
    """
    Yield fully-qualified module names for all non-package modules under PACKAGE_ROOT.
    """
    pkg = importlib.import_module(package)
    for info in pkgutil.walk_packages(pkg.__path__, prefix=pkg.__name__ + "."):
        if not info.ispkg:
            yield info.name


def list_tool_modules() -> list[str]:
    """Return a list of module names (e.g., 'src.mcp.tools.graph.query')."""
    return list(iter_tool_modules())


def list_tools() -> list[str]:
    """Return a list of MCP tool names (e.g., 'graph.query')."""
    return [tool_name_for_module(m) for m in list_tool_modules()]


def discover() -> list[ToolSpec]:
    """
    Return a list of ToolSpec with best-effort callable resolution for each module.
    """
    specs: list[ToolSpec] = []
    for m in list_tool_modules():
        try:
            mod = importlib.import_module(m)
        except Exception:
            # Skip modules that fail to import
            continue
        cname, _ = find_callable_in_module(mod)
        specs.append(ToolSpec(name=tool_name_for_module(m), module=m, callable_name=cname))
    return specs


__all__ = [
    "PACKAGE_ROOT",
    "ToolSpec",
    "discover",
    "find_callable_in_module",
    "import_module_for_tool",
    "iter_tool_modules",
    "list_tool_modules",
    "list_tools",
    "load",
    "module_name_for_tool",
    "tool_name_for_module",
]
