"""
Model management endpoints (admin-oriented).

Mounted under /model by the application.

Endpoints:
- GET    /model                 -> list models (and indicate default if known)
- GET    /model/default         -> get current default model name
- POST   /model/default         -> set default model (admin)
- POST   /model/load            -> load/prepare a model (admin)
- POST   /model/unload          -> unload/free a model (admin)
- POST   /model/test            -> run a short test prompt against a model
- GET    /model/builtins        -> list built-in models
- POST   /model/builtins/stage  -> stage remote builtins manifest (fetch only)
- POST   /model/builtins/activate-> activate staged builtins manifest
- POST   /model/builtins/rollback-> rollback builtins manifest to previous
- GET    /model/builtins/staged -> get staged manifest if any

The router imports `src.adapters.llm` lazily and degrades gracefully if the
adapter is not implemented yet, returning demo outputs so the API remains usable.

Note: built-in model endpoints are implemented below and delegate to src.services.llm_registry
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import suppress
from types import SimpleNamespace
from typing import Any
from urllib.parse import urljoin, urlparse

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.schemas.auth import UserInfo
from src.schemas.models import (
    ActionResponse,
    InstanceCreateRequest,
    ModelInfo,
    PatchDefaultsBody,
    TestRequest,
    TestResponse,
    UnregisterLLMRequest,
    Usage,
)
from src.schemas.providers import (
    AuthConfig,
    Paths,
    ProviderConfig,
    RequestTemplates,
    ResponseExtract,
    TLSConfig,
    Timeouts,
)
from src.config import settings
from src.provenance import record_provenance
from src.routers.auth import get_current_user
from src.routers.models import _build_upstream_headers, problem_response
from src.security.perm import require_perms
from src.utils import test_helpers
from src.utils.pagination import make_page
from src.utils.provider_resolver import (
    DEFAULT_HTTPX_TIMEOUT,
    debug_log_provider_call,
    is_ollama_provider,
    resolve_provider_base_url,
    resolve_upstream_model_id,
    timeout_for_provider,
)


def require_tenant_header(request: Request) -> str:
    # Tenant header is optional; default to 'global' when missing (admin-only endpoints may require explicit tenant)
    tid = request.headers.get("X-Tenant-Id")
    return tid or "global"


# Router without default tags - we'll apply tags per endpoint group
router = APIRouter()

logger = logging.getLogger(__name__)


PROVIDER_TYPES = {"openai_compatible", "custom"}


def _validate_provider_payload(
    provider_type: str, base_url: str | None, config: dict[str, Any] | None
) -> ProviderConfig:
    if provider_type not in PROVIDER_TYPES:
        raise ValueError("invalid provider type; must be one of: openai_compatible, custom")
    cfg = ProviderConfig(**(config or {}))
    effective_base = base_url or cfg.base_url
    if provider_type in {"openai_compatible", "custom"} and not effective_base:
        raise ValueError("base_url required for non-local providers")
    return cfg


def _egress_allowed(url: str | None) -> bool:
    if not url:
        return True
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if not host:
        return False
    allow = settings.EGRESS_ALLOWLIST
    if not allow:
        return True
    allow_items: list[str] = []
    for raw in allow.split(","):
        item = raw.strip()
        if not item:
            continue
        if item.startswith("http://") or item.startswith("https://"):
            item = urlparse(item).netloc
        if item:
            allow_items.append(item.lower())
    allow_items.extend(["localhost", "127.0.0.1", "::1"])
    host = host.rstrip("/")
    for entry in allow_items:
        entry = entry.rstrip("/")
        if not entry:
            continue
        if host == entry:
            return True
        if host.startswith(entry):
            return True
        if host.endswith(entry):
            return True
    return False


# Repository-backed persistence (PostgreSQL authoritative + Redis cache). Legacy _INSTANCES retained for backward compatibility with existing code paths.
import src.repositories.models_repo as _repo  # Legacy Redis-only repo for instances
from db.postgres_control.repositories import (
    model_instance_repo as pg_instance_repo,  # PostgreSQL-backed instances
    provider_repo as pg_repo,  # PostgreSQL-backed providers
)

_INSTANCES: dict[str, dict[str, Any]] = {}


# NOTE: ModelInfo, TestRequest, TestResponse, Usage, ActionResponse, etc. now imported from schemas.models
# (Legacy definitions removed - see schemas/models.py for canonical versions)


# ---------------- Utilities ----------------
def _adapter():
    with suppress(Exception):
        import importlib

        return importlib.import_module("src.adapters.llm")
    return None


def _principal_name(user_like: Any) -> str:
    """Best-effort extraction of a principal name for provenance/logging.

    Supports either the legacy UserInfo (with .username) or the OIDC Principal (with .sub) or raw dict.
    """
    for attr in ("username", "sub", "name", "email"):
        with suppress(Exception):
            v = getattr(user_like, attr, None)
            if v:
                return str(v)
        if isinstance(user_like, dict):
            v = user_like.get(attr)
            if v:
                return str(v)
    # Final fallback: raw claim
    with suppress(Exception):
        raw = getattr(user_like, "raw", {}) or {}
        sub = raw.get("sub")
        if sub:
            return str(sub)
    return "unknown"


def _fallback_models() -> list[ModelInfo]:  # retained for compatibility; returns empty in registry-only mode
    return []


def _require_admin(user: UserInfo) -> None:
    # Normalize permissions from available attributes
    raw_scopes = set(user.scopes or [])
    raw_perms = set(getattr(user, "permissions", []) or [])
    union = {s.lower() for s in (raw_scopes | raw_perms)}
    accepted = {"admin:all", "admin:*", "models:write", "models:admin"}
    if union.intersection(accepted):
        return
    # legacy fallback: plain "admin" scope
    if "admin" in union:
        return
    logger.warning("auth.admin.denied", extra={"seen": sorted(union)})
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin scope required")


# ---------------- Routes ----------------
# NOTE: /instances endpoints have been moved to model_instances.py router
# The following endpoints are commented out to prevent route conflicts:
# - GET /instances
# - POST /instances
# - GET /instances/{id}
# - DELETE /instances/{id}
# See src/routers/model_instances.py for the new PostgreSQL-backed implementation


# @router.get("/instances", response_model=List[ModelInfo], tags=["models-instances"], summary="List model instances (registry-only)", description="""
# Return only model instances that were explicitly registered via POST /admin/models/instances.
#
# No filesystem auto-discovery, no implicit demo insertion. Empty array means nothing is registered yet.
# Authentication required (non-admin callers allowed for read). Response shape: ModelInfo[].
# """)
async def _DISABLED_list_instances(
    user: UserInfo = Depends(get_current_user), request: Request = None
) -> list[ModelInfo]:
    """Registry-only listing of model instances.

    Ignores any legacy query parameters (e.g., include_discovered). If such a parameter is present
    we silently ignore it (could be changed to 400 if stricter behavior desired).
    """
    corr = str(uuid.uuid4())
    uname = _principal_name(user)
    logger.info(
        "model.instances.list.start", extra={"correlation_id": corr, "user": uname, "marker": "entered_list_instances"}
    )
    # Pull registry models from repository (Redis-backed) and refresh legacy mirror
    registry_models: list[ModelInfo] = []
    tenant_filter: str | None = None
    if request:
        try:
            tenant_filter = request.headers.get("X-Tenant-Id") or None
        except Exception:
            tenant_filter = None
        if tenant_filter == "global":
            tenant_filter = None

    try:
        repo_instances = _repo.list_instances()
    except Exception as exc:
        logger.warning("model.instances.repo.list.failed", extra={"error": str(exc)})
        repo_instances = []
    _INSTANCES.clear()
    for inst in repo_instances:
        # Normalize provider field for response: prefer stored 'provider', fallback to 'provider_id'
        if not inst.get("provider") and inst.get("provider_id"):
            inst = {**inst, "provider": inst.get("provider_id")}
        _INSTANCES[inst["id"]] = inst
        if tenant_filter and inst.get("tenant_id") not in (None, tenant_filter):
            continue
        data = {k: v for k, v in inst.items() if k in ModelInfo.model_fields}
        try:
            registry_models.append(ModelInfo(**data))
        except Exception:
            continue
    models = list(registry_models)
    # Enforce single default (first occurrence if multiple flagged due to manual tampering)
    # Normalize defaults: ensure at most one model has default=True (registry-only, avoid index errors)
    try:
        defaults = [m for m in models if getattr(m, "default", False)]
        if len(defaults) > 1:
            # Pick the lexicographically smallest name deterministically to avoid non-determinism
            try:
                keep_name = sorted([d.name for d in defaults if d.name])[:1]
                keep = keep_name[0] if keep_name else None
            except Exception:
                keep = None
            for m in models:
                m.default = keep is not None and m.name == keep
    except Exception as e:
        logger.error("model.instances.normalize_default.failed", extra={"error": str(e), "correlation_id": corr})
    record_provenance(
        actor="api",
        action="model.list",
        resource="/model",
        input={},
        output={"models": [m.model_dump() for m in models]},
        meta={"user": uname, "source": "registry", "correlation_id": corr},
    )
    logger.info(
        "model.instances.list.end",
        extra={"correlation_id": corr, "count": len(models), "defaults": [m.name for m in models if m.default]},
    )
    return models


