"""
Errors tools package.

Hosts MCP tools related to structured error reporting and diagnostics.

Concrete modules:
- src.mcp.tools.errors.report  (exposes `invoke(payload, **kwargs)`)

This __init__ remains lightweight and offers simple discovery helpers.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterable
from typing import List

PACKAGE = __name__  # e.g., "src.mcp.tools.errors"


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
