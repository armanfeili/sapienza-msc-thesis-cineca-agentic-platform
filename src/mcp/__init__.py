"""
MCP package: manifest/policy loaders and lightweight tool discovery.

This module is intentionally side-effect free. It provides:
- Cached loading of the MCP JSON manifest (`src/mcp/manifest.json`)
- Helper accessors for tool specs defined in the manifest
- Optional YAML policy loader for `src/mcp/policies.yaml` (best-effort)
- Introspection utilities to list Python tool modules under `src.mcp.tools`

Nothing heavy is imported at module import time.
"""

from __future__ import annotations

import importlib
import json
import os
import pkgutil
import time
from collections.abc import Iterable
from contextlib import suppress
from typing import Any, Dict, List, Optional, Tuple

# Optional YAML
try:  # pragma: no cover
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

# Optional logging (structlog if app configured; else stdlib)
with suppress(Exception):
    from src.logging_setup import get_logger  # type: ignore

    logger = get_logger(__name__)  # type: ignore[assignment]
if "logger" not in globals():
    import logging

    logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Paths & basic config
# --------------------------------------------------------------------------- #


def manifest_path() -> str:
    """Return the default path to the MCP manifest JSON file."""
    return os.path.join("src", "mcp", "manifest.json")


def policy_path() -> str:
    """Return the default path to the MCP policies YAML file."""
    return os.path.join("src", "mcp", "policies.yaml")


TOOLS_PACKAGE = "src.mcp.tools"  # Python package path for tool modules


# --------------------------------------------------------------------------- #
# Manifest cache
# --------------------------------------------------------------------------- #

_MANIFEST_CACHE: dict[str, Any] | None = None
_MANIFEST_MTIME: float | None = None
_MANIFEST_FILE: str | None = None


def _load_manifest_file(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("manifest JSON must be an object")
    return data


def get_manifest(*, path: str | None = None, force_reload: bool = False) -> dict[str, Any]:
    """
    Load (and cache) the MCP manifest.

    - If `force_reload` is True, bypass the cache.
    - If the file's mtime changes on disk, the cache is refreshed automatically.
    """
    global _MANIFEST_CACHE, _MANIFEST_MTIME, _MANIFEST_FILE
    path = path or _MANIFEST_FILE or manifest_path()
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        # If manifest missing, return an empty skeleton (non-fatal for dev)
        logger.warning("mcp manifest not found at %s", path)
        _MANIFEST_CACHE = {"tools": [], "categories": []}
        _MANIFEST_MTIME = None
        _MANIFEST_FILE = path
        return _MANIFEST_CACHE

    if force_reload or _MANIFEST_CACHE is None or mtime != _MANIFEST_MTIME or path != _MANIFEST_FILE:
        _MANIFEST_CACHE = _load_manifest_file(path)
        _MANIFEST_MTIME = mtime
        _MANIFEST_FILE = path
        logger.info("mcp_manifest_loaded", path=path, tools=len(_MANIFEST_CACHE.get("tools", [])))
    return _MANIFEST_CACHE


def list_tool_specs(manifest: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return the list of tool spec dicts from the manifest."""
    m = manifest or get_manifest()
    tools = m.get("tools") or []
    return [t for t in tools if isinstance(t, dict)]


def list_tool_names(manifest: dict[str, Any] | None = None) -> list[str]:
    """Return the list of tool names defined in the manifest."""
    return [str(t.get("name")) for t in list_tool_specs(manifest) if "name" in t]


def get_tool_spec(name: str, manifest: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Return the tool spec dict by name (or None)."""
    for t in list_tool_specs(manifest):
        if t.get("name") == name:
            return t
    return None


# --------------------------------------------------------------------------- #
# Policy loader (best-effort; YAML optional)
# --------------------------------------------------------------------------- #

_POLICIES_CACHE: dict[str, Any] | None = None
_POLICIES_MTIME: float | None = None
_POLICIES_FILE: str | None = None


def get_policies(*, path: str | None = None, force_reload: bool = False) -> dict[str, Any]:
    """
    Load (and cache) the MCP policies YAML into a dict. If PyYAML is unavailable
    or the file is missing, returns {} (non-fatal).
    """
    global _POLICIES_CACHE, _POLICIES_MTIME, _POLICIES_FILE
    path = path or _POLICIES_FILE or policy_path()
    if yaml is None:  # pragma: no cover
        logger.debug("PyYAML not installed; skipping policies load")
        _POLICIES_CACHE = _POLICIES_CACHE or {}
        _POLICIES_FILE = path
        _POLICIES_MTIME = None
        return _POLICIES_CACHE

    try:
        mtime = os.path.getmtime(path)
    except OSError:
        _POLICIES_CACHE = _POLICIES_CACHE or {}
        _POLICIES_FILE = path
        _POLICIES_MTIME = None
        return _POLICIES_CACHE

    if force_reload or _POLICIES_CACHE is None or mtime != _POLICIES_MTIME or path != _POLICIES_FILE:
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if not isinstance(data, dict):
                data = {}
            _POLICIES_CACHE = data
            _POLICIES_MTIME = mtime
            _POLICIES_FILE = path
            logger.info("mcp_policies_loaded", path=path)
        except Exception as e:  # pragma: no cover
            logger.warning("failed to load policies from %s: %s", path, e)
            _POLICIES_CACHE = _POLICIES_CACHE or {}
    return _POLICIES_CACHE


# --------------------------------------------------------------------------- #
# Python tool module discovery (optional convenience)
# --------------------------------------------------------------------------- #


def iter_tool_modules(package: str = TOOLS_PACKAGE) -> Iterable[str]:
    """
    Yield fully-qualified module names under the given tools package.
    Only lists available modules; does not import them.
    """
    try:
        pkg = importlib.import_module(package)
    except Exception:
        return []
    if not hasattr(pkg, "__path__"):
        return []
    for modinfo in pkgutil.walk_packages(pkg.__path__, prefix=pkg.__name__ + "."):
        yield modinfo.name


def list_tool_modules(package: str = TOOLS_PACKAGE) -> list[str]:
    return list(iter_tool_modules(package))


# --------------------------------------------------------------------------- #
# Diagnostics
# --------------------------------------------------------------------------- #


def describe() -> dict[str, Any]:
    """Return a summary of the current manifest/policies state."""
    m = get_manifest()
    p = get_policies()
    return {
        "manifest_file": _MANIFEST_FILE or manifest_path(),
        "manifest_mtime": _MANIFEST_MTIME,
        "tools_count": len(m.get("tools", [])),
        "tool_names": list_tool_names(m),
        "categories": m.get("categories", []),
        "policies_file": _POLICIES_FILE or policy_path(),
        "policies_loaded": bool(p),
        "now": int(time.time()),
    }


__all__ = [
    "TOOLS_PACKAGE",
    "describe",
    "get_manifest",
    "get_policies",
    "get_tool_spec",
    "iter_tool_modules",
    "list_tool_modules",
    "list_tool_names",
    "list_tool_specs",
    "manifest_path",
    "policy_path",
]