_DEFAULTS: dict[str, str | None] = {"chat": None}  # legacy shadow


async def _resolve_default_record(tenant_id: str | None = None) -> dict[str, Any] | None:
    try:
        defs = _repo.get_default("chat", tenant_id=tenant_id) or _repo.get_defaults().get("chat")
    except Exception:
        defs = None
    if isinstance(defs, dict):
        iid = defs.get("instance_id")
        if iid:
            return _repo.get_instance(iid)
    return None


# @router.get("/defaults", response_model=Dict[str, Any], tags=["models-instances"], summary="Get default model selection", description="""Return the current default model (registry only).""")
async def _DISABLED_get_defaults(
    user: UserInfo = Depends(get_current_user), tenant_id: str = Depends(require_tenant_header)
) -> dict[str, Any]:
    """DISABLED: Use /v1/admin/models/defaults GET endpoint in model_instances.py instead."""
    rec = await _resolve_default_record(tenant_id=tenant_id if tenant_id != "global" else None)
    name = rec.get("name") if rec else None
    out: dict[str, Any] = {"name": name, "chat": None}
    if rec:
        out["chat"] = {
            "instance_id": rec.get("id"),
            "name": rec.get("name"),
            "tenant_id": None if tenant_id == "global" else tenant_id,
        }
    record_provenance(
        actor="api",
        action="model.default.get",
        resource="/model/default",
        input={},
        output=out,
        meta={"user": _principal_name(user)},
    )
    return out


# NOTE: PatchDefaultsBody imported from schemas.models


