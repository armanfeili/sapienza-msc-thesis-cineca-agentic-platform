"""
MCP Tool: catalog.discover

Return a catalog of available MCP tools as declared in the manifest, with
optional filtering and enrichment.

Actions
-------
- discover (default):
    Payload (all optional):
    {
      "prefix": "graph.",           # only tools whose name starts with this prefix
      "names_only": false,          # return just a list of tool names
      "categories_only": false,     # return just categories from the manifest
      "include_schemas": false,     # include input_schema/output_schema per tool
      "include_scopes": true,       # include 'scope' per tool
      "include_modules": false,     # include Python module path (best-effort)
      "sort": "name",               # "name" | "category"
      "limit": 100                  # limit number of tools returned
    }

    **P6 Feature**: Short-term caching of manifest (5 seconds) to reduce overhead.
"""

from __future__ import annotations

import time
from contextlib import suppress
from typing import Any

# ── Logging ───────────────────────────────────────────────────────────────────
with suppress(Exception):
    from src.logging_setup import get_logger  # type: ignore

    logger = get_logger(__name__)  # type: ignore[assignment]
if "logger" not in globals():
    import logging

    logger = logging.getLogger(__name__)

# ── P3 Pattern: ToolContext ───────────────────────────────────────────────────
with suppress(Exception):
    from src.mcp.decorator import mcp_tool  # type: ignore
with suppress(Exception):
    from src.mcp.context import ToolContext  # type: ignore

# ── MCP manifest helpers ──────────────────────────────────────────────────────
with suppress(Exception):
    from src.mcp import get_manifest, list_tool_specs  # type: ignore
if "get_manifest" not in globals():

    def get_manifest(**_: Any) -> dict[str, Any]:  # type: ignore
        return {"tools": [], "categories": []}

    def list_tool_specs(_: dict[str, Any] | None = None) -> list[dict[str, Any]]:  # type: ignore
        return []


# ── Module name resolver ──────────────────────────────────────────────────────
with suppress(Exception):
    from src.mcp.tools import module_name_for_tool  # type: ignore
if "module_name_for_tool" not in globals():

    def module_name_for_tool(name: str) -> str:  # type: ignore
        return "src.mcp.tools." + name


# ── Audit ─────────────────────────────────────────────────────────────────────
with suppress(Exception):
    from src.security.audit import audit_access  # type: ignore
if "audit_access" not in globals():

    def audit_access(**_: Any) -> None:  # type: ignore
        return


# ── Redis Cache ───────────────────────────────────────────────────────────────
_REDIS_AVAILABLE = False
try:
    from db.redis_cache.client import cache_get_json, cache_set_json  # type: ignore
    _REDIS_AVAILABLE = True
    logger.info("catalog.discover.redis_import_success", available=True)
except Exception as e:
    logger.warning("catalog.discover.redis_import_failed", error=str(e), available=False)
    def cache_get_json(_key: str) -> Any:  # type: ignore
        return None
    def cache_set_json(_key: str, _value: Any, ex: int | None = None) -> bool:  # type: ignore
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Catalog caching configuration (Phase 3: Tool Discovery Optimization)
# ─────────────────────────────────────────────────────────────────────────────
_CACHE: dict[str, Any] | None = None
_CACHE_TIME: float = 0

# Get cache TTL from settings (default: 1800s / 30 minutes)
try:
    from src.config import settings
    _CACHE_TTL: float = float(getattr(settings, "CATALOG_CACHE_TTL", 1800))
except Exception:
    _CACHE_TTL: float = 1800.0  # 30 minutes fallback


def _cached_manifest() -> dict[str, Any]:
    """
    Get manifest with configurable cache TTL.
    
    Phase 3 Enhancement: Uses CATALOG_CACHE_TTL (default: 30 minutes) to reduce
    overhead while ensuring tool changes are reflected within acceptable timeframe.
    """
    global _CACHE, _CACHE_TIME
    now = time.time()

    if _CACHE is None or (now - _CACHE_TIME) > _CACHE_TTL:
        _CACHE = get_manifest()
        _CACHE_TIME = now
        logger.debug("catalog.manifest_cache.refreshed", extra={"ttl": _CACHE_TTL})

    return _CACHE


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _category_of(tool_name: str) -> str:
    """Extract category from tool name (e.g., 'graph.query' -> 'graph')."""
    return tool_name.split(".", 1)[0] if "." in tool_name else "misc"


