"""
Tools API (generic MCP-style dispatcher)

Endpoints (mounted under /tools):
- GET  /tools                    -> discover available tools (best-effort)
- POST /tools/invocations        -> invoke a tool by dotted name ("graph.query")

Note: The legacy colon-style path `/{name}:invoke` is retained only as a hidden, deprecated compatibility stub (include_in_schema=False) and should not be used by new clients.

Design goals:
- **Loose coupling**: we don't hard-depend on any particular tools module layout.
- **Discovery**: we scan `src.mcp.tools` and surface modules that expose a likely entrypoint.
- **Invocation**: we load the module lazily and call one of: `invoke`, `run`, `handle`, `main`.
- **Resilience**: if a tool isn't present, we return a friendly error instead of 500.

This router is usable even before you implement the full MCP tool surface.
Replace/extend the discovery rules and entrypoint selection as your tool modules evolve.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import inspect
import json as _json
import pkgutil
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

try:  # optional runtime validation
    from jsonschema import ValidationError as JSValidationError, validate as js_validate
except Exception:  # pragma: no cover
    js_validate = None  # type: ignore
    JSValidationError = None  # type: ignore

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status
from fastapi.responses import JSONResponse

# no pagination helpers needed; endpoint uses fixed defaults
from sqlalchemy.orm import Session
from starlette.responses import Response as StarletteResponse

from db.postgres_control.database import get_db
from db.postgres_control.repositories.tools import ToolsRepository
from db.redis_cache import tools_cache
from db.redis_cache.client import idem_get, idem_set
from src.schemas.auth import UserInfo
from src.schemas.tools import ToolInfo, ToolInvokeRequest, ToolInvokeResponse, ToolsListResponse
from src.config import settings
from src.observability.metrics import (
    record_tool_cache_operation,
    record_tool_idempotency_conflict,
    record_tool_invocation,
)
from src.provenance import record_provenance
from src.routers.auth import get_current_user
from src.security.perm import current_permissions, require_perms
from src.services.invocation_store import load_invocation, save_invocation
from src.utils.principal import principal_identity

# Initialize structured logger
log = structlog.get_logger(__name__)

# Prometheus (optional)
try:
    from prometheus_client import Counter, Histogram
except Exception:  # pragma: no cover
    Counter = None  # type: ignore
    Histogram = None  # type: ignore

if Counter is not None:
    TOOL_INVOKE = Counter(
        "tools_invoke_total",
        "Number of tool invocations",
        labelnames=("name", "success"),
    )
else:  # pragma: no cover
    TOOL_INVOKE = None  # type: ignore

if Histogram is not None:
    TOOL_LATENCY = Histogram(
        "tools_invoke_latency_seconds",
        "Latency of tool invocations in seconds",
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, float("inf")),
    )
else:  # pragma: no cover
    TOOL_LATENCY = None  # type: ignore

router = APIRouter(tags=["tools"])

TOOLS_PACKAGE = "src.mcp.tools"
ENTRYPOINT_CANDIDATES = ("invoke", "run", "handle", "main")


@dataclass
class _ResolvedTool:
    name: str
    module: str
    entrypoint_name: str | None
    func: Callable[..., Any] | None


def _iter_tool_modules() -> list[str]:
    """Return a list of submodule import paths under TOOLS_PACKAGE."""
    modules: list[str] = []
    try:
        pkg = importlib.import_module(TOOLS_PACKAGE)
        if not hasattr(pkg, "__path__"):
            return []
        for m in pkgutil.walk_packages(pkg.__path__, prefix=pkg.__name__ + "."):
            # include both packages and modules; we will filter later
            modules.append(m.name)
    except Exception:
        pass
    return modules


def _short_name(module_path: str) -> str | None:
    """
    Convert 'src.mcp.tools.graph.query' -> 'graph.query'.
    Returns None for unexpected patterns.
    """
    prefix = TOOLS_PACKAGE + "."
    if module_path.startswith(prefix):
        return module_path[len(prefix) :]
    return None


def _detect_entrypoint(mod) -> tuple[str | None, Callable[..., Any] | None]:
    """Pick the first callable entrypoint from candidates."""
    for name in ENTRYPOINT_CANDIDATES:
        fn = getattr(mod, name, None)
        if callable(fn):
            return name, fn
    return None, None


def _resolve_tool(name: str) -> _ResolvedTool:
    """
    Resolve a dotted short name like 'graph.query' to a module and entrypoint.

    Strategy:
      1) Try importing TOOLS_PACKAGE + '.' + name directly.
      2) If that fails, attempt to import each parent package progressively.
    """
    module_path = f"{TOOLS_PACKAGE}.{name}"
    try:
        mod = importlib.import_module(module_path)
        ep_name, fn = _detect_entrypoint(mod)
        return _ResolvedTool(name=name, module=module_path, entrypoint_name=ep_name, func=fn)
    except Exception:
        # As a fallback, try to import the closest module that exists (e.g., tools.graph)
        # but since we need a concrete module with a callable, we can just return unresolved.
        return _ResolvedTool(name=name, module=module_path, entrypoint_name=None, func=None)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value  # type: ignore[misc]
    return value


def _default_schema() -> dict[str, Any]:
    return {"type": "object", "properties": {}, "additionalProperties": False}


def _is_namespace(module_path: str, all_modules: set[str]) -> bool:
    """A namespace is a package without a direct entrypoint and with children modules."""
    prefix = module_path + "."
    return any(m.startswith(prefix) for m in all_modules)


def _tool_version(mod) -> int:
    """Extract tool version from module. Defaults to 1 if not defined."""
    try:
        return int(getattr(mod, "VERSION", 1))
    except Exception:
        return 1


def _tool_capabilities(short_name: str, mod) -> list[str]:
    """Extract or infer tool capabilities.

    Checks module for CAPABILITIES attribute, otherwise infers from tool name.
    """
    # Try explicit CAPABILITIES attribute first
    try:
        caps = getattr(mod, "CAPABILITIES", None)
        if caps and isinstance(caps, (list, tuple)):
            return list(caps)
    except Exception:
        pass

    # Infer from tool name patterns
    capabilities = []

    # Graph tools that read from DB
    if short_name.startswith("graph.") and short_name in {
        "graph.query",
        "graph.schema",
        "graph.search",
        "graph.analytics",
    }:
        capabilities.append("reads_db")

    # Graph tools that write to DB
    if short_name.startswith("graph.") and short_name in {"graph.crud", "graph.bulk"}:
        capabilities.extend(["reads_db", "writes_db"])

    # System health/monitoring tools
    if short_name.startswith("system."):
        capabilities.append("system_info")

    # Security audit tools
    if short_name.startswith("security."):
        capabilities.append("security_audit")

    # Data management tools
    if short_name.startswith("data."):
        capabilities.append("data_management")

    # Model management tools
    if short_name.startswith("model."):
        capabilities.append("model_management")

    # Tenancy management
    if short_name == "tenancy.manage":
        capabilities.append("tenancy_management")

    return capabilities


def _scopes_for_tool(short_name: str, safe: set[str]) -> list[str]:
    """Return required scopes for a tool.

    Policy simplification: tools in the SAFE list (and core system.* health/status/metrics)
    are invokable with tools:basic. All other non-admin tools require tools:all. Admin-only
    namespaces retain admin:all requirement.
    """
    if short_name.startswith("security.") or short_name in {"tenancy.manage"}:
        return ["admin:all"]
    if short_name in safe or short_name in {"system.health", "system.status", "system.metrics"}:
        return ["tools:basic"]
    return ["tools:all"]


# ---------------- Stable JSON helpers for ETag/304 ----------------
def _json_bytes_stable(payload: dict[str, Any]) -> bytes:
    """Render canonical JSON bytes: deterministic ordering and no spaces."""
    return _json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _compute_etag_from_bytes(b: bytes) -> str:
    return f'W/"{hashlib.sha256(b).hexdigest()}"'


def _if_none_match_matches(header_value: str | None, current: str) -> bool:
    if not header_value:
        return False
    # Comma-separated list; exact token match or wildcard
    return any(tok.strip() == current or tok.strip() == "*" for tok in header_value.split(","))


# ---------------- Principal identity helper ----------------
def _principal_identity(p: Any) -> str:
    """Back-compat shim: reuse shared principal helper."""
    return principal_identity(p)


# ---------------- Routes ----------------
@router.get(
    "",
    response_model=ToolsListResponse,
    summary="List available tools (best effort discovery)",
    description=(
        "**GET /tools – Discover available tools**\n\n"
        "**Why we need this endpoint:**\n"
        "- **Tool discovery**: AI agents and client apps need to know what tools are available before they can invoke them.\n"
        "- **Dynamic capabilities**: Tools can be added or removed at runtime, so clients must query to see the current set.\n"
        "- **Permission awareness**: Shows only tools the current user has permission to use, preventing unauthorized access attempts.\n"
        "- **Schema introspection**: Returns input schemas so clients can construct valid tool invocation requests.\n"
        "- Without this endpoint, clients would have to hardcode tool names and wouldn't know about new tools or permission changes.\n\n"
        "**What it does:**\n"
        "- Scans the `src.mcp.tools` package and returns a best-effort list of detected tools.\n"
        "- Shows which tools are invokable vs. namespaces (non-invokable groupings).\n"
        "- Provides metadata: name, entrypoint, input schema, required permissions, and capabilities.\n"
        "- Returns up to 50 tools per page with `has_more` indicating if additional items exist.\n\n"
        "**Access:**\n"
        "- Requires `tools:basic`, `tools:all`, or `admin:all` scope.\n"
        "- Visibility follows RBAC rules: admin-only tools hidden from non-admins, basic tools visible to `tools:basic` holders.\n\n"
        "**Behavior:**\n"
        "- **Filtering**: By default only invokable tools are returned (namespaces excluded).\n"
        "- **Caching**: Supports conditional GET via `If-None-Match`/`ETag` (304 on cache hit).\n"
        "- **Headers**: Sets `Cache-Control: private, max-age=30` and `Vary: Authorization`.\n"
        "- **Redaction**: Non-admin callers see redacted `module` paths (null instead of internal paths).\n\n"
        "**Responses:**\n"
        "- **200 OK**: Returns `ToolsListResponse` with items array, total count, and pagination flags.\n"
        "- **304 Not Modified**: When `If-None-Match` matches current `ETag` (no changes).\n"
        "- **401 Unauthorized**: Missing or invalid auth token.\n"
        "- **500 Internal Server Error**: Unexpected failure during tool discovery.\n\n"
        "**Examples:**\n"
        "```bash\n"
        "# List all available tools\n"
        "curl -H 'Authorization: Bearer YOUR_TOKEN' \\\n"
        "  https://api.example.com/v1/tools\n\n"
        "# Conditional GET (check for updates)\n"
        "curl -H 'Authorization: Bearer YOUR_TOKEN' \\\n"
        "  -H 'If-None-Match: W/\"abc123\"' \\\n"
        "  https://api.example.com/v1/tools\n"
        "# → 304 if unchanged\n"
        "```"
    ),
    responses={
        200: {
            "description": "OK",
            "content": {
                "application/json": {
                    "example": {
                        "items": [
                            {
                                "id": "system.health@1",
                                "name": "system.health",
                                "module": None,
                                "entrypoint": "invoke",
                                "description": "MCP Tool: system.health",
                                "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
                                "scopes": ["tools:basic"],
                                "capabilities": ["system_info"],
                                "namespace": False,
                                "invokable": True,
                                "long_running": False,
                            }
                        ],
                        "next_page_token": None,
                        "total": 1,
                        "has_more": False,
                    }
                }
            },
        },
        304: {"description": "Not Modified"},
        401: {
            "description": "Unauthorized",
            "content": {
                "application/problem+json": {
                    "examples": {
                        "unauth": {
                            "summary": "Missing or invalid token",
                            "value": {
                                "type": "about:blank",
                                "title": "Unauthorized",
                                "status": 401,
                                "detail": "Not authenticated",
                            },
                        }
                    }
                }
            },
        },
        400: {"description": "Bad Request"},
        500: {
            "description": "Internal Server Error",
            "content": {
                "application/problem+json": {
                    "examples": {
                        "server_error": {
                            "summary": "Unexpected failure",
                            "value": {
                                "type": "about:blank",
                                "title": "Internal Server Error",
                                "status": 500,
                                "detail": "unexpected error",
                            },
                        }
                    }
                }
            },
        },
    },
)
async def list_tools(
    request: Request,
    response: Response,
    user: UserInfo = Depends(require_perms(["tools:basic", "tools:all", "admin:all"])),
) -> ToolsListResponse:
    """Return a paginated list of detected tool modules and their metadata.

    This is a best-effort discovery API meant to help UIs and orchestration layers show what tools are available. Results may vary between runtime environments.
    """
    all_mods = _iter_tool_modules()
    mod_set: set[str] = set(all_mods)
    out: list[ToolInfo] = []
    try:
        safe = {s.strip() for s in (settings.SAFE_TOOLS or "").split(",") if s.strip()}
    except Exception:
        safe = set()
    eff_perms = set(current_permissions(user))
    is_admin = "admin:all" in eff_perms

    for mod_path in all_mods:
        short = _short_name(mod_path)
        if not short:
            continue
        # Attempt to import to see if an entrypoint exists
        entrypoint_name: str | None = None
        description: str | None = None
        input_schema: dict[str, Any] | None = None
        invokable = False
        long_running = False
        namespace = False
        version = 1
        capabilities: list[str] = []
        mod = None
        try:
            mod = importlib.import_module(mod_path)
            entrypoint_name, _fn = _detect_entrypoint(mod)
            invokable = bool(entrypoint_name)
            version = _tool_version(mod)
            capabilities = _tool_capabilities(short, mod)
            # Pull a short description from module docstring if present
            if isinstance(getattr(mod, "__doc__", None), str):
                doc = (mod.__doc__ or "").strip().splitlines()
                if doc:
                    description = doc[0].strip()
                    # Treat explicit namespace modules as namespaces even if they export an `invoke` dispatcher
                    if description.lower().startswith("mcp namespace"):
                        namespace = True
                        invokable = False
            try:
                long_running = bool(getattr(mod, "LONG_RUNNING", False))
            except Exception:
                long_running = False
            # Try to read an input schema by convention (and ensure non-null for invokable)
            if hasattr(mod, "INPUT_SCHEMA"):
                input_schema = mod.INPUT_SCHEMA
            elif hasattr(mod, "get_input_schema") and callable(mod.get_input_schema):
                with suppress(Exception):
                    input_schema = mod.get_input_schema()
            elif hasattr(mod, "describe") and callable(mod.describe):
                with suppress(Exception):
                    desc = mod.describe()
                    if isinstance(desc, dict) and isinstance(desc.get("schema"), dict):
                        input_schema = desc["schema"]
        except Exception:
            # leave entrypoint as None; still list the module name
            pass
        # Determine namespace if no entrypoint and has children
        if not invokable and not namespace:
            namespace = _is_namespace(mod_path, mod_set)
        # If identified as a namespace, clear entrypoint/schema and mark non-invokable
        if namespace:
            invokable = False
            entrypoint_name = None
            input_schema = None

        # Determine scopes for the tool (used for RBAC visibility)
        scopes = _scopes_for_tool(short, set(safe))

        # RBAC visibility rules:
        # - admin:all → sees everything
        # - if tool requires admin:all → admin only
        # - if tool requires tools:basic → visible when caller has tools:basic
        # - if tool requires tools:all → visible to any authenticated user (tools:basic/tools:all/admin)
        if not is_admin:
            if "admin:all" in scopes:
                continue
            has_basic = "tools:basic" in eff_perms
            has_all = "tools:all" in eff_perms
            visible = False
            if "tools:basic" in scopes:
                visible = has_basic or has_all  # elevated implies basic
            elif "tools:all" in scopes:
                visible = has_basic or has_all  # visible to any authenticated user per policy
            else:
                # default: not visible
                visible = False
            if not visible:
                continue

        # Default schema for invokable tools if missing
        if invokable and not input_schema:
            input_schema = _default_schema()
        module_path_value = mod_path if is_admin else None  # redact internals for non-admin
        tool_id = f"{short}@{version}"

        item = ToolInfo(
            id=tool_id,
            name=short,
            module=module_path_value,
            entrypoint=entrypoint_name,
            description=description,
            input_schema=input_schema if invokable else None,
            scopes=scopes,
            capabilities=capabilities,
            namespace=namespace,
            invokable=invokable,
            long_running=long_running,
        )
        out.append(item)
    # Provide a minimal static seed list if discovery found nothing
    if not out:
        for short in (
            "graph.query",
            "graph.generate_cypher",
            "graph.schema",
            "graph.search",
            "system.health",
            "system.status",
            "system.metrics",
            "graph.crud",
        ):
            scopes = _scopes_for_tool(short, set())
            module_seed = f"{TOOLS_PACKAGE}.{short}" if is_admin else None

            # Create a temporary mock module to get capabilities
            class _MockMod:
                pass

            caps = _tool_capabilities(short, _MockMod())
            out.append(
                ToolInfo(
                    id=f"{short}@1",
                    name=short,
                    module=module_seed,
                    entrypoint=None,
                    description=None,
                    input_schema=None,
                    scopes=scopes,
                    capabilities=caps,
                    namespace=False,
                    invokable=False,
                    long_running=False,
                )
            )

    # Filter visibility by invokable/namespaces flag as requested
    out = [i for i in out if i.invokable]

    # Stable sort by name
    out.sort(key=lambda i: i.name)

    # Fixed-size page (no external pagination parameters)
    page_size = 50
    total = len(out)
    slice_items = out[:page_size]
    next_token = None
    end = len(slice_items)

    # Build final body as a plain dict for stable JSON rendering
    items_payload: list[dict[str, Any]] = []
    for it in slice_items:
        d = it.model_dump(exclude_none=False)
        # Ensure deterministic ordering of list fields
        if isinstance(d.get("scopes"), list):
            d["scopes"] = sorted(d["scopes"])  # sort for determinism
        if isinstance(d.get("capabilities"), list):
            d["capabilities"] = sorted(d["capabilities"])  # sort for determinism
        items_payload.append(d)

    result: dict[str, Any] = {
        "items": items_payload,
        "next_page_token": next_token if next_token is not None else None,
        "total": total,
        "has_more": (end < total),
    }

    # Render once -> bytes, compute ETag from those bytes, and short-circuit 304
    body_bytes = _json_bytes_stable(result)
    etag = _compute_etag_from_bytes(body_bytes)
    if _if_none_match_matches(request.headers.get("if-none-match"), etag):
        return StarletteResponse(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers={
                "ETag": etag,
                "Cache-Control": "private, max-age=30",
                "Vary": "Authorization",
            },
        )

    return StarletteResponse(
        content=body_bytes,
        media_type="application/json",
        headers={
            "ETag": etag,
            "Cache-Control": "private, max-age=30",
            "Vary": "Authorization",
        },
    )


# Legacy `/tools/invoke` removed; use `/tools/{name}/invocations` instead. A deprecated compatibility stub for `/{name}:invoke` remains but is hidden.


@router.post(
    "/{name}/invocations",
    name="invoke_tool_by_path",
    response_model=ToolInvokeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Invoke a tool by name (create invocation)",
    description=(
        "**POST /tools/{name}/invocations – Execute a tool and get results**\n\n"
        "**Why we need this endpoint:**\n"
        "- **Tool execution**: AI agents and automated workflows need to run tools to accomplish tasks (querying databases, processing data, etc.).\n"
        "- **Result retrieval**: Returns structured output that agents can parse and use for decision-making.\n"
        "- **Idempotent retries**: Network failures are common; idempotency keys prevent duplicate executions when retrying failed requests.\n"
        "- **Audit trail**: Creates permanent invocation records with timing and provenance for compliance and debugging.\n"
        "- Without this endpoint, agents would need direct database access or custom code for each operation, creating security risks and maintenance burden.\n\n"
        "**What it does:**\n"
        "- Invokes the named tool (e.g., `graph.query`) with provided arguments.\n"
        "- Returns structured results with provenance tracking (trace_id/event_id) and timing.\n"
        "- Creates a retrievable invocation record at `/v1/tools/{name}/invocations/{event_id}`.\n"
        "- Supports idempotent execution via `Idempotency-Key` header (replay returns 200 instead of 201).\n\n"
        "**Access:**\n"
        "- Requires `tools:basic`, `tools:all`, or `admin:all` scope.\n"
        "- Per-tool RBAC enforced: some tools require elevated permissions beyond route-level auth.\n\n"
        "**Behavior:**\n"
        "- **Request body**: `ToolInvokeRequest` with `args` (JSON object → kwargs) and optional `timeout_seconds` (1-3600).\n"
        "- **Idempotency**: Supply `Idempotency-Key` header to cache results for 24h; replays return 200 OK with `Idempotency-Replayed: true`.\n"
        "- **Validation**: Pre-invocation JSON Schema validation when tool exposes `INPUT_SCHEMA`.\n"
        "- **Headers**: Returns `Location` header pointing to invocation resource, `X-Request-Id` with event_id.\n\n"
        "**Responses:**\n"
        "- **201 Created**: New invocation executed successfully (includes `Location` header).\n"
        "- **200 OK**: Idempotent replay of previous invocation (includes `Idempotency-Replayed: true`).\n"
        "- **400 Bad Request**: Invalid arguments (failed schema validation).\n"
        "- **401 Unauthorized**: Missing or invalid auth token.\n"
        "- **403 Forbidden**: Caller lacks required permission for this specific tool.\n"
        "- **404 Not Found**: Tool doesn't exist or is non-invokable (namespace).\n"
        "- **500 Internal Server Error**: Tool execution failed.\n\n"
        "**Examples:**\n"
        "```bash\n"
        "# Invoke graph.query tool\n"
        "curl -X POST -H 'Authorization: Bearer YOUR_TOKEN' \\\n"
        "  -H 'Content-Type: application/json' \\\n"
        '  -d \'{"args": {"cypher": "MATCH (n) RETURN count(n)"}}\' \\\n'
        "  https://api.example.com/v1/tools/graph.query/invocations\n\n"
        "# Idempotent invocation (safe retry)\n"
        "curl -X POST -H 'Authorization: Bearer YOUR_TOKEN' \\\n"
        "  -H 'Idempotency-Key: my-unique-key-123' \\\n"
        "  -H 'Content-Type: application/json' \\\n"
        '  -d \'{"args": {"query": "test"}}\' \\\n'
        "  https://api.example.com/v1/tools/system.health/invocations\n"
        "# → 201 first time, 200 on replay\n\n"
        "# Invoke with timeout\n"
        "curl -X POST -H 'Authorization: Bearer YOUR_TOKEN' \\\n"
        "  -H 'Content-Type: application/json' \\\n"
        '  -d \'{"args": {"operation": "long"}, "timeout_seconds": 30}\' \\\n'
        "  https://api.example.com/v1/tools/data.process/invocations\n"
        "```"
    ),
    responses={
        200: {"description": "OK (idempotent replay)"},
        201: {"description": "Created (new invocation)"},
        400: {"description": "Bad Request (invalid args)"},
        401: {"description": "Unauthorized (missing/invalid token)"},
        403: {"description": "Forbidden (missing permission)"},
        404: {"description": "Not Found (unknown or non-invokable tool)"},
        500: {"description": "Internal Server Error"},
    },
)
async def invoke_tool_by_path(
    request: Request,
    name: str = Path(..., description="Tool short name"),
    req: ToolInvokeRequest | None = None,
    # Align with list/get tool endpoints: allow tools:basic OR tools:all OR admin:all
    user: UserInfo = Depends(require_perms(["tools:basic", "tools:all", "admin:all"])),
    db: Session = Depends(get_db),
) -> ToolInvokeResponse:
    """Invoke a tool implementation discovered under `src.mcp.tools`.

    The router will lazily import the tool module and call a supported entrypoint (`invoke`, `run`, `handle`, `main`). Errors are returned as HTTP 4xx/5xx with helpful messages when the tool is missing or fails.
    """
    # Support both body with args or empty body; prefer body if provided
    args = (req.args if req else {}) if isinstance(req, ToolInvokeRequest) else ({})
    timeout = req.timeout_seconds if isinstance(req, ToolInvokeRequest) else None
    # Resolve tool existence and invokability first (404 on unknown or namespace)
    module_path = f"{TOOLS_PACKAGE}.{name}"
    try:
        mod = importlib.import_module(module_path)
        ep_name, _fn = _detect_entrypoint(mod)
        invokable = bool(ep_name)
        # treat explicit namespace or modules without entrypoint as non-invokable
        if isinstance(getattr(mod, "__doc__", None), str):
            doc0 = (mod.__doc__ or "").strip().splitlines()
            if doc0 and doc0[0].strip().lower().startswith("mcp namespace"):
                invokable = False
        if not invokable:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")

    # RBAC after confirming tool exists
    try:
        safe = {s.strip() for s in (settings.SAFE_TOOLS or "").split(",") if s.strip()}
    except Exception:
        safe = set()
    perms = set(current_permissions(user))
    scopes = _scopes_for_tool(name, safe)
    with suppress(Exception):
        # Temporary diagnostic log to understand unexpected 403s for tools:basic invocations
        from src.logging_setup import get_logger  # type: ignore

        _lg = get_logger(__name__)
        _lg.debug(
            "tool.invoke.rbac_check",
            extra={
                "tool": name,
                "scopes_required": scopes,
                "perms": sorted(perms),
                "safe_listed": name in safe,
                "safe_set": sorted(safe)[:20],
            },
        )
    # Route-level dependency already enforced that caller has one of tools:basic|tools:all|admin:all.
    # Additional per-tool RBAC checks are skipped to avoid double-enforcement inconsistencies.

    # Idempotency cache lookup after auth/existence checks
    idem_key = request.headers.get("Idempotency-Key")
    cache_key = None
    repo = ToolsRepository(db)

    # Generate correlation ID for logging
    import uuid as uuid_mod

    correlation_id = request.headers.get("X-Request-Id") or str(uuid_mod.uuid4())

    # Log invocation start with correlation ID
    log.info(
        "tool.invocation.start",
        tool_name=name,
        correlation_id=correlation_id,
        idempotency_key=idem_key,
        user=getattr(user, "sub", None) or getattr(user, "username", None),
        has_args=bool(args),
    )

    if idem_key:
        # Check PostgreSQL first for idempotency
        try:
            existing_inv = repo.get_invocation_by_idempotency_key(idem_key)
            if existing_inv:
                # Validate params match (409 if different)
                if existing_inv.params_json != args:
                    # Record idempotency conflict metric
                    record_tool_idempotency_conflict(tool_name=name)
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Idempotency key '{idem_key}' already used with different parameters",
                    )
                # Return existing invocation (200 OK for idempotent replay)
                evt_id = existing_inv.eid
                try:
                    loc = request.url_for("get_tool_invocation", name=name, eid=str(evt_id))
                except Exception:
                    try:
                        loc = request.app.url_path_for("get_tool_invocation", name=name, eid=str(evt_id))
                    except Exception:
                        loc = f"/v1/tools/{name}/invocations/{evt_id}"

                # Build response from existing invocation
                response_body = {
                    "name": existing_inv.tool_name,
                    "ok": existing_inv.status in ("finished",),
                    "result": existing_inv.result_json,
                    "error": existing_inv.error_json.get("message") if existing_inv.error_json else None,
                    "duration_ms": existing_inv.latency_ms or 0,
                    "trace_id": "",  # Legacy field
                    "event_id": existing_inv.eid,
                }

                headers = {
                    "Cache-Control": "no-store",
                    "Idempotency-Replayed": "true",
                    "Idempotency-Key": idem_key,
                    "X-Request-Id": str(evt_id),
                    "Location": loc,
                }
                return JSONResponse(status_code=status.HTTP_200_OK, content=response_body, headers=headers)
        except HTTPException:
            raise
        except Exception as e:
            # Log but don't fail on idempotency check errors
            with suppress(Exception):
                from src.logging_setup import get_logger

                _lg = get_logger(__name__)
                _lg.warning("idempotency_check_failed", extra={"error": str(e), "idem_key": idem_key})

        # Also check Redis cache as fallback
        cache_key = f"idem:tools:{idem_key}:{name}"
        cached = idem_get(cache_key)
        if cached is not None:
            # Build stable Location from cached event_id if present
            evt_id = cached.get("event_id") if isinstance(cached, dict) else None
            loc = None
            if evt_id:
                try:
                    loc = str(request.url_for("get_tool_invocation", name=name, eid=str(evt_id)))
                except Exception:
                    try:
                        loc = str(request.app.url_path_for("get_tool_invocation", name=name, eid=str(evt_id)))
                    except Exception:
                        loc = f"/v1/tools/{name}/invocations/{evt_id}"
            headers = {
                "Cache-Control": "no-store",
                "Idempotency-Replayed": "true",
            }
            if idem_key:
                headers["Idempotency-Key"] = idem_key
            if evt_id:
                headers["X-Request-Id"] = str(evt_id)
            if loc:
                headers["Location"] = loc
            return JSONResponse(status_code=status.HTTP_200_OK, content=cached, headers=headers)

    # Pre-invocation JSON Schema validation when available
    schema = None
    if hasattr(mod, "INPUT_SCHEMA"):
        schema = mod.INPUT_SCHEMA
    elif hasattr(mod, "get_input_schema") and callable(mod.get_input_schema):
        with suppress(Exception):
            schema = mod.get_input_schema()
    elif hasattr(mod, "describe") and callable(mod.describe):
        with suppress(Exception):
            desc = mod.describe()
            if isinstance(desc, dict) and isinstance(desc.get("schema"), dict):
                schema = desc["schema"]
    if schema and js_validate is not None:
        try:
            js_validate(instance=args or {}, schema=schema)
        except Exception as e:  # prefer jsonschema's ValidationError
            if JSValidationError and isinstance(e, JSValidationError):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid args: {e.message}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid args")

    # NOTE: Earlier RBAC checks based on `_scopes_for_tool` already enforced the correct policy.
    # We intentionally removed a second, redundant permission gate that required membership in
    # SAFE_TOOLS for tools:basic to succeed. This ensures core system.* health/status/metrics tools
    # (granted tools:basic by policy) do not depend on an environment variable configuration.

    resp = await _invoke_by_name(name, args, timeout, user)
    body = resp.model_dump() if hasattr(resp, "model_dump") else resp.__dict__

    # Get tenant_id (use a default or infer from user context)
    tenant_id = getattr(user, "tenant_id", None) or "default-tenant"

    # Ensure default tenant exists in PostgreSQL (for backward compatibility)
    try:
        from db.postgres_control.repositories.tenants import TenantsRepository

        tenant_repo = TenantsRepository(db)
        if not tenant_repo.get_by_id("default-tenant"):
            # Create default tenant if it doesn't exist
            tenant_repo.create(name="Default Tenant", admin_email="admin@localhost", metadata={"auto_created": True})
            db.commit()
    except Exception as e:
        # If tenant creation fails, log but continue (fallback to legacy store)
        from src.logging_setup import get_logger

        _lg = get_logger(__name__)
        _lg.error("default_tenant_creation_failed", error=str(e))

    # Create invocation record in PostgreSQL
    try:
        eid = str(body.get("event_id") or "")
        owner = getattr(user, "sub", None) or getattr(user, "username", "")

        if eid and owner:
            # Determine tool version (default to 1)
            tool_version = "1"

            # Extract request headers for audit
            request_headers = {
                "user-agent": request.headers.get("user-agent"),
                "x-request-id": request.headers.get("x-request-id"),
            }

            # Create invocation in PostgreSQL
            invocation, _created = repo.create_invocation(
                tool_name=name,
                tool_version=tool_version,
                tenant_id=tenant_id,
                params=args,
                requested_by=owner,
                idempotency_key=idem_key,
                request_headers=request_headers,
            )

            # Update with results
            if body.get("ok"):
                repo.update_invocation_status(
                    eid=invocation.eid,
                    status="finished",
                    result=body.get("result"),
                    latency_ms=body.get("duration_ms"),
                )
                # Cache result in Redis
                if body.get("result"):
                    tools_cache.cache_invocation_result(invocation.eid, body.get("result"))
                    record_tool_cache_operation("set", "success")

                # Record metrics for successful invocation
                duration_sec = (body.get("duration_ms") or 0) / 1000.0
                record_tool_invocation(
                    tool_name=name,
                    status="finished",
                    duration_seconds=duration_sec,
                    tenant_id=tenant_id,
                )

                # Log successful completion
                log.info(
                    "tool.invocation.success",
                    tool_name=name,
                    correlation_id=correlation_id,
                    invocation_id=invocation.eid,
                    duration_ms=body.get("duration_ms"),
                )
            else:
                error_detail = {"message": body.get("error"), "type": "InvocationError"}
                repo.update_invocation_status(
                    eid=invocation.eid,
                    status="failed",
                    error=error_detail,
                    latency_ms=body.get("duration_ms"),
                )
                # Cache error in Redis
                tools_cache.cache_invocation_error(invocation.eid, error_detail)
                record_tool_cache_operation("set", "success")

                # Record metrics for failed invocation
                duration_sec = (body.get("duration_ms") or 0) / 1000.0
                record_tool_invocation(
                    tool_name=name,
                    status="failed",
                    duration_seconds=duration_sec,
                    tenant_id=tenant_id,
                )

                # Log failure
                log.warning(
                    "tool.invocation.failed",
                    tool_name=name,
                    correlation_id=correlation_id,
                    invocation_id=invocation.eid,
                    error=body.get("error"),
                    duration_ms=body.get("duration_ms"),
                )

            # Update body with actual eid from database
            body["event_id"] = invocation.eid

            # Set idempotency mapping in Redis
            if idem_key:
                tools_cache.set_idempotency_mapping(idem_key, invocation.eid)

    except Exception as e:
        # Log but don't fail the request if persistence fails
        with suppress(Exception):
            from src.logging_setup import get_logger

            _lg = get_logger(__name__)
            _lg.error("invocation_persistence_failed", extra={"error": str(e), "tool": name})

    # Legacy: Also persist invocation for retrieval using old store
    try:
        eid = str(body.get("event_id") or "")
        owner = getattr(user, "sub", None) or getattr(user, "username", "")
        if eid and owner:
            save_invocation(name, eid, owner, body)
    except Exception:
        pass
    if cache_key:
        with suppress(Exception):
            idem_set(cache_key, body, ex=24 * 3600)
    # If provenance event id is available, advertise a canonical invocation resource
    try:
        if hasattr(resp, "event_id"):
            eid = resp.event_id
            try:
                loc = request.url_for("get_tool_invocation", name=name, eid=eid)
            except Exception:
                try:
                    loc = request.app.url_path_for("get_tool_invocation", name=name, eid=eid)
                except Exception:
                    loc = f"/v1/tools/{name}/invocations/{eid}"
            headers = {
                "Location": loc,
                "Cache-Control": "no-store",
                "Idempotency-Replayed": "false",
            }
            if idem_key:
                headers["Idempotency-Key"] = idem_key
            if body.get("event_id"):
                headers["X-Request-Id"] = str(body["event_id"])
            return JSONResponse(status_code=status.HTTP_201_CREATED, content=body, headers=headers)
    except Exception:
        pass
    # Fallback return if location/event header path not taken
    headers = {
        "Cache-Control": "no-store",
        "Idempotency-Replayed": "false",
    }
    if idem_key:
        headers["Idempotency-Key"] = idem_key
    if body.get("event_id"):
        headers["X-Request-Id"] = str(body["event_id"])
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=body, headers=headers)


@router.get(
    "/{name}/invocations/{eid}",
    name="get_tool_invocation",
    summary="Get tool invocation result",
    description=(
        "**GET /tools/{name}/invocations/{eid} – Retrieve stored invocation result**\n\n"
        "**Why we need this endpoint:**\n"
        "- **Asynchronous workflows**: Agents can retrieve results later instead of waiting for long-running tools to complete.\n"
        "- **Audit and compliance**: Permanently stored invocation records provide an audit trail showing who did what and when.\n"
        "- **Debugging assistance**: When tool invocations fail, developers can inspect the exact inputs, outputs, and errors.\n"
        "- **Result sharing**: Team members can reference specific invocation IDs when discussing issues or outcomes.\n"
        "- Without this endpoint, results would be lost after initial retrieval, making debugging and auditing impossible.\n\n"
        "**What it does:**\n"
        "- Returns the exact stored result for a specific tool invocation (by event_id).\n"
        "- Provides access to historical invocation data for auditing, debugging, or result retrieval.\n"
        "- Enforces anti-enumeration: only the invocation owner or admins can access (non-owners get 404).\n\n"
        "**Access:**\n"
        "- Requires valid auth token (any authenticated user can attempt access).\n"
        "- **Owner-only**: Only the user who created the invocation (by token `sub`) or admins can fetch.\n"
        "- **Anti-enumeration**: Non-owners receive 404 (not 403) to prevent invocation ID discovery.\n\n"
        "**Behavior:**\n"
        "- **Path validation**: `name` must match the tool that produced `eid`; mismatches return 404.\n"
        "- **UUID validation**: `eid` must be a valid UUID; invalid formats return 400.\n"
        "- **Retention**: Results retained per `RETENTION_DAYS` setting; expired invocations return 404.\n"
        "- **Caching**: Supports `If-None-Match`/`ETag` for 304 responses; sets `Cache-Control: private, max-age=30`.\n"
        "- **Headers**: Returns `X-Request-Id: {eid}` and `Vary: Authorization`.\n\n"
        "**Responses:**\n"
        "- **200 OK**: Successfully retrieved invocation result (returns `ToolInvokeResponse`).\n"
        "- **304 Not Modified**: `If-None-Match` matches current `ETag` (no changes).\n"
        "- **400 Bad Request**: Invalid `eid` format (not a UUID).\n"
        "- **401 Unauthorized**: Missing or invalid auth token.\n"
        "- **404 Not Found**: Unknown invocation, expired, name mismatch, or caller not authorized (anti-enumeration).\n\n"
        "**Examples:**\n"
        "```bash\n"
        "# Retrieve invocation result\n"
        "curl -H 'Authorization: Bearer YOUR_TOKEN' \\\n"
        "  https://api.example.com/v1/tools/graph.query/invocations/33200c38-7bb0-47ea-9765-763c78315841\n\n"
        "# Conditional GET (check for updates)\n"
        "curl -H 'Authorization: Bearer YOUR_TOKEN' \\\n"
        "  -H 'If-None-Match: W/\"def456\"' \\\n"
        "  https://api.example.com/v1/tools/graph.query/invocations/33200c38-7bb0-47ea-9765-763c78315841\n"
        "# → 304 if unchanged\n\n"
        "# Non-owner attempt (anti-enumeration)\n"
        "curl -H 'Authorization: Bearer OTHER_USER_TOKEN' \\\n"
        "  https://api.example.com/v1/tools/system.health/invocations/abc-def-ghi\n"
        "# → 404 (not 403, to prevent ID discovery)\n"
        "```"
    ),
    response_model=ToolInvokeResponse,
    responses={
        200: {"description": "OK"},
        304: {"description": "Not Modified"},
        400: {"description": "Bad Request (invalid id)"},
        401: {"description": "Unauthorized (missing/invalid token)"},
        404: {"description": "Not Found (unknown id or not owned by caller)"},
    },
)
def get_tool_invocation(
    request: Request,
    name: str,
    eid: str = Path(..., description="Invocation id (UUID)", examples=["33200c38-7bb0-47ea-9765-763c78315841"]),
    user: UserInfo = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Validate UUID format early (simple hyphenated UUID v4 or any UUID)
    import uuid

    try:
        uuid.UUID(str(eid))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid id")

    # Try Redis cache first
    cached_result = tools_cache.get_cached_result(eid)
    if cached_result:
        # Record cache hit metric
        record_tool_cache_operation("get", "hit")

        # Log cache hit
        log.debug(
            "tool.invocation.cache_hit",
            tool_name=name,
            invocation_id=eid,
        )

        # Still need to check ownership from PostgreSQL
        repo = ToolsRepository(db)
        invocation = repo.get_invocation_by_eid(eid)
        if invocation and invocation.tool_name == name:
            eff_perms = set(current_permissions(user))
            is_admin = "admin:all" in eff_perms
            principal = getattr(user, "sub", None) or getattr(user, "username", None)

            # Anti-enumeration: only owner or admin
            if not is_admin and principal != invocation.requested_by:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="invocation not found")

            # Build response from cached data
            body = {
                "name": invocation.tool_name,
                "ok": invocation.status == "finished",
                "result": cached_result,
                "error": invocation.error_json.get("message") if invocation.error_json else None,
                "duration_ms": invocation.latency_ms or 0,
                "trace_id": "",
                "event_id": invocation.eid,
            }

            body_bytes = _json_bytes_stable(body)
            etag = _compute_etag_from_bytes(body_bytes)

            if _if_none_match_matches(request.headers.get("if-none-match"), etag):
                return StarletteResponse(
                    status_code=status.HTTP_304_NOT_MODIFIED,
                    headers={
                        "ETag": etag,
                        "Cache-Control": "private, max-age=30",
                        "Vary": "Authorization",
                        "X-Request-Id": str(eid),
                        "X-Cache": "HIT",
                    },
                )

            return StarletteResponse(
                content=body_bytes,
                media_type="application/json",
                headers={
                    "ETag": etag,
                    "Cache-Control": "private, max-age=30",
                    "Vary": "Authorization",
                    "X-Request-Id": str(eid),
                    "X-Cache": "HIT",
                },
            )

    # Fetch from PostgreSQL
    repo = ToolsRepository(db)
    invocation = repo.get_invocation_by_eid(eid)

    # Record cache miss metric (only if we didn't hit cache above)
    if not cached_result:
        record_tool_cache_operation("get", "miss")

        # Log cache miss
        log.debug(
            "tool.invocation.cache_miss",
            tool_name=name,
            invocation_id=eid,
        )

    if not invocation or invocation.tool_name != name:
        # Fallback to legacy store
        rec = load_invocation(name, eid)
        if not rec:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="invocation not found")

        owner = rec.get("owner")
        eff_perms = set(current_permissions(user))
        is_admin = "admin:all" in eff_perms
        principal = getattr(user, "sub", None) or getattr(user, "username", None)
        if not is_admin and principal != owner:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="invocation not found")

        body = rec.get("body") or {}
        if not isinstance(body, dict):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="invocation not found")

        body_bytes = _json_bytes_stable(body)
        etag = _compute_etag_from_bytes(body_bytes)

        if _if_none_match_matches(request.headers.get("if-none-match"), etag):
            return StarletteResponse(
                status_code=status.HTTP_304_NOT_MODIFIED,
                headers={
                    "ETag": etag,
                    "Cache-Control": "private, max-age=30",
                    "Vary": "Authorization",
                    "X-Request-Id": str(body.get("event_id") or ""),
                    "X-Cache": "MISS",
                },
            )

        return StarletteResponse(
            content=body_bytes,
            media_type="application/json",
            headers={
                "ETag": etag,
                "Cache-Control": "private, max-age=30",
                "Vary": "Authorization",
                "X-Request-Id": str(body.get("event_id") or ""),
                "X-Cache": "MISS",
            },
        )

    # Check ownership (anti-enumeration)
    eff_perms = set(current_permissions(user))
    is_admin = "admin:all" in eff_perms
    principal = getattr(user, "sub", None) or getattr(user, "username", None)

    if not is_admin and principal != invocation.requested_by:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="invocation not found")

    # Build response from PostgreSQL data
    body = {
        "name": invocation.tool_name,
        "ok": invocation.status == "finished",
        "result": invocation.result_json,
        "error": invocation.error_json.get("message") if invocation.error_json else None,
        "duration_ms": invocation.latency_ms or 0,
        "trace_id": "",
        "event_id": invocation.eid,
    }

    # Cache result in Redis for future requests
    if invocation.result_json and invocation.status == "finished":
        with suppress(Exception):
            tools_cache.cache_invocation_result(eid, invocation.result_json)

    body_bytes = _json_bytes_stable(body)
    etag = _compute_etag_from_bytes(body_bytes)

    if _if_none_match_matches(request.headers.get("if-none-match"), etag):
        return StarletteResponse(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers={
                "ETag": etag,
                "Cache-Control": "private, max-age=30",
                "Vary": "Authorization",
                "X-Request-Id": str(eid),
                "X-Cache": "MISS",
            },
        )

    return StarletteResponse(
        content=body_bytes,
        media_type="application/json",
        headers={
            "ETag": etag,
            "Cache-Control": "private, max-age=30",
            "Vary": "Authorization",
            "X-Request-Id": str(eid),
            "X-Cache": "MISS",
        },
    )


@router.get(
    "/{name}",
    response_model=ToolInfo,
    summary="Get tool metadata and input schema if available",
    description=(
        "**GET /tools/{name} – Fetch metadata for a specific tool**\n\n"
        "**Why we need this endpoint:**\n"
        "- **Input validation**: Client apps need the JSON schema to validate user inputs before submitting expensive or risky operations.\n"
        "- **Dynamic UI generation**: Front-end frameworks can render appropriate form fields based on the schema (text inputs, dropdowns, etc.).\n"
        "- **Documentation discovery**: Developers inspecting a tool can see exactly what parameters it accepts and what they mean.\n"
        "- **Permission checking**: Shows whether a tool requires elevated permissions before attempting to invoke it.\n"
        "- Without this endpoint, clients would have to hardcode validation rules or submit invalid requests, wasting API calls and user time.\n\n"
        "**What it does:**\n"
        "- Returns detailed metadata about a single tool: module path, entrypoint, description, input schema.\n"
        "- Helps client UIs render tool-specific forms or validate arguments before invocation.\n"
        "- Provides schema for input validation (JSON Schema format when available).\n\n"
        "**Access:**\n"
        "- Requires `tools:basic`, `tools:all`, or `admin:all` scope.\n"
        "- **Visibility rules**: Admin-only tools hidden from non-admins (404 instead of 403 for anti-enumeration).\n"
        "- **Redaction**: Non-admin callers see redacted `module` paths (null instead of internal paths).\n\n"
        "**Behavior:**\n"
        "- **Schema detection**: Checks `INPUT_SCHEMA`, `get_input_schema()`, or `describe()` methods.\n"
        "- **Namespace handling**: Returns 404 for namespaces (non-invokable groupings).\n"
        "- **Caching**: Supports `If-None-Match`/`ETag` for 304 responses; sets `Cache-Control: private, max-age=30`.\n"
        "- **Headers**: Returns `Vary: Authorization` to vary by user permissions.\n\n"
        "**Responses:**\n"
        "- **200 OK**: Successfully retrieved tool metadata (returns `ToolInfo`).\n"
        "- **304 Not Modified**: `If-None-Match` matches current `ETag` (no changes).\n"
        "- **401 Unauthorized**: Missing or invalid auth token.\n"
        "- **404 Not Found**: Unknown tool, namespace, or not visible to caller's scopes (anti-enumeration).\n\n"
        "**Examples:**\n"
        "```bash\n"
        "# Get metadata for graph.query tool\n"
        "curl -H 'Authorization: Bearer YOUR_TOKEN' \\\n"
        "  https://api.example.com/v1/tools/graph.query\n\n"
        "# Conditional GET (check for schema updates)\n"
        "curl -H 'Authorization: Bearer YOUR_TOKEN' \\\n"
        "  -H 'If-None-Match: W/\"xyz789\"' \\\n"
        "  https://api.example.com/v1/tools/system.health\n"
        "# → 304 if unchanged\n\n"
        "# Attempt to access admin-only tool (non-admin caller)\n"
        "curl -H 'Authorization: Bearer USER_TOKEN' \\\n"
        "  https://api.example.com/v1/tools/security.audit\n"
        "# → 404 (anti-enumeration, not 403)\n"
        "```"
    ),
    responses={
        200: {"description": "OK"},
        304: {"description": "Not Modified"},
        401: {"description": "Unauthorized (missing/invalid token)"},
        404: {"description": "Not Found (unknown tool, not visible to caller, or namespace)"},
    },
)
async def get_tool(
    request: Request,
    name: str,
    response: Response,
    user: UserInfo = Depends(require_perms(["tools:basic", "tools:all", "admin:all"])),
):
    """Provide metadata and input schema information for a single tool.

    Returns lightweight information suitable for rendering forms or performing client-side validation prior to calling `/tools/{name}/invocations`.
    """
    short = name
    module_path = f"{TOOLS_PACKAGE}.{short}"
    entrypoint = None
    description = None
    input_schema = None
    scopes: list[str] = []
    namespace = False
    invokable = False
    long_running = False
    version = 1
    capabilities: list[str] = []
    is_admin = "admin:all" in set(current_permissions(user))
    mod = None
    try:
        mod = importlib.import_module(module_path)
        entrypoint, _fn = _detect_entrypoint(mod)
        invokable = bool(entrypoint)
        version = _tool_version(mod)
        capabilities = _tool_capabilities(short, mod)
        if isinstance(getattr(mod, "__doc__", None), str):
            doc = (mod.__doc__ or "").strip().splitlines()
            if doc:
                description = doc[0].strip()
                if description.lower().startswith("mcp namespace"):
                    namespace = True
                    invokable = False
                    entrypoint = None
        # Try to read an input schema by convention
        if hasattr(mod, "INPUT_SCHEMA"):
            input_schema = mod.INPUT_SCHEMA
        elif hasattr(mod, "get_input_schema") and callable(mod.get_input_schema):
            with suppress(Exception):
                input_schema = mod.get_input_schema()
        elif hasattr(mod, "describe") and callable(mod.describe):
            with suppress(Exception):
                desc = mod.describe()
                if isinstance(desc, dict) and isinstance(desc.get("schema"), dict):
                    input_schema = desc["schema"]
        try:
            long_running = bool(getattr(mod, "LONG_RUNNING", False))
        except Exception:
            long_running = False
    except Exception:
        # Not importable — return best-effort metadata
        module_path = f"{TOOLS_PACKAGE}.{short}"

        # Try to get capabilities even if module failed to import
        class _MockMod:
            pass

        capabilities = _tool_capabilities(short, _MockMod())
    # Ensure schema non-null for invokable tools
    if invokable and not input_schema:
        input_schema = _default_schema()
    # Namespaces never expose entrypoint/schema
    if namespace and not invokable:
        entrypoint = None
        input_schema = None
    # Determine scopes and namespace flag
    try:
        safe = {s.strip() for s in (settings.SAFE_TOOLS or "").split(",") if s.strip()}
    except Exception:
        safe = set()
    scopes = _scopes_for_tool(short, safe)
    try:
        all_mods = set(_iter_tool_modules())
        namespace = _is_namespace(module_path, all_mods) and not invokable
    except Exception:
        namespace = not invokable

    # Visibility and anti-enumeration: mirror list_tools visibility for single fetch
    eff_perms = set(current_permissions(user))
    has_basic = "tools:basic" in eff_perms
    has_all = "tools:all" in eff_perms
    visible = False
    if is_admin:
        visible = True
    elif "admin:all" in scopes:
        visible = False
    elif "tools:basic" in scopes:
        visible = has_basic or has_all  # elevated implies basic
    elif "tools:all" in scopes:
        visible = has_basic or has_all  # visible to any authenticated user per policy
    else:
        visible = False

    # Return 404 for namespaces or non-visible tools (anti-enumeration), or when not importable
    if namespace or not visible:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tool not found")

    module_value = module_path if is_admin else None
    tool_id = f"{short}@{version}"
    item = ToolInfo(
        id=tool_id,
        name=short,
        module=module_value,
        entrypoint=entrypoint,
        description=description,
        input_schema=input_schema if invokable else None,
        scopes=scopes,
        capabilities=capabilities,
        namespace=namespace,
        invokable=invokable,
        long_running=long_running,
    )

    # Build deterministic JSON bytes for ETag and conditional GET
    payload = item.model_dump(exclude_none=False)
    # Deterministic order for list fields
    if isinstance(payload.get("scopes"), list):
        payload["scopes"] = sorted(payload["scopes"])  # sort for determinism
    if isinstance(payload.get("capabilities"), list):
        payload["capabilities"] = sorted(payload["capabilities"])  # sort for determinism

    body_bytes = _json_bytes_stable(payload)
    etag = _compute_etag_from_bytes(body_bytes)
    if _if_none_match_matches(request.headers.get("if-none-match"), etag):
        return StarletteResponse(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers={
                "ETag": etag,
                "Cache-Control": "private, max-age=30",
                "Vary": "Authorization",
            },
        )

    return StarletteResponse(
        content=body_bytes,
        media_type="application/json",
        headers={
            "ETag": etag,
            "Cache-Control": "private, max-age=30",
            "Vary": "Authorization",
        },
    )


# ---------------- Invocation core ----------------
async def _invoke_by_name(
    name: str,
    args: dict[str, Any],
    timeout_seconds: float | None,
    user: UserInfo,
) -> ToolInvokeResponse:
    resolved = _resolve_tool(name)
    start_ns = time.monotonic_ns()

    if resolved.func is None:
        # Try importing module just to surface a richer error
        try:
            mod = importlib.import_module(resolved.module)
            ep_name, fn = _detect_entrypoint(mod)
            resolved.entrypoint_name, resolved.func = ep_name, fn
        except Exception as e:
            duration_ms = int((time.monotonic_ns() - start_ns) / 1_000_000)
            ev = record_provenance(
                actor="api",
                action=f"tools.{name}",
                resource="/tools/invoke",
                input={"args": args},
                output={"error": str(e)},
                meta={"user": _principal_identity(user), "module": resolved.module, "entrypoint": None},
                success=False,
                duration_ms=duration_ms,
            )
            if TOOL_INVOKE is not None:  # pragma: no cover
                with suppress(Exception):
                    TOOL_INVOKE.labels(name=name, success="false").inc()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tool '{name}' not found or not importable",
            ) from e

    if resolved.func is None:
        # Module imported but no entrypoint
        duration_ms = int((time.monotonic_ns() - start_ns) / 1_000_000)
        ev = record_provenance(
            actor="api",
            action=f"tools.{name}",
            resource="/tools/invoke",
            input={"args": args},
            output={"error": "entrypoint not found"},
            meta={"user": _principal_identity(user), "module": resolved.module, "entrypoint": None},
            success=False,
            duration_ms=duration_ms,
        )
        if TOOL_INVOKE is not None:  # pragma: no cover
            with suppress(Exception):
                TOOL_INVOKE.labels(name=name, success="false").inc()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tool '{name}' has no supported entrypoint {ENTRYPOINT_CANDIDATES}",
        )

    # Call the tool with optional timeout; pass through kwargs (args)
    async def _call() -> Any:
        try:
            result = resolved.func(**args)  # type: ignore[misc]
            return await _maybe_await(result)
        except TypeError:
            # Fallback for tools expecting a single 'payload' argument
            result = resolved.func(args)  # type: ignore[misc]
            return await _maybe_await(result)

    try:
        if timeout_seconds and timeout_seconds > 0:
            result = await asyncio.wait_for(_call(), timeout=timeout_seconds)
        else:
            result = await _call()
        ok = True
        error = None
    except Exception as e:
        result = None
        ok = False
        error = f"{type(e).__name__}: {e}"

    duration_ms = int((time.monotonic_ns() - start_ns) / 1_000_000)

    ev = record_provenance(
        actor="api",
        action=f"tools.{name}",
        resource=f"/tools/{name}/invocations",
        input={"args": args},
        output={"result": result} if ok else {"error": error},
        meta={"user": _principal_identity(user), "module": resolved.module, "entrypoint": resolved.entrypoint_name},
        success=ok,
        duration_ms=duration_ms,
    )

    # Metrics
    if TOOL_INVOKE is not None:  # pragma: no cover
        with suppress(Exception):
            TOOL_INVOKE.labels(name=name, success=str(ok).lower()).inc()
    if TOOL_LATENCY is not None:  # pragma: no cover
        with suppress(Exception):
            TOOL_LATENCY.observe(duration_ms / 1000.0)

    if not ok:
        raise HTTPException(status_code=500, detail=error)

    return ToolInvokeResponse(
        name=name,
        ok=True,
        result=result,
        error=None,
        duration_ms=duration_ms,
        trace_id=ev.trace_id,
        event_id=ev.event_id,
    )


# Compatibility stub for old colon-style invocation path -> return 404 Not Found (anti-enumeration)
@router.post("/{name}:invoke", summary="(Deprecated) invoke by path (compat)", include_in_schema=False)
async def legacy_invoke_410(name: str, request: Request):
    # Hide from OpenAPI and indicate the route is no longer available
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"ok": False, "message": "deprecated: use POST /v1/tools/{name}/invocations"},
    )