# @router.patch("/defaults", response_model=ActionResponse, tags=["models-instances"], summary="Patch default model selection (admin)", description="""Set the registry default model. Accepts legacy {name} or {chat:{name|instance_id}}.""")
async def _DISABLED_patch_defaults(
    body: PatchDefaultsBody,
    user: UserInfo = Depends(require_perms(["admin:all"])),
    tenant_id: str = Depends(require_tenant_header),
) -> ActionResponse:
    """DISABLED: Use /v1/admin/models/defaults PATCH endpoint in model_instances.py instead."""
    _require_admin(user)
    target_name: str | None = None
    target_id: str | None = None
    if body.chat:
        target_name = body.chat.get("name")
        target_id = body.chat.get("instance_id")
    if body.name and not (target_name or target_id):
        target_name = body.name
    inst: dict[str, Any] | None = None
    if target_id:
        inst = _repo.get_instance(target_id)
    if not inst and target_name:
        for v in _repo.list_instances():
            if v.get("name") == target_name:
                inst = v
                break
    if not inst:
        msg = "Instance not found"
        record_provenance(
            actor="api",
            action="model.default.set",
            resource="/model/default",
            input=body.model_dump(),
            output={"error": msg},
            meta={"user": _principal_name(user)},
            success=False,
        )
        raise HTTPException(status_code=404, detail=msg)
    try:
        _repo.set_default("chat", inst.get("id"), tenant_id=None if tenant_id == "global" else tenant_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    ev = record_provenance(
        actor="api",
        action="model.default.set",
        resource="/model/default",
        input=body.model_dump(),
        output={"ok": True, "chat": inst.get("id")},
        meta={"user": _principal_name(user)},
        success=True,
    )
    return ActionResponse(
        ok=True,
        message=f"default set to {inst.get('name')}",
        details={"chat": inst.get("id")},
        trace_id=ev.trace_id,
        event_id=ev.event_id,
    )


# @router.post("/instances", response_model=Dict[str, Any], status_code=201, tags=["models-instances"], summary="Load/prepare a model instance (admin)", description="""
# Load or prepare a model instance on the platform runtime.
#
# Admin-only operation that asks the runtime adapter to load or stage a model instance so it
# is available for low-latency use. The request accepts `modelKey` (or `name`) and optional
# adapter-specific `options`. The endpoint returns a small object containing an `id` that can
# be used to reference the instance in subsequent admin calls. On systems without a runtime
# adapter this endpoint returns a demo/compatibility response and does not change runtime
# behavior.
# """)
async def _DISABLED_create_instance(
    req: InstanceCreateRequest, user: UserInfo = Depends(require_perms(["admin:all"]))
) -> dict[str, Any]:
    """Create (register + load) a model instance via provider.

    Supports providing a local `model_uri` (container-absolute path) or a logical `model_id`.
    Persists instance metadata in the in-memory registry. No automatic filesystem discovery.
    """
    _require_admin(user)
    # Normalize legacy name
    if not req.instance_name and req.name:
        req.instance_name = req.name  # type: ignore
    if not req.instance_name:
        raise HTTPException(status_code=400, detail="instance_name required")
    inst_id = req.instance_name
    if _repo.get_instance(inst_id):
        raise HTTPException(status_code=409, detail="instance already exists")
    # provider must exist
    if not _repo.get_provider(req.provider_id):
        raise HTTPException(status_code=404, detail="provider not found")
    if req.model_uri:
        if not os.path.isabs(req.model_uri):
            raise HTTPException(status_code=400, detail="model_uri must be absolute")
        if not os.path.isfile(req.model_uri):
            raise HTTPException(status_code=400, detail="model_uri not found or unreadable")
    load_params = dict(req.parameters)
    if req.model_uri:
        load_params.setdefault("model_uri", req.model_uri)
    if req.model_id:
        load_params.setdefault("model_id", req.model_id)
    # Optional soft validation: check model_id exists at provider (OpenAI-compatible /v1/models)
    if req.model_id:
        try:
            from src.repositories import models_repo

            prov = models_repo.get_provider(req.provider_id)
            base_url = prov and (prov.get("base_url") or (prov.get("config") or {}).get("base_url"))
            if base_url:
                import httpx

                url = base_url.rstrip("/") + "/models"
                # Short timeout, non-blocking failure
                with httpx.Client(timeout=2.0) as http:
                    r = http.get(url)
                    if r.status_code == 200:
                        data = r.json()
                        ids = set()
                        # Accept both OpenAI-compatible {data:[{id}]} and Ollama tags {data:[{id}]}
                        if isinstance(data, dict):
                            items = data.get("data") or []
                            for it in items:
                                mid = (it.get("id") or it.get("name") or "").split(":")[0]
                                if mid:
                                    ids.add(mid)
                        if req.model_id.split(":")[0] not in ids:
                            logger.warning(
                                "model.instances.create.softcheck.missing",
                                extra={"provider": req.provider_id, "model_id": req.model_id},
                            )
        except Exception:
            # Never block on soft-check failures
            pass

    mod = _adapter()
    ok = False
    msg = ""
    details: dict[str, Any] = {}
    if mod and hasattr(mod, "load_model"):
        try:
            res = mod.load_model(inst_id, provider_id=req.provider_id, **load_params)  # type: ignore[attr-defined]
            ok = True
            msg = f"instance '{inst_id}' loaded"
            if isinstance(res, dict):
                details.update(res)
        except Exception as exc:
            msg = f"adapter load failed: {exc}"
    if not ok and (settings.LLM_PROVIDER or "demo") == "demo":
        ok = True
        msg = f"instance '{inst_id}' ready (demo)"
    record_provenance(
        actor="api",
        action="model.load",
        resource="/model/load",
        input=req.model_dump(by_alias=True),
        output={"ok": ok, "message": msg, "details": details},
        meta={"user": _principal_name(user)},
        success=ok,
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    try:
        _repo.create_instance(
            inst_id,
            inst_id,
            req.provider_id,
            model_id=req.model_id or req.instance_name,
            model_uri=req.model_uri,
            parameters=req.parameters,
            loaded=ok,
            enabled=ok,
            tenant_id=req.tenant_id,
            context_window=load_params.get("num_ctx") or 8192,
            modalities=["text"],
            description=details.get("description"),
        )
    except ValueError as ve:
        raise HTTPException(status_code=409, detail=str(ve))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"id": inst_id, "ok": True, "message": msg}


# @router.delete("/instances/{instance_id}", status_code=204, tags=["models-instances"], summary="Unload/free a model instance (admin)", description="""
# Unload or free a previously prepared model instance.
#
# Admin-only operation. Requests to this endpoint ask the runtime adapter to unload resources
# associated with the provided instance id. On success the endpoint returns HTTP 204 No
# Content. If the adapter is unavailable the platform may respond with a demo/no-op success
# message; otherwise a 400 error is returned when unloading is not possible.
# """)
async def _DISABLED_delete_instance(instance_id: str, user: UserInfo = Depends(require_perms(["admin:all"]))):
    """Unload resources associated with a model instance.

    The implementation will attempt to call the adapter's `unload_model` and will also
    remove the instance from the local compatibility store when appropriate.
    """
    _require_admin(user)
    mod = _adapter()
    ok = False
    msg = ""
    details: dict[str, Any] = {}

    if mod and hasattr(mod, "unload_model"):
        with suppress(Exception):
            res = mod.unload_model(instance_id)  # type: ignore[attr-defined]
            ok = True
            msg = f"model '{instance_id}' unloaded"
            if isinstance(res, dict):
                details.update(res)

    if not ok:
        if (settings.LLM_PROVIDER or "demo") == "demo":
            ok = True
            msg = f"model '{instance_id}' unloaded (noop demo)"
        else:
            msg = f"adapter missing; cannot unload '{instance_id}'"

    record_provenance(
        actor="api",
        action="model.unload",
        resource="/model/instances",
        input={"instance_id": instance_id},
        output={"ok": ok, "message": msg, "details": details},
        meta={"user": _principal_name(user)},
        success=ok,
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    # Remove from repository
    with suppress(Exception):
        _repo.delete_instance(instance_id)
    return Response(status_code=204)


def get_instance_by_id(instance_id: str) -> dict[str, Any] | None:
    # Use PostgreSQL repository (authoritative source)
    return pg_instance_repo.get_instance(instance_id)


# @router.get("/instances/{instance_id}", response_model=Dict[str, Any], tags=["models-instances"], summary="Get a model instance (admin)", description="""
# Retrieve details for a specific model instance identified by `instance_id`.
#
# Admin-only read endpoint. Returns the instance record (id, name and any adapter-provided
# `details`) if known. Returns 404 when the instance cannot be found. This endpoint is useful
# for debugging, instrumenting, or confirming the state of a prepared model instance.
# """)
async def _DISABLED_get_instance(
    instance_id: str, user: UserInfo = Depends(require_perms(["admin:all"]))
) -> dict[str, Any]:
    """Return a stored model instance record.

    The returned dict is intentionally permissive to accommodate adapter-specific payloads
    in the `details` field. Admin privileges required.
    """
    _require_admin(user)
    inst = get_instance_by_id(instance_id)
    if not inst:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instance not found")
    record_provenance(
        actor="api",
        action="model.instance.get",
        resource="/model/instances/{instance_id}",
        input={"instance_id": instance_id},
        output={"instance": inst},
        meta={"user": _principal_name(user)},
    )
    return inst


try:
    from prometheus_client import Histogram  # type: ignore

    _TEST_LATENCY = Histogram(
        "model_instance_test_latency_ms",
        "Latency of model instance test calls (ms)",
        labelnames=("instance_id", "provider"),
        buckets=(5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000),
    )
except Exception:  # pragma: no cover
    _TEST_LATENCY = None  # type: ignore


async def _provider_preflight(client) -> None:
    """Perform a very short preflight request to the provider base URL to catch fast failures.

    We deliberately keep this lightweight: a GET to base_url (or /health if it exists) with 1s timeout.
    Failures are silently ignored (we still attempt the real call) unless the failure is a connection error,
    in which case we raise to map to 502 earlier.
    """
    import httpx

    base = getattr(client, "base_url", None)
    if not base:
        return
    # Normalize trailing slash
    if base.endswith("/"):
        base = base[:-1]
    # Try common quick endpoints: OpenAI root, health, and models listing
    candidate_urls = [base + path for path in ("/health", "/models", "")]
    for u in candidate_urls:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(connect=1.0, read=2.0, write=2.0, pool=1.0)) as http:
                await http.get(u)
            return  # success or at least reachable
        except httpx.ConnectError as ce:  # immediate connection failure
            raise HTTPException(status_code=502, detail=f"Provider unreachable at {base}: {ce}")
        except Exception:
            # Ignore other failures (timeouts, 404) and try next candidate
            continue


# NOTE: This endpoint has been DISABLED and moved to model_instances.py
# Use POST /v1/models/instances/{instance_id}/tests instead (or legacy /v1/admin/models/instances/{instance_id}/tests)
#
# @router.post(
#     "/instances/{instance_id}/tests",
#     response_model=TestResponse,
#     tags=["models-instances"],
#     summary="Run a short test prompt against an instance",
#     description="""
# Execute a short diagnostic prompt against a specific loaded model instance using the configured provider.
#
# This endpoint performs a live call to the instance's provider (OpenAI-compatible Chat Completions).
# Body parameters: `prompt`, optional `model` override, `temperature`, `max_tokens`.
# Returns provider output (first choice), `usage` tokens when supplied by provider, and provenance trace IDs.
# Falls back to demo response ONLY when no providers are registered AND settings.DEMO_MODE=true.
#
# **Examples**:
# - Factual query (deterministic): `{"prompt": "Explain quantum computing in one sentence.", "temperature": 0.0, "max_tokens": 64}`
# - Short answer: `{"prompt": "What is the capital of France?", "temperature": 0.0, "max_tokens": 32, "stop": ["\\n\\n"]}`
# - Creative task: `{"prompt": "Write a haiku about programming.", "temperature": 0.7, "max_tokens": 100}`
# """,
#     responses={
#         200: {
#             "description": "Provider returned a response with model output and observability metadata",
#             "content": {
#                 "application/json": {
#                     "example": {
#                         "model": "llama3.2:3b-instruct",
#                         "output": "Quantum computing uses quantum-mechanical phenomena such as superposition and entanglement to perform calculations exponentially faster than classical computers.",
#                         "usage": {
#                             "prompt_tokens": 32,
#                             "completion_tokens": 28,
#                             "total_tokens": 60
#                         },
#                         "trace_id": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
#                         "event_id": "evt_7f8e9d0a1b2c3d4e5f6",
#                         "provider": "ollama-local",
#                         "latency_ms": 1842.5,
#                         "parameters": {
#                             "temperature": 0.0,
#                             "max_tokens": 64,
#                             "stop": ["\n\n", "```", "---"]
#                         }
#                     }
#                 }
#             },
#         },
#         404: {
#             "description": "Instance not found",
#             "content": {
#                 "application/problem+json": {
#                     "example": {
#                         "type": "about:blank",
#                         "title": "instance not found",
#                         "status": 404,
#                         "detail": "Instance not found",
#                         "traceId": "deadbeef",
#                         "extensions": {"correlation_id": "deadbeef", "event_id": "evt_missing"},
#                     }
#                 }
#             },
#         },
#         409: {
#             "description": "Instance not loaded",
#             "content": {
#                 "application/problem+json": {
#                     "example": {
#                         "type": "about:blank",
#                         "title": "instance not loaded",
#                         "status": 409,
#                         "detail": "Instance not loaded",
#                         "traceId": "deadbeef",
#                         "extensions": {"correlation_id": "deadbeef", "event_id": "evt_unloaded"},
#                     }
#                 }
#             },
#         },
#         502: {
#             "description": "Provider error",
#             "content": {
#                 "application/problem+json": {
#                     "example": {
#                         "type": "about:blank",
#                         "title": "provider request failed",
#                         "status": 502,
#                         "detail": "Upstream provider error",
#                         "traceId": "deadbeef",
#                         "extensions": {"correlation_id": "deadbeef", "event_id": "evt_bad_gateway"},
#                     }
#                 }
#             },
#         },
#     },
# )
async def _DISABLED_instance_test(
    instance_id: str,
    request: Request,
    user: UserInfo = Depends(get_current_user),
    req: TestRequest = Body(
        ...,
        openapi_examples={
            "quantum_computing": {
                "summary": "Factual query (deterministic)",
                "description": "Ask a specific factual question with deterministic output",
                "value": {"prompt": "Explain quantum computing in one sentence.", "temperature": 0.0, "max_tokens": 64},
            },
            "capital_question": {
                "summary": "Short answer with custom stop",
                "description": "Simple question with shorter token limit and custom stop sequence",
                "value": {
                    "prompt": "What is the capital of France?",
                    "temperature": 0.0,
                    "max_tokens": 32,
                    "stop": ["\n\n"],
                },
            },
            "creative_haiku": {
                "summary": "Creative task (non-deterministic)",
                "description": "Generate creative content with higher temperature",
                "value": {
                    "prompt": "Write a haiku about programming.",
                    "temperature": 0.7,
                    "max_tokens": 100,
                    "stop": None,
                },
            },
        },
    ),
) -> TestResponse:
    # Validate input: either prompt or messages must be provided
    if not req.prompt and not req.messages:
        return problem_response(
            status.HTTP_400_BAD_REQUEST,
            "missing prompt or messages",
            detail="Either 'prompt' or 'messages' must be provided",
            request=request,
            extra={"instance_id": instance_id},
        )

    # Resolve instance
    inst = get_instance_by_id(instance_id)
    if not inst:
        ev = record_provenance(
            actor="api",
            action="model.test",
            resource=f"/model/instances/{instance_id}/tests",
            input=req.model_dump(),
            output={"error": "Instance not found"},
            meta={"user": _principal_name(user), "instance_id": instance_id},
            success=False,
        )
        return problem_response(
            status.HTTP_404_NOT_FOUND,
            "instance not found",
            detail="Instance not found",
            request=request,
            extra={"instance_id": instance_id},
            extensions={"event_id": getattr(ev, "event_id", None)},
        )
    if not inst.get("loaded"):
        ev = record_provenance(
            actor="api",
            action="model.test",
            resource=f"/model/instances/{instance_id}/tests",
            input=req.model_dump(),
            output={"error": "Instance not loaded"},
            meta={"user": _principal_name(user), "instance_id": instance_id},
            success=False,
        )
        return problem_response(
            status.HTTP_409_CONFLICT,
            "instance not loaded",
            detail="Instance not loaded",
            request=request,
            extra={"instance_id": instance_id},
            extensions={"event_id": getattr(ev, "event_id", None)},
        )

    # Get provider_id from instance (prioritize database)
    provider_name = inst.get("provider_id") or inst.get("provider")

    # Add comprehensive tracing for debugging
    logger.info(
        "model.instance.test.lookup",
        extra={
            "instance_id": instance_id,
            "instance_name": inst.get("instance_name"),
            "provider_id": provider_name,
            "model_id": inst.get("model_id"),
            "enabled": inst.get("enabled"),
            "loaded": inst.get("loaded"),
        },
    )

    # Primary: Fetch provider from database repository (PostgreSQL)
    provider_ctx: dict[str, Any] | None = None
    provider_api_key: str | None = None

    if provider_name:
        # Get provider from PostgreSQL database with secrets
        with suppress(Exception):
            provider_ctx = pg_repo.get_provider(provider_name, include_secrets=True)

        # Log provider resolution
        logger.info(
            "model.instance.test.provider_resolved",
            extra={
                "instance_id": instance_id,
                "provider_id": provider_name,
                "provider_found": provider_ctx is not None,
                "provider_base_url": provider_ctx.get("base_url") if provider_ctx else None,
            },
        )

        # Extract API key if available
        if provider_ctx and isinstance(provider_ctx, dict):
            provider_api_key = provider_ctx.get("api_key")
    else:
        logger.warning("model.instance.test.no_provider", extra={"instance_id": instance_id, "instance_data": inst})

    # Fallback: Try orchestrator only if database lookup failed
    client = None
    if not provider_ctx and provider_name:
        try:
            from src.services.orchestrator import get_orchestrator_instance

            orch = get_orchestrator_instance()
            client = getattr(orch, "llm_clients", {}).get(provider_name) if provider_name else None
            logger.info(
                "model.instance.test.orchestrator_fallback",
                extra={"instance_id": instance_id, "provider_id": provider_name, "client_found": client is not None},
            )
        except Exception as e:
            logger.warning(
                "model.instance.test.orchestrator_error", extra={"instance_id": instance_id, "error": str(e)}
            )

    # Use database provider first, fallback to orchestrator client
    final_provider_ctx = provider_ctx or client
    ollama_provider = is_ollama_provider(final_provider_ctx)
    effective_base_url = resolve_provider_base_url(final_provider_ctx)
    if not effective_base_url and client and getattr(client, "base_url", None):
        effective_base_url = str(client.base_url).rstrip("/")

    logical_model = inst.get("model_id") or inst.get("name") or instance_id
    upstream_model = resolve_upstream_model_id(final_provider_ctx, logical_model, req.model, inst)
    model_id = upstream_model or req.model or logical_model

    # Normalize request to chat messages with system prompt (used by all paths)
    prompt_hash = test_helpers.hash_prompt(req.prompt or str(req.messages))
    try:
        messages = test_helpers.normalize_request_to_messages(
            prompt=req.prompt,
            messages=req.messages,
            model_id=model_id,
            one_sentence=req.one_sentence,
            no_system=req.no_system,
            format_hint=req.format_hint,
        )
    except (TypeError, ValueError) as exc:
        return _error(
            "invalid request parameters",
            f"Invalid request: {exc}",
            status.HTTP_400_BAD_REQUEST,
        )

    # Compute smart stop sequences
    try:
        computed_stop = test_helpers.get_stop_sequences(
            one_sentence=req.one_sentence,
            model_id=model_id,
            custom_stop=req.stop,
        )
    except (TypeError, ValueError) as exc:
        return _error(
            "invalid request parameters",
            f"Invalid request: {exc}",
            status.HTTP_400_BAD_REQUEST,
        )

    # Check warm-up cache
    should_warmup = test_helpers.should_warmup(instance_id)

    if ollama_provider and upstream_model and upstream_model != logical_model:
        with suppress(Exception):
            logger.info(
                "model.instance.test.ollama_model_mapped",
                extra={
                    "instance_id": instance_id,
                    "provider": provider_name,
                    "logical_model": logical_model,
                    "mapped_model": upstream_model,
                },
            )

    usage = Usage()
    provider_status: int | None = None
    t0 = time.perf_counter()
    principal = _principal_name(user)
    logger.info("model.instance.test.start", extra={"instance_id": instance_id, "provider": provider_name})

    def _latency_ms() -> float:
        return (time.perf_counter() - t0) * 1000.0

    def _error(title: str, detail: str, status_code: int, *, extra: dict[str, Any] | None = None) -> JSONResponse:
        latency_ms = _latency_ms()
        meta = {
            "user": principal,
            "provider": provider_name,
            "instance_id": instance_id,
            "model": model_id,
            "latency_ms": latency_ms,
            "status": provider_status,
        }
        if extra:
            meta.update(extra)
        ev = record_provenance(
            actor="api",
            action="model.test",
            resource=f"/model/instances/{instance_id}/tests",
            input=req.model_dump(),
            output={"error": detail},
            meta=meta,
            success=False,
        )
        logger.warning(
            "model.instance.test.error",
            extra={
                "instance_id": instance_id,
                "provider": provider_name,
                "status": provider_status,
                "title": title,
                "detail": detail,
                "latency_ms": latency_ms,
            },
        )
        body_extra = {"instance_id": instance_id, "provider": provider_name}
        if extra:
            body_extra.update(extra)
        if provider_status is not None:
            body_extra.setdefault("provider_status", provider_status)
        return problem_response(
            status_code,
            title,
            detail=detail,
            request=request,
            extra=body_extra,
            extensions={"event_id": getattr(ev, "event_id", None)},
        )

    # Prefer orchestrator client when it has a base_url; otherwise, use provider_base_url from repo
    if effective_base_url:
        # Egress allowlist enforcement
        if not _egress_allowed(effective_base_url):
            allowlist = settings.EGRESS_ALLOWLIST or "<empty>"
            host = urlparse(effective_base_url).netloc or effective_base_url
            return _error(
                "egress not allowed",
                f"egress not allowed for host '{host}' (EGRESS_ALLOWLIST={allowlist})",
                status.HTTP_403_FORBIDDEN,
                extra={"host": host, "allowlist": allowlist},
            )
        # Preflight (best-effort) to detect immediate connectivity issues
        try:
            await _provider_preflight(
                client if getattr(client, "base_url", None) else SimpleNamespace(base_url=effective_base_url)
            )
        except HTTPException as exc:
            return _error("provider unreachable", exc.detail, exc.status_code)
        except Exception:
            pass
        import httpx

        base_url = effective_base_url.rstrip("/")
        cfg = None
        if final_provider_ctx is not None:
            cfg = getattr(final_provider_ctx, "config", None)
            if cfg is None and isinstance(final_provider_ctx, dict):
                cfg = final_provider_ctx.get("config_json") or final_provider_ctx.get("config")
        path_override = None
        if isinstance(cfg, dict):
            paths_cfg = cfg.get("paths")
            if isinstance(paths_cfg, dict):
                path_override = paths_cfg.get("chat_completions") or paths_cfg.get("completions")
        url = urljoin(base_url + "/", (path_override or "/chat/completions").lstrip("/"))

        # Build payload with pre-computed messages and stops
        payload = {
            "model": model_id,
            "messages": messages,
        }
        if req.temperature is not None:
            payload["temperature"] = req.temperature
        if req.max_tokens is not None:
            payload["max_tokens"] = req.max_tokens
        if computed_stop:
            payload["stop"] = computed_stop
        metadata_payload = req.metadata if isinstance(req.metadata, dict) else None
        header_source = final_provider_ctx
        headers = (
            _build_upstream_headers(header_source, metadata=metadata_payload)
            if header_source
            else {"Content-Type": "application/json"}
        )
        if provider_api_key and "Authorization" not in headers:
            headers["Authorization"] = f"Bearer {provider_api_key}"
        timeout = timeout_for_provider(final_provider_ctx, default=DEFAULT_HTTPX_TIMEOUT)
        log_context = {
            "instance_id": instance_id,
            "provider": provider_name,
            "logical_model": logical_model,
            "prompt_hash": prompt_hash,
            "warm_cache_hit": not should_warmup,
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as http:
                start_time = time.perf_counter()
                resp = await http.post(url, json=payload, headers=headers)
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                debug_log_provider_call(
                    logger,
                    event="model.instance.test.provider_call",
                    trace_meta=log_context,
                    base_url=effective_base_url,
                    resolved_model=logical_model,
                    mapped_model=upstream_model,
                    elapsed_ms=elapsed_ms,
                    status_code=resp.status_code,
                    extra={"url": url},
                )
                provider_status = resp.status_code
                if resp.status_code >= 400:
                    try:
                        body = resp.json()
                    except Exception:
                        body = {"raw": resp.text[:500]}
                    if resp.status_code == status.HTTP_404_NOT_FOUND:
                        return _error(
                            "model not present in provider",
                            f"model '{model_id}' not configured for provider",
                            status.HTTP_404_NOT_FOUND,
                            extra={"provider_response": body},
                        )
                    if status.HTTP_400_BAD_REQUEST <= resp.status_code < status.HTTP_500_INTERNAL_SERVER_ERROR:
                        return _error(
                            "upstream request failed",
                            "Provider returned client error",
                            status.HTTP_424_FAILED_DEPENDENCY,
                            extra={"provider_response": body},
                        )
                    return _error(
                        "provider request failed",
                        "Upstream provider error",
                        status.HTTP_502_BAD_GATEWAY,
                        extra={"provider_response": body},
                    )
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            elapsed_ms = (
                int((time.perf_counter() - start_time) * 1000)
                if "start_time" in locals()
                else int((time.perf_counter() - t0) * 1000)
            )
            provider_status = exc.response.status_code
            try:
                body = exc.response.json()
            except Exception:
                body = {"raw": exc.response.text[:500] if exc.response else str(exc)}
            detail = (
                body.get("error", {}).get("message") or body.get("message") if isinstance(body, dict) else str(body)
            )
            if provider_status == status.HTTP_404_NOT_FOUND:
                detail = f"model '{model_id}' not configured for provider"
            debug_log_provider_call(
                logger,
                event="model.instance.test.provider_http_error",
                trace_meta=log_context,
                base_url=effective_base_url,
                resolved_model=logical_model,
                mapped_model=upstream_model,
                elapsed_ms=elapsed_ms,
                status_code=provider_status,
                error=detail,
                extra={"url": url},
            )
            return _error(
                "provider request failed",
                detail or "provider request failed",
                status.HTTP_502_BAD_GATEWAY,
                extra={"provider_response": body},
            )
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError, httpx.RequestError) as exc:
            provider_status = 0
            elapsed_ms = (
                int((time.perf_counter() - start_time) * 1000)
                if "start_time" in locals()
                else int((time.perf_counter() - t0) * 1000)
            )
            detail = f"provider request failed: {type(exc).__name__}: {exc} (url={url})"
            debug_log_provider_call(
                logger,
                event="model.instance.test.provider_error",
                trace_meta=log_context,
                base_url=effective_base_url,
                resolved_model=logical_model,
                mapped_model=upstream_model,
                elapsed_ms=elapsed_ms,
                error=detail,
                extra={"url": url},
            )
            return _error("provider request failed", detail, status.HTTP_502_BAD_GATEWAY)
        except Exception as exc:
            provider_status = 0
            elapsed_ms = (
                int((time.perf_counter() - start_time) * 1000)
                if "start_time" in locals()
                else int((time.perf_counter() - t0) * 1000)
            )
            detail = f"provider request failed: {type(exc).__name__}: {exc} (url={url})"
            debug_log_provider_call(
                logger,
                event="model.instance.test.provider_exception",
                trace_meta=log_context,
                base_url=effective_base_url,
                resolved_model=logical_model,
                mapped_model=upstream_model,
                elapsed_ms=elapsed_ms,
                error=detail,
                extra={"url": url},
            )
            return _error("provider request failed", detail, status.HTTP_502_BAD_GATEWAY)

        # Extract text from response (handles JSON strings, null content)
        # extract_text_from_response returns (text, usage_dict) tuple
        output_text, extracted_usage = test_helpers.extract_text_from_response(data, model_id)

        # Note: normalize_output_text is already called inside extract_text_from_response
        # So output_text is already normalized here

        # Truncate to one sentence if requested
        if req.one_sentence and output_text:
            output_text = test_helpers.truncate_to_sentence(output_text)

        # Use extracted usage if available, otherwise estimate
        if extracted_usage:
            usage = Usage(
                prompt_tokens=extracted_usage.get("prompt_tokens", 0),
                completion_tokens=extracted_usage.get("completion_tokens", 0),
                total_tokens=extracted_usage.get("total_tokens", 0),
            )
        elif isinstance(data, dict) and "usage" in data and isinstance(data["usage"], dict):
            u = data["usage"]
            usage = Usage(
                prompt_tokens=int(u.get("prompt_tokens") or 0),
                completion_tokens=int(u.get("completion_tokens") or 0),
                total_tokens=int(u.get("total_tokens") or 0),
            )
        else:
            # Fallback: estimate usage
            estimated = test_helpers.estimate_usage(req.prompt or "", output_text)
            usage = Usage(
                prompt_tokens=estimated["prompt_tokens"],
                completion_tokens=estimated["completion_tokens"],
                total_tokens=estimated["total_tokens"],
            )

        # Mark as warmed up
        if should_warmup:
            test_helpers.mark_warmed(instance_id)

        latency_ms = _latency_ms()
    elif client and not getattr(client, "base_url", None):
        # Local client path: reuse client.complete (text-only)
        prompt_text = req.prompt or (messages[0].get("content", "") if messages else "")
        try:
            result = await client.complete(
                prompt_text,
                model=model_id,
                temperature=req.temperature,
                max_tokens=req.max_tokens,
                metadata=req.metadata,
                user=user.model_dump(),
            )
            output_text = test_helpers.normalize_output_text(str(result))
            if req.one_sentence and output_text:
                output_text = test_helpers.truncate_to_sentence(output_text)
            # Estimate usage for local client
            estimated = test_helpers.estimate_usage(prompt_text, output_text)
            usage = Usage(
                prompt_tokens=estimated["prompt_tokens"],
                completion_tokens=estimated["completion_tokens"],
                total_tokens=estimated["total_tokens"],
            )
        except Exception as exc:
            provider_status = None
            return _error("local client error", f"local client error: {exc}", status.HTTP_502_BAD_GATEWAY)
        latency_ms = _latency_ms()
    else:
        # No provider client registered for this instance
        if settings.DEMO_MODE and _repo.provider_count() == 0:
            output_text = f"(demo test) {req.prompt or 'test prompt'}"
        else:
            return _error("provider not available", "Provider not available for instance", status.HTTP_502_BAD_GATEWAY)
        latency_ms = _latency_ms()

    ev = record_provenance(
        actor="api",
        action="model.test",
        resource=f"/model/instances/{instance_id}/tests",
        input=req.model_dump(),
        output={"output": output_text, "usage": usage.model_dump()},
        meta={
            "user": principal,
            "model": model_id,
            "provider": provider_name,
            "instance_id": instance_id,
            "latency_ms": latency_ms,
            "status": provider_status,
        },
        success=True,
    )
    logger.info(
        "model.instance.test.end",
        extra={
            "instance_id": instance_id,
            "provider": provider_name,
            "latency_ms": latency_ms,
            "status": provider_status,
        },
    )
    # Metrics
    try:  # pragma: no cover
        if _TEST_LATENCY and latency_ms is not None:
            _TEST_LATENCY.labels(instance_id=instance_id, provider=str(provider_name)).observe(latency_ms)
    except Exception:
        pass

    # Collect actual parameters used for transparency
    actual_parameters = {
        "temperature": req.temperature,
        "max_tokens": req.max_tokens,
        "one_sentence": req.one_sentence,
    }
    if computed_stop:
        actual_parameters["stop"] = computed_stop
    if req.format_hint:
        actual_parameters["format_hint"] = req.format_hint

    return TestResponse(
        model=model_id,
        output=output_text,
        usage=usage,
        trace_id=ev.trace_id,
        event_id=ev.event_id,
        provider=provider_name,
        provider_base_url=effective_base_url,
        latency_ms=latency_ms,
        parameters=actual_parameters,
    )


# ============================================================================
# DEPRECATED: Old builtins manifest endpoints (replaced by src/routers/manifests.py)
#
# These endpoints have been migrated to a dedicated manifests router with:
# - PostgreSQL authoritative storage
# - Proper ETag/304 support
# - Redis caching with TTLs
# - Prometheus metrics
# - Activation locks
# - Full audit trail
#
# The new implementation is mounted at the same paths via src/routers/admin.py
# ============================================================================

# @router.get("/manifests/builtins") - REMOVED, see src/routers/manifests.py
# @router.post("/manifests/builtins/staged") - REMOVED, see src/routers/manifests.py
# @router.post("/manifests/builtins/activations") - REMOVED, see src/routers/manifests.py
# @router.post("/manifests/builtins/rollbacks") - REMOVED, see src/routers/manifests.py
# @router.get("/manifests/builtins/history") - REMOVED, see src/routers/manifests.py


# ---------------- Runtime LLM client management ----------------
# Import canonical schemas from centralized schema module
from src.schemas.providers import (
    ActionResponse,
    GetMainProviderResponse,
    ProviderListResponse,
    RegisterProviderRequest,
    SetDefaultProviderRequest,
    UpdateProviderRequest,
)


# NOTE: UnregisterLLMRequest imported from schemas.models


@router.get(
    "/providers",
    response_model=ProviderListResponse,
    tags=["models-providers"],
    summary="List runtime LLM providers",
    description="""
List configured runtime LLM providers (registry-only, Redis-backed).

**RBAC**: Requires admin:all scope. Returns providers exactly as previously registered via
POST /v1/admin/models/providers/register. No discovery logic.

**Multi-tenant visibility**:
- Admin users see **all** providers (global + all tenant-scoped)
- Providers with `tenant_id=null` are global (available to all tenants)
- Providers with specific `tenant_id` are scoped to that tenant only
- Future non-admin endpoint would filter to user's tenant + global providers

**Pagination**:
- Query params: `page_size` (integer, 1-1000, default 100), `page_token` (string, optional)
- Returns: `{items: Provider[], next_page_token?: string, total?: number}`
- Link header (RFC 5988) included when next page available

**Caching**:
- Supports `If-None-Match` header for conditional requests
- Returns `304 Not Modified` if ETag matches
- `ETag` header always present on 200 responses

**Response headers**:
- `ETag`: Content hash for caching
- `Link`: Next page URL (when applicable)
- `X-Request-Id`: Request correlation ID
- `RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset`: Rate limit status

**Provider config**:
- `config` field may contain **arbitrary provider-specific keys** added via PATCH
- Schema accepts extra fields to support custom provider configurations
- Nested objects are preserved (e.g., `config.custom_field.nested_value`)

**Secret redaction**:
- `api_key`: Always null or masked ("***")
- `has_api_key`: Boolean indicating if api_key is configured
- `config.headers.authorization`, `config.auth.token`: Masked
""",
)
async def list_providers(
    request: Request,
    response: Response,
    page_size: int = Query(default=100, ge=1, le=1000),
    page_token: str | None = Query(default=None),
    tenant_id: str = Depends(require_tenant_header),
    user: UserInfo = Depends(require_perms(["admin:all"])),
) -> ProviderListResponse:
    """List providers with pagination, caching, and proper secret redaction (PostgreSQL-backed).

    Returns providers in paginated format with Link headers and ETag support.
    All secrets are redacted, with has_api_key boolean indicator.
    """
    # Get all providers from PostgreSQL (already redacted by pg_repo layer)
    tenant_filter = None if tenant_id == "global" else tenant_id
    all_providers = pg_repo.list_providers(tenant_id=tenant_filter)

    # Attach cached health snapshots (non-blocking)
    for p in all_providers:
        try:
            health = pg_repo.get_provider_health(p.get("id"))
            if health:
                p["health"] = health
        except Exception:
            pass

    # Paginate
    page_items, next_token = make_page(all_providers, page_size=page_size, page_token=page_token)

    # Compute ETag for caching
    etag = pg_repo.compute_list_etag(page_items)
    inm = request.headers.get("if-none-match")
    if inm and inm == etag:
        response.status_code = status.HTTP_304_NOT_MODIFIED
        return ProviderListResponse(items=[], next_page_token=None)

    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, max-age=60"
    response.headers["Vary"] = "Authorization"

    # Add Link header for pagination (RFC 5988)
    if next_token:
        # Build next page URL
        base_path = str(request.url.path)
        next_url = f"{base_path}?page_size={page_size}&page_token={next_token}"
        response.headers["Link"] = f'<{next_url}>; rel="next"'

    # Provenance logging
    record_provenance(
        actor="api",
        action="model.providers.list",
        resource="/model/providers",
        input={"tenant_id": tenant_id, "page_size": page_size, "page_token": page_token},
        output={"count": len(page_items)},
        meta={"user": _principal_name(user)},
    )

    return ProviderListResponse(
        items=page_items, next_page_token=next_token, total=len(all_providers)  # Optional: include total count
    )


# Tagging for OpenAPI: providers
list_providers.__dict__.setdefault("__tags__", ["Models – Providers"])


@router.post(
    "/providers/register",
    response_model=ActionResponse,
    tags=["models-providers"],
    summary="Register a runtime LLM provider",
    description="""
Register a new runtime LLM provider with the platform.

Admin-only operation to add or register an external LLM endpoint for use by the
orchestrator. The request should include the provider `name`, `base_url`, and optional
fields like `model` and `api_key`. On success the provider will be available for selection
and orchestration.

**RBAC**: Requires `admin:all` scope.

**Tenant scoping**:
- `tenant_id` (optional): If provided, provider is scoped to that tenant only
- If omitted or null: Provider is **global** and available to all tenants
- Admin users see all providers (global + tenant-scoped) in LIST
- Future non-admin endpoints would filter by user's tenant

**Request validation**:
- `name`: Required, 1-255 characters
- `type`: Required, must be `openai_compatible` or `custom`
- `base_url`: Required for `openai_compatible` type
- `api_key`: Optional, will be stored securely and never returned in responses

**Idempotency**:
- Registering same `(tenant_id, name)` with **identical config** → **200 OK** (no-op, idempotent)
- Comparison normalizes configs (ignores key order, compares api_key presence via `has_api_key` boolean)
- Registering same name with **different config** → **409 Conflict** with diff details in `X-Conflict-Details` header

**Status codes**:
- 200: Provider registered successfully (or idempotent no-op)
- 400: Business logic error (e.g., egress not allowed)
- 403: Forbidden (egress allowlist violation)
- 409: Conflict (provider exists with different config)
- 422: Validation error (invalid fields)
""",
)
async def register_client(
    req: RegisterProviderRequest, user: UserInfo = Depends(require_perms(["admin:all"]))
) -> ActionResponse:
    """Register a runtime LLM provider with idempotency support.

    Requires admin privileges. Returns an ActionResponse with the registered provider name on
    success. Implements idempotency: if provider exists with same config, returns 200 with note.
    If exists with different config, returns 409 Conflict.
    """
    _require_admin(user)

    # Validation: provider type and config
    try:
        cfg = _validate_provider_payload(req.type.value, req.base_url, req.config)
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))

    base_url = req.base_url or (cfg.base_url if cfg else None)

    # Egress allowlist validation
    if base_url and not _egress_allowed(base_url):
        allowlist = settings.EGRESS_ALLOWLIST or "<empty>"
        host = urlparse(base_url).netloc or base_url
        raise HTTPException(status_code=403, detail=f"Egress not allowed for host '{host}' (allowlist: {allowlist})")

    # Create provider using PostgreSQL repository (handles idempotency internally)
    try:
        provider = pg_repo.create_provider(
            name=req.name,
            type=req.type.value,
            base_url=base_url,
            model=req.model,
            api_key=req.api_key,
            tenant_id=req.tenant_id,
            config=cfg.model_dump() if cfg else req.config,
            actor=_principal_name(user),
        )

        # Record successful registration
        ev = record_provenance(
            actor="api",
            action="model.providers.register",
            resource="/model/providers/register",
            input=req.model_dump(),
            output={"name": req.name, "provider_id": provider.get("id")},
            meta={"user": _principal_name(user)},
            success=True,
        )

        # Sync to orchestrator (best-effort, don't fail request if sync fails)
        try:
            _repo.sync_providers_to_orchestrator()
        except Exception as sync_err:
            logger.warning(f"Failed to sync provider to orchestrator: {sync_err}")

        return ActionResponse(
            ok=True,
            message=f"Successfully registered provider {req.name}",
            details={"name": req.name, "type": req.type.value, "base_url": base_url},
            trace_id=ev.trace_id,
            event_id=ev.event_id,
        )

    except ValueError as ve:
        # Provider exists - check if idempotent (same config) or conflict (different config)
        if "already exists" in str(ve):
            # Get existing provider to compare
            existing = pg_repo.get_provider(req.name, include_secrets=False)
            if existing:
                # Normalize config for comparison
                def normalize_config(cfg):
                    if cfg is None:
                        return {}
                    if isinstance(cfg, dict):
                        return {k: v for k, v in sorted(cfg.items()) if k not in ("api_key", "auth")}
                    return cfg.model_dump(exclude={"api_key", "auth"}) if hasattr(cfg, "model_dump") else {}

                existing_base_url = (existing.get("base_url") or "").rstrip("/")
                req_base_url = (base_url or "").rstrip("/")
                existing_has_key = existing.get("has_api_key", False)
                req_has_key = bool(req.api_key)

                same_config = (
                    existing.get("type") == req.type.value
                    and existing_base_url == req_base_url
                    and existing.get("model") == req.model
                    and existing.get("tenant_id") == req.tenant_id
                    and existing_has_key == req_has_key
                    and normalize_config(existing.get("config_json")) == normalize_config(cfg or req.config)
                )

                if same_config:
                    # Idempotent: same provider, return success with note
                    ev = record_provenance(
                        actor="api",
                        action="model.providers.register",
                        resource="/model/providers/register",
                        input=req.model_dump(),
                        output={"name": req.name, "idempotent": True},
                        meta={"user": _principal_name(user)},
                        success=True,
                    )
                    return ActionResponse(
                        ok=True,
                        message=f"Provider {req.name} already registered with same configuration",
                        details={"name": req.name, "idempotent": True},
                        trace_id=ev.trace_id,
                        event_id=ev.event_id,
                    )
                else:
                    # Conflict: different config
                    diff_details = {}
                    if existing.get("type") != req.type.value:
                        diff_details["type"] = {"existing": existing.get("type"), "requested": req.type.value}
                    if existing_base_url != req_base_url:
                        diff_details["base_url"] = {"existing": existing_base_url, "requested": req_base_url}
                    if existing.get("model") != req.model:
                        diff_details["model"] = {"existing": existing.get("model"), "requested": req.model}
                    if existing.get("tenant_id") != req.tenant_id:
                        diff_details["tenant_id"] = {"existing": existing.get("tenant_id"), "requested": req.tenant_id}
                    if existing_has_key != req_has_key:
                        diff_details["has_api_key"] = {"existing": existing_has_key, "requested": req_has_key}

                    raise HTTPException(
                        status_code=409,
                        detail=f"Provider '{req.name}' already exists with different configuration",
                        headers={"X-Conflict-Details": str(diff_details)},
                    )

        raise HTTPException(status_code=409, detail=str(ve))
    except Exception as exc:
        logger.error(f"Failed to register provider: {exc}")
        raise HTTPException(status_code=400, detail=str(exc))


