"""
MCP Tools — Tenancy package

This package aggregates tenancy-related tools under a single registry so the
MCP loader can discover them without importing individual modules directly.

It exposes:
- TOOLS: mapping of tool-name → callable(payload: dict | None, **kwargs) -> dict
- DESCRIPTORS: optional mapping of tool-name → static description/metadata
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Dict

# Public registries discovered by the MCP loader
TOOLS: dict[str, Callable[..., Any]] = {}
DESCRIPTORS: dict[str, dict[str, Any]] = {}

# Optional import: each tool module should expose an `invoke(payload, **kwargs)` function
try:
    from . import manage as _manage  # type: ignore

    if hasattr(_manage, "invoke"):
        TOOLS["tenancy.manage"] = _manage.invoke  # main entrypoint
    if hasattr(_manage, "describe"):
        # Optional static descriptor (schema/help text) if provided by the tool
        try:
            DESCRIPTORS["tenancy.manage"] = _manage.describe()  # type: ignore
        except Exception:
            # Descriptor is optional; ignore failures to keep import resilient
            pass
except Exception:
    # Keep import resilient if optional dependencies are missing
    pass

__all__ = ["DESCRIPTORS", "TOOLS"]
