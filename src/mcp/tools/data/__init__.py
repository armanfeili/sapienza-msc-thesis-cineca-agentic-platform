"""
Data tools package.

Holds MCP tools for data-related functionality such as archival and quality
checks.

Concrete modules:
- src.mcp.tools.data.archive  (exposes `invoke(payload, **kwargs)`)
- src.mcp.tools.data.quality  (exposes `invoke(payload, **kwargs)`)

This __init__ keeps imports lightweight and provides simple discovery helpers.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterable
from typing import List

PACKAGE = __name__  # e.g., "src.mcp.tools.data"


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