register_client.__dict__.setdefault("__tags__", ["Models – Providers"])


@router.get(
    "/providers/main",
    response_model=GetMainProviderResponse,
    tags=["models-providers"],
    summary="Get resolved main LLM provider for a tenant (or global if none)",
    description="""
Get the resolved main LLM provider for a tenant or the global default.

**RBAC**: Admin-only endpoint (requires `admin:all` scope).

**Resolution precedence**:
1. Tenant-scoped default (if tenant_id provided and tenant has a default)
2. Global default (if no tenant default exists)
3. 404 Not Found (if no defaults configured)

**Caching**:
- Supports `If-None-Match` header for conditional requests
- Returns `304 Not Modified` if ETag matches
- `ETag` header always present on 200 responses

**Status codes**:
- 200: Default provider found and returned
- 304: Not Modified (ETag match)
- 404: No default provider configured
""",
)
async def get_main_client(
    request: Request,
    response: Response,
    tenant_id: str | None = None,
    user: UserInfo = Depends(require_perms(["admin:all"])),
) -> GetMainProviderResponse:
    """Return the resolved main/default LLM provider for a tenant or global fallback.

    If `tenant_id` is omitted the global default provider is returned. Requires admin
    privileges. Returns 404 if no default is configured.
    """
    _require_admin(user)

    # Get default provider from PostgreSQL (with scope resolution)
    main_name: str | None = None
    try:
        default = pg_repo.get_provider_default(scope="global", tenant_id=tenant_id)
        if not default:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No default provider configured for tenant '{tenant_id or 'global'}'",
            )
        main_name = default.get("provider_id")  # Fixed: was provider_name, should be provider_id
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to get default provider: {exc}")
        record_provenance(
            actor="api",
            action="model.providers.get_main",
            resource="/model/providers/main",
            input={"tenant_id": tenant_id},
            output={"error": str(exc)},
            meta={"user": _principal_name(user)},
            success=False,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No default provider configured for tenant '{tenant_id or 'global'}'",
        )

    # Build response
    result = GetMainProviderResponse(ok=True, tenant_id=tenant_id, main=main_name)

    # ETag support for caching (compute based on default record)
    etag = pg_repo.compute_provider_etag(default)
    inm = request.headers.get("if-none-match")
    if inm and inm == etag:
        response.status_code = status.HTTP_304_NOT_MODIFIED
        return GetMainProviderResponse(ok=True, tenant_id=tenant_id, main=None)

    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, max-age=60"
    response.headers["Vary"] = "Authorization"

    record_provenance(
        actor="api",
        action="model.providers.get_main",
        resource="/model/providers/main",
        input={"tenant_id": tenant_id},
        output={"main": main_name},
        meta={"user": _principal_name(user)},
        success=True,
    )

    return result


