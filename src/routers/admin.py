"""
Admin-only router aggregator.

This module collects admin/runtime routers (model management, processes, jobs,
tenants, internal ops) and exposes them as a single composed router. The
application can mount it under an admin-only prefix (for example `/v1/admin`)
when operator enables admin routes via an environment variable.
"""
from __future__ import annotations

from contextlib import suppress

from fastapi import APIRouter, Security

from src.security.jwt import require_scopes

# Use Security with scopes so OpenAPI documents the required bearer scope.
_admin_guard = Security(require_scopes(None), scopes=["admin:all"])

# Router without tags - sub-routers provide their own tags
router = APIRouter()


def _include(module_path: str, prefix: str, skip_admin_guard: bool = False, router_name: str = "router") -> None:
    """
    Include a router from a module at the specified prefix.

    Args:
        module_path: Module path to import (e.g., "src.routers.model_instances")
        prefix: URL prefix for the router
        skip_admin_guard: If True, don't apply admin:all security requirement
        router_name: Name of the router to import from module (default: "router")
    """
    with suppress(Exception):
        mod = __import__(module_path, fromlist=[router_name])  # type: ignore
        sub = getattr(mod, router_name)
        # Only apply admin guard if not explicitly skipped (for routers with per-endpoint auth)
        deps = [] if skip_admin_guard else [_admin_guard]
        router.include_router(sub, prefix=prefix, dependencies=deps)


# Mount admin/runtime surfaces under their logical prefixes. These modules are
# left in-place (so they are still available for development), but they will
# only be reachable when the admin router is mounted by the app.
_include(
    "src.routers.model_management", "/models"
)  # Includes providers endpoints (instances endpoints are disabled in that router)
_include(
    "src.routers.model_instances", "/models", skip_admin_guard=True, router_name="admin_router"
)  # DEPRECATED: Legacy backward compat path, hidden from schema. Use /v1/models instead.
_include("src.routers.manifests", "")  # Already prefixed with /admin/models/manifests/builtins
_include("src.routers.model_processes", "/processes")
_include("src.routers.admin_jobs", "/jobs")
_include("src.routers.tenants_admin", "/tenants")
# Internal operations have been moved to the top-level internal prefix
# _include("src.routers.internal_ops", "/internal")
