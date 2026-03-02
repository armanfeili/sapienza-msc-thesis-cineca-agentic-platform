"""
Agent tools package.

Contains tools used to build and expose agent-related capabilities to MCP,
such as assembling execution context that includes user/session metadata,
available tools, and model information.

Concrete tool modules live under this package, e.g.:
- src.mcp.tools.agent.context  (exposes `invoke(payload, **kwargs)`)

This __init__ keeps imports light and offers small discovery helpers.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterable
from typing import List

PACKAGE = __name__  # e.g., "src.mcp.tools.agent"


def iter_modules(package: str = PACKAGE) -> Iterable[str]:
    """
    Yield fully-qualified module names for non-package modules under this package.
    """
    pkg = importlib.import_module(package)
    if not hasattr(pkg, "__path__"):
        return []
    for info in pkgutil.walk_packages(pkg.__path__, prefix=pkg.__name__ + "."):
        if not info.ispkg:
            yield info.name


def list_modules() -> list[str]:
    """Return a list of module names under this package."""
    return list(iter_modules())


__all__ = ["PACKAGE", "iter_modules", "list_modules"]