@router.get(
    "/providers/{provider_id}",
    tags=["models-providers"],
    summary="Get provider details",
    description="""
Retrieve detailed information about a specific runtime LLM provider.

**RBAC**: Admin-only endpoint (requires `admin:all` scope).

**Secret redaction**:
- `api_key`: Always null or masked
- `has_api_key`: Boolean indicator showing if api_key is configured
- `config.headers.authorization`, `config.auth.token`: Masked

**Caching**:
- Supports `If-None-Match` header for conditional requests
- Returns `304 Not Modified` if ETag matches
- `ETag` header always present on 200 responses

**Status codes**:
- 200: Provider found and returned
- 304: Not Modified (ETag match)
- 404: Provider not found

**Response headers**:
- `ETag`: Content hash for caching
- `X-Request-Id`: Request correlation ID
""",
)
async def get_provider(
    provider_id: str, request: Request, response: Response, user: UserInfo = Depends(require_perms(["admin:all"]))
) -> dict[str, Any]:
    """Fetch provider registration details for `provider_id`.

    Useful for debugging provider configuration and verifying credentials or tenant
    assignments. Requires admin privileges. Returns 404 if provider not found.
    """
    _require_admin(user)

    # Get provider from PostgreSQL (secrets redacted by default)
    rec = pg_repo.get_provider(provider_id, include_secrets=False)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' not found")

    # Add health status if available
    try:
        health = pg_repo.get_provider_health(provider_id)
        if health:
            rec["health"] = health
    except Exception:
        pass

    # Compute ETag for caching
    etag = pg_repo.compute_provider_etag(rec)
    inm = request.headers.get("if-none-match")
    if inm and inm == etag:
        response.status_code = status.HTTP_304_NOT_MODIFIED
        return {}

    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, max-age=60"
    response.headers["Vary"] = "Authorization"
    if rec.get("updated_at"):
        # updated_at comes from repo as ISO string, convert to datetime for Last-Modified header
        from datetime import datetime

        try:
            dt = datetime.fromisoformat(rec["updated_at"].replace("Z", "+00:00"))
            response.headers["Last-Modified"] = dt.strftime("%a, %d %b %Y %H:%M:%S GMT")
        except Exception:
            pass  # Skip Last-Modified header if conversion fails

    record_provenance(
        actor="api",
        action="model.providers.get",
        resource=f"/model/providers/{provider_id}",
        input={"provider_id": provider_id},
        output={"ok": True},
        meta={"user": _principal_name(user)},
        success=True,
    )

    return rec