def _bool(payload: dict[str, Any], key: str, default: bool) -> bool:
    """Safe boolean extraction."""
    return bool(payload.get(key, default))


# ─────────────────────────────────────────────────────────────────────────────
# P3 Internal Action Handler
# ─────────────────────────────────────────────────────────────────────────────


def _act_discover(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Discover MCP tools based on the JSON manifest, with optional filters.

    P6 Feature: Uses short-term cached manifest (5s TTL) to reduce overhead.
    Redis Session Cache: Uses Redis cache per tenant+session (3600s TTL) to avoid
    redundant calls within the same agent run.
    """
    prefix = str(payload.get("prefix") or "")
    names_only = _bool(payload, "names_only", False)
    categories_only = _bool(payload, "categories_only", False)
    include_schemas = _bool(payload, "include_schemas", False)
    include_scopes = _bool(payload, "include_scopes", True)
    include_modules = _bool(payload, "include_modules", False)
    sort = str(payload.get("sort") or "name").lower()
    try:
        limit = int(payload.get("limit")) if payload.get("limit") is not None else None
    except Exception:
        limit = None

    # Build cache key from context and payload signature
    # CRITICAL: Do NOT include session_id - catalog is tenant-scoped, not session-scoped
    # Including session_id breaks caching because each tool call gets a different session context
    tenant_id = getattr(ctx, "tenant_id", None) or "default"
    # Include payload parameters in cache key for correctness
    cache_key = f"catalog:{tenant_id}:{prefix}:{names_only}:{categories_only}:{include_schemas}:{include_scopes}:{include_modules}:{sort}:{limit}"

    # Log cache key for debugging (INFO level so it appears in test logs)
    logger.info(
        "catalog.discover.cache_check",
        cache_key=cache_key,
        tenant_id=tenant_id,
        redis_available=_REDIS_AVAILABLE
    )

    # Try Redis cache first (tenant-scoped, 1 hour TTL) - only if Redis is available
    if _REDIS_AVAILABLE:
        try:
            cached = cache_get_json(cache_key)
            if cached is not None and isinstance(cached, dict) and cached.get("ok"):
                logger.info(
                    "catalog.discover.cache_hit",
                    tenant_id=tenant_id,
                    prefix=prefix,
                    cache_key=cache_key,
                )
                return cached
            else:
                logger.info(
                    "catalog.discover.cache_miss",
                    tenant_id=tenant_id,
                    cached_value=type(cached).__name__ if cached else "None",
                )
        except Exception as e:
            logger.warning("catalog.discover.cache_get_failed", error=str(e))
    else:
        logger.debug("catalog.discover.cache_skipped", reason="redis_not_available")

    # P6 Feature: Use cached manifest
    manifest = _cached_manifest()
    tool_specs = list_tool_specs(manifest)

    # Categories-only short-circuit
    if categories_only:
        cats = manifest.get("categories") or []
        res = {"ok": True, "categories": cats, "count": len(cats)}
        # Audit
        with suppress(Exception):
            audit_access(
                principal=None,
                resource="mcp.tools.catalog.discover",
                action="read",
                allowed=True,
                attributes={"mode": "categories"},
            )
        return res

    # Filter + map
    items: list[dict[str, Any]] = []
    for spec in tool_specs:
        name = spec.get("name")
        if not name or not isinstance(name, str):
            continue
        if prefix and not name.startswith(prefix):
            continue

        if names_only:
            items.append({"name": name})
            continue

        entry: dict[str, Any] = {
            "name": name,
            "description": spec.get("description"),
            "category": _category_of(name),
        }
        if include_scopes and "scope" in spec:
            entry["scope"] = spec.get("scope")
        if include_schemas:
            if "input_schema" in spec:
                entry["input_schema"] = spec["input_schema"]
            if "output_schema" in spec:
                entry["output_schema"] = spec["output_schema"]
        if include_modules:
            entry["module"] = module_name_for_tool(name)

        items.append(entry)

    # Sort
    if sort == "category":
        items.sort(key=lambda x: (x.get("category") or "", x.get("name") or ""))
    else:
        items.sort(key=lambda x: x.get("name") or "")

    # Limit
    if limit is not None and limit >= 0:
        items = items[:limit]

    # Build response
    if names_only:
        out = {"ok": True, "names": [i["name"] for i in items], "count": len(items)}
    else:
        out = {
            "ok": True,
            "count": len(items),
            "items": items,
            "categories": manifest.get("categories") or [],
            "manifest": {
                "id": manifest.get("id"),
                "version": manifest.get("version"),
                "schema_version": manifest.get("schema_version"),
            },
        }

    # Audit
    with suppress(Exception):
        audit_access(
            principal=None,
            resource="mcp.tools.catalog.discover",
            action="read",
            allowed=True,
            attributes={
                "prefix": prefix,
                "names_only": names_only,
                "include_schemas": include_schemas,
                "include_modules": include_modules,
                "returned": out.get("count", 0),
            },
        )

    # Store in Redis cache (configurable TTL for tenant-scoped results) - only if Redis is available
    # Default: 3600s (1 hour), configurable via CATALOG_CACHE_TTL environment variable
    # Shorter TTL (60-300s) recommended for dev environments with hot-reload
    if _REDIS_AVAILABLE:
        try:
            import os
            catalog_cache_ttl = int(os.getenv("CATALOG_CACHE_TTL", "3600"))
            success = cache_set_json(cache_key, out, ex=catalog_cache_ttl)
            if success:
                logger.info(
                    "catalog.discover.cache_set_success",
                    tenant_id=tenant_id,
                    prefix=prefix,
                    count=out.get("count", 0),
                    ttl=catalog_cache_ttl,
                )
            else:
                logger.warning(
                    "catalog.discover.cache_set_returned_false",
                    tenant_id=tenant_id,
                )
        except Exception as e:
            logger.warning("catalog.discover.cache_set_failed", error=str(e))
    else:
        logger.debug("catalog.discover.cache_set_skipped", reason="redis_not_available")

    return out


# ─────────────────────────────────────────────────────────────────────────────
# P3 Decorated Entry Point
# ─────────────────────────────────────────────────────────────────────────────

if "mcp_tool" in globals():

    @mcp_tool(tool_name="catalog.discover", required_scope="tools:catalog")
    def catalog_discover(
        ctx: ToolContext, payload: dict[str, Any] | None = None, **kwargs: Any  # type: ignore
    ) -> dict[str, Any]:
        """Entry function for catalog.discover tool (P3 pattern)."""
        payload = payload or {}
        try:
            return _act_discover(ctx, payload)
        except Exception as e:
            logger.exception("catalog.discover failed")
            return {"ok": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Fallback Entry Point
# ─────────────────────────────────────────────────────────────────────────────

if "mcp_tool" not in globals():

    def catalog_discover(ctx: Any = None, payload: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        """Fallback entry function for catalog.discover tool."""
        # Handle context from orchestrator (passed as 'context' kwarg)
        if ctx is None and "context" in kwargs:
            # Create a simple object with attributes from the context dict
            class ContextObject:
                def __init__(self, **attrs):
                    for k, v in attrs.items():
                        setattr(self, k, v)
            
            ctx = ContextObject(**kwargs["context"])
        
        payload = payload or {}
        try:
            return _act_discover(ctx, payload)
        except Exception as e:
            logger.exception("catalog.discover failed")
            return {"ok": False, "error": str(e)}


# Aliases
invoke = catalog_discover
run = catalog_discover
handle = catalog_discover


def describe() -> dict[str, Any]:
    """Static descriptor for discovery/UX."""
    return {
        "name": "catalog.discover",
        "summary": "Discover available MCP tools with filtering",
        "features": ["manifest_caching", "filtering", "enrichment"],
    }
