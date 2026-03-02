"""
Graph tools package.

Contains MCP tools for graph-related operations such as analytics, bulk load,
CRUD, Cypher generation, ad-hoc queries, schema discovery, and search.

Concrete modules (expected):
- src.mcp.tools.graph.analytics
- src.mcp.tools.graph.bulk
- src.mcp.tools.graph.crud
- src.mcp.tools.graph.generate_cypher
- src.mcp.tools.graph.query
- src.mcp.tools.graph.schema
- src.mcp.tools.graph.search

This __init__ avoids heavy imports and provides simple discovery helpers.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterable
from typing import List

PACKAGE = __name__  # e.g., "src.mcp.tools.graph"


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