@router.patch(
    "/providers/{provider_id}",
    response_model=ActionResponse,
    tags=["models-providers"],
    summary="Patch provider details",
    description="""
Update registration details for an existing runtime LLM provider.

**RBAC**: Admin-only operation (requires `admin:all` scope).

**Behavior**:
- Supply any optional fields (base_url, model, api_key, tenant_id, config) to update
- **Config fields are merged** (not replaced) - provide partial updates
- **Arbitrary config keys are supported** (provider-specific customization)
- Provider is re-validated after merge
- Orchestrator is notified of changes

**Flexible config**:
- You can add arbitrary provider-specific keys under `config`
- Nested objects are preserved (e.g., `config.custom_field.nested_value`)
- LIST endpoint will return all config keys without validation errors
- Redaction rules still apply: `api_key`, `auth.token`, `headers.authorization` are masked

**Status codes**:
- 200: Provider updated successfully (includes trace_id/event_id)
- 400: Empty body (at least one field required)
- 403: Forbidden (egress allowlist violation)
- 404: Provider not found
- 422: Validation error (invalid merged config)

**Response**: ActionResponse with trace_id and event_id for auditing
""",
)
async def patch_provider(
    provider_id: str, req: UpdateProviderRequest, user: UserInfo = Depends(require_perms(["admin:all"]))
) -> ActionResponse:
    """Apply updates to an existing provider registration.

    Returns 404 if the provider does not exist. Requires admin privileges.
    """
    _require_admin(user)

    # Reject empty body (at least one field must be provided)
    if all(v is None for v in [req.base_url, req.model, req.api_key, req.tenant_id, req.config]):
        raise HTTPException(
            status_code=400,
            detail="At least one field must be provided for update (base_url, model, api_key, tenant_id, or config)",
        )

    # Load existing to merge type and config
    existing = pg_repo.get_provider(provider_id, include_secrets=False)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' not found")

    prov_type = existing.get("type")
    merged_cfg = existing.get("config_json") or {}
    if req.config:
        # Deep merge: user's partial update into existing config
        merged_cfg.update(req.config)

    base_url = req.base_url or existing.get("base_url")

    # Egress allowlist validation (only if base_url is being changed)
    if req.base_url and not _egress_allowed(req.base_url):
        allowlist = settings.EGRESS_ALLOWLIST or "<empty>"
        host = urlparse(req.base_url).netloc or req.base_url
        raise HTTPException(status_code=403, detail=f"Egress not allowed for host '{host}' (allowlist: {allowlist})")

    # Light validation: just ensure base_url exists if provider type requires it
    # Don't validate full config structure - allow arbitrary fields for flexibility
    if prov_type in {"openai_compatible"} and not base_url:
        raise HTTPException(status_code=422, detail="base_url is required for openai_compatible providers")

    # Record provenance context for audit
    ev = record_provenance(
        actor="api",
        action="model.providers.patch",
        resource=f"/model/providers/{provider_id}",
        input=req.model_dump() if hasattr(req, "model_dump") else {},
        output={"provider_id": provider_id},
        meta={"user": _principal_name(user)},
        success=True,
    )

    # Apply patch using PostgreSQL repository (handles audit logging)
    try:
        pg_repo.patch_provider(
            provider_id=provider_id,
            base_url=req.base_url,
            model=req.model,
            api_key=req.api_key,
            tenant_id=req.tenant_id,
            config=merged_cfg if req.config else None,
            actor=_principal_name(user),
            trace_id=ev.trace_id,
            event_id=ev.event_id,
        )

        # Sync to orchestrator asynchronously - don't fail request if sync fails
        try:
            _repo.sync_providers_to_orchestrator()
        except Exception as sync_err:
            logger.warning(f"Failed to sync provider to orchestrator: {sync_err}")

    except KeyError:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' not found")
    except Exception as exc:
        logger.error(f"Failed to patch provider: {exc}")
        raise HTTPException(status_code=400, detail=str(exc))

    return ActionResponse(
        ok=True,
        message=f"Successfully updated provider {provider_id}",
        details={"provider_id": provider_id},
        trace_id=ev.trace_id,
        event_id=ev.event_id,
    )


