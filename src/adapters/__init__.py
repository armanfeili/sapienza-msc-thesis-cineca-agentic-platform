"""
Adapters package: lazy access to IO/DB/LLM/MCP adapters.

This module exposes convenient, lazily-imported symbols so callers can write:

    from src.adapters import get_client, query          # Memgraph
    from src.adapters import get_redis, cache_get       # Redis
    from src.adapters import complete, list_models      # LLM
    from src.adapters import get_mcp_client             # MCP client

Nothing is imported until you first access an attribute, avoiding import-time
side effects and keeping startup fast.
"""

from __future__ import annotations

import importlib
from typing import Any, Dict

# Map public names -> (module, attribute)
_EXPORTS: dict[str, tuple[str, str]] = {
    # ---- Redis ----
    "get_redis": ("src.adapters.redis", "get_redis"),
    "redis_available": ("src.adapters.redis", "redis_available"),
    "redis_health": ("src.adapters.redis", "redis_health"),
    "cache_set": ("src.adapters.redis", "cache_set"),
    "cache_get": ("src.adapters.redis", "cache_get"),
    "cache_delete": ("src.adapters.redis", "cache_delete"),
    "cache_set_json": ("src.adapters.redis", "cache_set_json"),
    "cache_get_json": ("src.adapters.redis", "cache_get_json"),
    "incr_with_ttl": ("src.adapters.redis", "incr_with_ttl"),
    "ttl": ("src.adapters.redis", "ttl"),
    # ---- Memgraph (DB) ----
    "DBError": ("src.adapters.db_memgraph", "DBError"),
    "DBUnavailable": ("src.adapters.db_memgraph", "DBUnavailable"),
    "get_client": ("src.adapters.db_memgraph", "get_client"),
    "close_client": ("src.adapters.db_memgraph", "close_client"),
    "mg_health": ("src.adapters.db_memgraph", "mg_health"),
    "query": ("src.adapters.db_memgraph", "query"),
    "query_one": ("src.adapters.db_memgraph", "query_one"),
    "execute": ("src.adapters.db_memgraph", "execute"),
    "ensure_index": ("src.adapters.db_memgraph", "ensure_index"),
    "upsert_node": ("src.adapters.db_memgraph", "upsert_node"),
    "upsert_relationship": ("src.adapters.db_memgraph", "upsert_relationship"),
    "wipe_all": ("src.adapters.db_memgraph", "wipe_all"),
    # ---- LLM ----
    "list_models": ("src.adapters.llm", "list_models"),
    "get_default_model": ("src.adapters.llm", "get_default_model"),
    "set_default_model": ("src.adapters.llm", "set_default_model"),
    "load_model": ("src.adapters.llm", "load_model"),
    "unload_model": ("src.adapters.llm", "unload_model"),
    "complete": ("src.adapters.llm", "complete"),
    "test": ("src.adapters.llm", "test"),
    # ---- MCP client ----
    "MCPClient": ("src.adapters.mcp_client", "MCPClient"),
    "get_mcp_client": ("src.adapters.mcp_client", "get_mcp_client"),
    "MCPError": ("src.adapters.mcp_client", "MCPError"),
    "ToolNotFound": ("src.adapters.mcp_client", "ToolNotFound"),
    "ToolInvocationError": ("src.adapters.mcp_client", "ToolInvocationError"),
    "ToolInfo": ("src.adapters.mcp_client", "ToolInfo"),
}

__all__ = list(_EXPORTS.keys())


def __getattr__(name: str) -> Any:
    """PEP 562: lazily import adapter symbols on first access."""
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    mod_name, attr = _EXPORTS[name]
    module = importlib.import_module(mod_name)
    value = getattr(module, attr)
    globals()[name] = value  # cache for future lookups
    return value


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + __all__)