@router.delete(
    "/providers/{provider_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["models-providers"],
    summary="Delete/unregister a provider",
    description="""
Unregister and remove a runtime LLM provider from the platform.

**RBAC**: Admin-only operation (requires `admin:all` scope).

**Behavior**:
- Completely removes provider from registry
- **Auto-clears all defaults**: If provider is set as default (global or tenant), it is automatically cleared before deletion
- Orchestrator is notified of removal
- Safe deletion: No errors if provider was set as default

**Auto-clear defaults policy**:
- Checks all default scopes (global + all tenants)
- Clears any defaults pointing to this provider
- Clears both in-memory and Redis cache keys
- Atomic operation: defaults cleared, then provider deleted

**Status codes**:
- 204: Provider successfully deleted (no response body, but includes headers)
- 404: Provider not found

**Response headers** (always present on 204):
- `X-Request-Id`: Request correlation ID
- `X-Event-Id`: Event/provenance ID for auditing
- `X-Trace-Id`: Distributed trace ID
""",
)
async def delete_provider(
    provider_id: str, response: Response, user: UserInfo = Depends(require_perms(["admin:all"]))
) -> Response:
    """Unregister a provider identified by `provider_id`.

    Removes the provider from the orchestrator registry and returns 204 No Content on success.
    Requires admin privileges.
    """
    _require_admin(user)

    # Record provenance before deletion
    ev = record_provenance(
        actor="api",
        action="model.providers.delete",
        resource=f"/model/providers/{provider_id}",
        input={"provider_id": provider_id},
        output={"provider_id": provider_id},
        meta={"user": _principal_name(user)},
        success=True,
    )

    # Delete provider using PostgreSQL repository (handles cascade deletion)
    try:
        pg_repo.delete_provider(
            provider_id=provider_id, actor=_principal_name(user), trace_id=ev.trace_id, event_id=ev.event_id
        )

        # Sync to orchestrator asynchronously - don't fail request if sync fails
        try:
            _repo.sync_providers_to_orchestrator()
        except Exception as sync_err:
            logger.warning(f"Failed to sync provider deletion to orchestrator: {sync_err}")

    except ValueError as ve:
        # Provider not found
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as exc:
        logger.error(f"Failed to delete provider: {exc}")
        raise HTTPException(status_code=500, detail=f"Failed to delete provider: {exc!s}")

    # Set audit headers on the response
    response.headers["X-Event-Id"] = ev.event_id
    response.headers["X-Trace-Id"] = ev.trace_id
    response.status_code = status.HTTP_204_NO_CONTENT

    return response


@router.put(
    "/providers/default",
    response_model=ActionResponse,
    tags=["models-providers"],
    summary="Set a provider as default/global (or per-tenant)",
    description="""
Set a runtime LLM provider as the global or tenant-scoped default.

**RBAC**: Admin-only endpoint (requires `admin:all` scope).

**Behavior**:
- If `tenant_id` is **not provided** or null: Sets **global** default provider
- If `tenant_id` is **provided**: Sets **tenant-scoped** default provider
- Provider must exist or 404 is returned

**Default resolution precedence** (for context):
1. Tenant-scoped default (if request has tenant and tenant has default)
2. Global default (if no tenant default)
3. 404 (if no defaults configured)

**Status codes**:
- 200: Default provider successfully set (includes trace_id/event_id)
- 404: Provider not found
- 400: Business logic error

**Response**: ActionResponse with trace_id and event_id for auditing
""",
)
async def provider_set_default(
    req: SetDefaultProviderRequest, user: UserInfo = Depends(require_perms(["admin:all"]))
) -> ActionResponse:
    """Make `provider_id` the default provider globally or for a tenant.

    Supply `tenant_id` to scope the default change to a specific tenant. Requires admin
    privileges.
    """
    _require_admin(user)

    # Verify provider exists (using PostgreSQL)
    prov = pg_repo.get_provider(req.provider_id, include_secrets=False)
    if not prov:
        raise HTTPException(status_code=404, detail=f"Provider '{req.provider_id}' not found")

    # Record provenance before setting
    scope = req.tenant_id or "global"
    ev = record_provenance(
        actor="api",
        action="model.providers.set_default",
        resource="/model/providers/default",
        input={"provider_id": req.provider_id, "tenant_id": req.tenant_id},
        output={"provider_id": req.provider_id, "scope": scope},
        meta={"user": _principal_name(user)},
        success=True,
    )

    # Set provider default using PostgreSQL repository
    try:
        pg_repo.set_provider_default(
            scope=scope,
            provider_id=req.provider_id,
            tenant_id=req.tenant_id,
            actor=_principal_name(user),
            trace_id=ev.trace_id,
            event_id=ev.event_id,
        )
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as exc:
        logger.error(f"Failed to set default provider: {exc}")
        raise HTTPException(status_code=400, detail=str(exc))

    return ActionResponse(
        ok=True,
        message=f"Default provider set to {req.provider_id} (scope: {scope})",
        details={"provider_id": req.provider_id, "scope": scope},
        trace_id=ev.trace_id,
        event_id=ev.event_id,
    )


# Kebab-style OpenAPI colon-action route (tests expect lower-kebab action name)
# Legacy provider endpoints removed; prefer canonical colon-action routes


# ---------------- Helpers ----------------
async def _maybe_await(value: Any) -> Any:
    import inspect

    if inspect.isawaitable(value):
        return await value  # type: ignore[misc]
    return value
