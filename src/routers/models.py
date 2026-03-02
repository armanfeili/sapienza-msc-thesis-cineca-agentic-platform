"""
Models API (lightweight LLM surface)

Endpoints (mounted under /v1/models):
- GET  /v1/models                -> list available models (from adapters if present; else fallback)
- POST /v1/models/completions    -> simple text completion proxy (best-effort)

The router imports `src.adapters.llm` lazily and degrades gracefully if the
adapter is not implemented yet, returning a deterministic echo so that the API
remains usable during development.
"""

from __future__ import annotations

import time
import uuid
from contextlib import suppress
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.config import settings
from src.observability.metrics import MODEL_RUNTIME_COUNTER, MODEL_RUNTIME_HISTOGRAM
from src.provenance import record_provenance
from src.repositories import models_repo
from src.schemas.auth import UserInfo
from src.schemas.models import (
    ChatRequest,
    CompletionRequest,
    CompletionResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    EmbeddingVector,
    ModelInfo,
    Usage,
)
from src.routers.auth import get_current_user
from src.utils.pagination import compute_etag, make_page
from src.utils.provider_resolver import (
    DEFAULT_HTTPX_TIMEOUT,
    debug_log_provider_call as _debug_log_provider_call,
    is_ollama_provider as _is_ollama_provider,
    resolve_provider_base_url as _resolve_provider_base_url,
    resolve_upstream_model_id as _resolve_upstream_model_id,
    timeout_for_provider as _timeout_for_provider,
)

router = APIRouter(tags=["Models – Catalog"])


DEFAULT_UPSTREAM_TIMEOUT = DEFAULT_HTTPX_TIMEOUT


try:  # pragma: no cover - optional dependency
    from src.security.rate_limit import rate_limit_check as _rate_limit_check
except Exception:  # pragma: no cover
    _rate_limit_check = None  # type: ignore


# ---------------- Problem+JSON helper ----------------
def _resolve_trace_id(request: Request | None) -> str:
    if request is not None:
        with suppress(Exception):
            state_trace = getattr(request.state, "trace_id", None)
            if state_trace:
                return str(state_trace)
        if request.headers.get("X-Trace-Id"):
            return request.headers["X-Trace-Id"]
        if request.headers.get("X-Request-Id"):
            return request.headers["X-Request-Id"]
    return uuid.uuid4().hex


def problem_response(
    status_code: int,
    title: str,
    *,
    detail: str | None = None,
    type_: str | None = None,
    instance: str | None = None,
    request: Request | None = None,
    extra: dict[str, Any] | None = None,
    errors: list[Any] | None = None,
    extensions: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    resolved_trace = _resolve_trace_id(request)
    if request is not None:
        with suppress(Exception):
            request.state.trace_id = resolved_trace

    body: dict[str, Any] = {
        "type": type_ or "about:blank",
        "title": title,
        "status": status_code,
        "detail": detail or title,
        "traceId": resolved_trace,
    }
    if instance:
        body["instance"] = instance
    if errors:
        body["errors"] = errors

    ext: dict[str, Any] = {"correlation_id": resolved_trace}
    if extensions:
        ext.update(extensions)
    body["extensions"] = ext

    if extra:
        for key, value in extra.items():
            if key not in body:
                body[key] = value

    response_headers = dict(headers or {})
    response_headers.setdefault("X-Trace-Id", resolved_trace)
    if request is not None:
        req_id = request.headers.get("X-Request-Id")
        if req_id:
            response_headers.setdefault("X-Request-Id", req_id)

    return JSONResponse(
        status_code=status_code, content=body, media_type="application/problem+json", headers=response_headers
    )


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


def _egress_violation_detail(host: str) -> str:
    allowlist = settings.EGRESS_ALLOWLIST or "<empty>"
    return f"Host '{host}' is not allowed by EGRESS_ALLOWLIST ({allowlist})"


# ---------------- Runtime helpers ----------------
@dataclass
class RuntimeContext:
    request: Request
    user: UserInfo
    route_label: str
    start_ns: int
    tenant_id: str
    subject: str

    @classmethod
    def create(cls, request: Request, user: UserInfo, route_label: str) -> RuntimeContext:
        tenant_id = getattr(request.state, "tenant_id", None) or "global"
        subject = getattr(user, "sub", None)
        if not subject:
            subject = getattr(user, "username", None) or getattr(user, "email", None) or "anonymous"
        return cls(
            request=request,
            user=user,
            route_label=route_label,
            start_ns=time.monotonic_ns(),
            tenant_id=tenant_id,
            subject=str(subject),
        )

    @property
    def rate_limit_key(self) -> str:
        return f"rl:{self.tenant_id}:{self.subject}:{self.route_label}"

    def emit_metrics(self, status_code: int, provider_label: str = "n/a", instance_label: str = "n/a") -> int:
        latency_ms = int((time.monotonic_ns() - self.start_ns) / 1_000_000)
        status_class = (
            "2xx"
            if 200 <= status_code < 300
            else "3xx"
            if 300 <= status_code < 400
            else "4xx"
            if 400 <= status_code < 500
            else "5xx"
        )
        if MODEL_RUNTIME_COUNTER is not None:  # pragma: no cover
            with suppress(Exception):
                MODEL_RUNTIME_COUNTER.labels(self.route_label, provider_label, instance_label, status_class).inc()
        if MODEL_RUNTIME_HISTOGRAM is not None:  # pragma: no cover
            with suppress(Exception):
                MODEL_RUNTIME_HISTOGRAM.labels(self.route_label, provider_label, instance_label, status_class).observe(
                    latency_ms
                )
        return latency_ms

    def check_rate_limit(self) -> JSONResponse | None:
        if _rate_limit_check is None:
            return None
        try:
            result = _rate_limit_check(
                self.rate_limit_key, limit=settings.RATE_LIMIT_DEFAULT_LIMIT, window=settings.RATE_LIMIT_DEFAULT_WINDOW
            )
        except Exception:
            return None
        if getattr(result, "allowed", True):
            return None
        retry_after = getattr(result, "reset_seconds", None)
        headers: dict[str, str] = {}
        extra: dict[str, Any] = {}
        if retry_after is not None:
            headers["Retry-After"] = str(retry_after)
            extra["retry_after"] = retry_after
        self.emit_metrics(status.HTTP_429_TOO_MANY_REQUESTS)
        return problem_response(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "rate limit exceeded",
            detail="Too Many Requests",
            extra=extra or None,
            headers=headers or None,
            request=self.request,
        )


def _resolve_runtime_targets(
    ctx: RuntimeContext,
    requested_model: str | None,
    *,
    scope: str = "chat",
) -> tuple[str | None, str | None, dict[str, Any] | None, Any | None]:
    resolved_model = requested_model or None
    default_source: str | None = None
    if not resolved_model:
        with suppress(Exception):
            tenant_default = models_repo.get_default(scope, tenant_id=ctx.tenant_id)
            if tenant_default and tenant_default.get("name"):
                resolved_model = tenant_default.get("name")
                default_source = "tenant"
    if not resolved_model:
        with suppress(Exception):
            global_default = models_repo.get_default(scope, tenant_id=None)
            if global_default and global_default.get("name"):
                resolved_model = global_default.get("name")
                default_source = "global"
    
    # Use DMR (Default Model Resolver) instead of direct settings access
    if not resolved_model:
        with suppress(Exception):
            from src.services.default_model_resolver import DefaultModelResolver
            
            dmr = DefaultModelResolver()
            dmr_result = dmr.get_default_model(
                tenant_id=ctx.tenant_id if ctx.tenant_id != "global" else None,
                scope="tenant" if ctx.tenant_id and ctx.tenant_id != "global" else "global"
            )
            if dmr_result:
                resolved_model = dmr_result.get("model_id")
                source = dmr_result.get("source", "unknown")
                default_source = f"dmr-{source}"
    
    if not resolved_model and settings.DEMO_MODE:
        resolved_model = "demo-echo"
        default_source = "demo"

    instances: list[dict[str, Any]] = []
    with suppress(Exception):
        instances = models_repo.list_instances() or []

    target_tenant = None if ctx.tenant_id in (None, "global") else ctx.tenant_id

    accessible: list[dict[str, Any]] = []
    for inst in instances:
        if inst.get("enabled") is False:
            continue
        inst_tenant = inst.get("tenant_id")
        if target_tenant is None:
            if inst_tenant not in (None, "global"):
                continue
        elif inst_tenant not in (None, target_tenant):
            continue
        accessible.append(inst)

    if target_tenant is not None:
        accessible.sort(
            key=lambda inst: (
                0 if inst.get("tenant_id") == target_tenant else 1,
                inst.get("name") or "",
                inst.get("id") or "",
            )
        )

    instance: dict[str, Any] | None = None
    search_pool = accessible or []
    if resolved_model:
        for inst in search_pool:
            if inst.get("name") == resolved_model or inst.get("id") == resolved_model:
                instance = inst
                break
        if not instance:
            for inst in search_pool:
                if inst.get("model_id") == resolved_model:
                    instance = inst
                    break

    provider_internal = None
    if instance:
        provider_id = instance.get("provider_id")
        if provider_id:
            with suppress(Exception):
                provider_internal = models_repo.get_provider_internal(provider_id)

    return resolved_model, default_source, instance, provider_internal


def _build_trace_meta(
    ctx: RuntimeContext,
    *,
    resolved_model: str | None,
    instance_id: str,
    provider_internal: Any,
    default_source: str | None,
) -> dict[str, Any]:
    return {
        "tenant": ctx.tenant_id,
        "subject": ctx.subject,
        "model": resolved_model,
        "instance_id": instance_id,
        "provider_id": getattr(provider_internal, "id", None),
        "provider_type": getattr(provider_internal, "type", None),
        "default_source": default_source,
    }


def _build_upstream_headers(provider_internal: Any, *, metadata: dict[str, Any] | None = None) -> dict[str, str]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    api_key = getattr(provider_internal, "api_key", None)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    cfg = getattr(provider_internal, "config", None)
    cfg_headers = None
    if isinstance(cfg, dict):
        cfg_headers = cfg.get("headers")
    elif cfg is not None:
        with suppress(Exception):
            cfg_headers = cfg.get("headers")  # type: ignore[assignment]
    if isinstance(cfg_headers, dict):
        for key, value in cfg_headers.items():
            if value:
                headers[str(key)] = str(value)
    if metadata and isinstance(metadata, dict) and metadata.get("run_id"):
        headers["X-Run-Id"] = str(metadata["run_id"])
    return headers


# NOTE: ModelInfo, CompletionRequest, CompletionResponse, Usage, EmbeddingRequest,
# EmbeddingVector, EmbeddingResponse, ChatRequest now imported from schemas.models
# (Legacy definitions removed - see schemas/models.py for canonical versions)


# ---------------- Adapters (lazy) ----------------
def _adapter():
    """
    Try importing the LLM adapter module.
    Expected optional callables:
        - list_models() -> List[dict or ModelInfo-like]
        - complete(prompt, model, temperature, max_tokens, metadata, user) -> dict
    """
    with suppress(Exception):
        import importlib

        return importlib.import_module("src.adapters.llm")
    return None


def _fallback_models() -> list[ModelInfo]:
    # Use DMR to get default model instead of direct settings access
    default = "demo-echo"  # Safe fallback
    with suppress(Exception):
        from src.services.default_model_resolver import DefaultModelResolver
        
        dmr = DefaultModelResolver()
        dmr_result = dmr.get_default_model(tenant_id=None, scope="global")
        if dmr_result and dmr_result.get("model_id"):
            default = dmr_result["model_id"]
    
    provider = settings.LLM_PROVIDER or "demo"
    return [
        ModelInfo(
            name=default,
            provider=provider,
            context_window=4096 if provider == "demo" else None,
            modalities=["text"],
            description="Demo echo model (no external calls)"
            if provider == "demo"
            else f"{provider} model (adapter not implemented yet)",
            enabled=True,
        )
    ]


# ---------------- Routes ----------------
@router.get(
    "",
    summary="List available models",
    description=(
        "Return a paginated list of available models exposed by the platform. The list is discovered from LLM adapters when present and falls back to a deterministic demo model when adapters are missing. "
        "Each item contains model metadata such as name, provider, context window, supported modalities, and a short description. The endpoint supports `ETag` conditional requests and pagination via `page_size` and `page_token`."
    ),
)
async def list_models(
    request: Request,
    response: Response,
    page_size: int = 50,
    page_token: str | None = None,
    user: UserInfo = Depends(get_current_user),
):
    """Discover and return models the platform can use.

    Useful for UIs and clients that want to present available model options and their capabilities before making inference calls.
    """
    mod = _adapter()
    items: list[ModelInfo]
    if mod and hasattr(mod, "list_models"):
        with suppress(Exception):
            raw = mod.list_models()  # type: ignore[attr-defined]
            out: list[ModelInfo] = []
            for m in raw or []:
                if isinstance(m, ModelInfo):
                    out.append(m)
                elif isinstance(m, dict):
                    out.append(ModelInfo(**m))
            items = out or _fallback_models()
    else:
        items = _fallback_models()

    # Pagination
    page_items, next_token = make_page([i.model_dump() for i in items], page_size=page_size, page_token=page_token)

    # ETag support
    etag = compute_etag(page_items)
    inm = request.headers.get("if-none-match")
    if inm and inm == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag, "Vary": "Authorization"})
    response.headers["ETag"] = etag
    response.headers.setdefault("Vary", "Authorization")

    # Provenance
    meta = {}
    with suppress(Exception):
        meta["user"] = getattr(user, "sub", None) or getattr(user, "username", None) or getattr(user, "email", None)
    record_provenance(
        actor="api",
        action="model.list",
        resource="/v1/models",
        input={"page_size": page_size, "page_token": page_token},
        output={"count": len(page_items)},
        meta=meta,
    )
    return {"items": page_items, "next_page_token": next_token}


# NOTE: /catalog path removed — /v1/models is the canonical model listing


@router.post(
    "/completions",
    response_model=CompletionResponse,
    summary="Invoke a configured completion model",
    description=(
        "Tenant-aware completion endpoint that resolves defaults, enforces rate limits, "
        "and proxies to the configured provider (OpenAI-compatible or custom templates)."
    ),
)
async def completions(
    req: CompletionRequest,
    request: Request,
    user: UserInfo = Depends(get_current_user),
) -> CompletionResponse:
    import json as _json
    import logging
    from urllib.parse import urljoin, urlparse

    import httpx
    import jmespath
    from jinja2 import Template

    logger = logging.getLogger("models.completions")

    logger = logging.getLogger("models.completions")
    ctx = RuntimeContext.create(request, user, "completions")

    try:  # pragma: no cover
        logger.info(
            "model.completions.start",
            extra={
                "details": {
                    "tenant_id": ctx.tenant_id,
                    "subject": ctx.subject,
                    "has_model_param": bool(req.model),
                }
            },
        )
    except Exception:
        pass

    rl_response = ctx.check_rate_limit()
    if rl_response is not None:
        return rl_response

    resolved_model, default_source, instance, provider_internal = _resolve_runtime_targets(ctx, req.model)
    if not resolved_model:
        ctx.emit_metrics(status.HTTP_404_NOT_FOUND)
        return problem_response(
            status.HTTP_404_NOT_FOUND,
            "model not found",
            detail=f"No default model available for tenant '{ctx.tenant_id}'",
            request=request,
        )

    provider_label = getattr(provider_internal, "id", None) or "n/a"
    instance_id = instance.get("id") if instance else resolved_model or "n/a"

    if (not instance or not provider_internal) and resolved_model == "demo-echo" and settings.DEMO_MODE:
        output_text = f"(demo) {req.prompt}"
        usage = Usage()
        latency_ms = ctx.emit_metrics(status.HTTP_200_OK, "demo", "demo")
        ev = record_provenance(
            actor="api",
            action="model.complete",
            resource="/v1/models/completions",
            input=req.model_dump(),
            output={"output": output_text},
            meta={"demo": True, "model": resolved_model},
            success=True,
            duration_ms=latency_ms,
        )
        return CompletionResponse(
            model=resolved_model,
            output=output_text,
            usage=usage,
            latency_ms=latency_ms,
            trace_id=ev.trace_id,
            event_id=ev.event_id,
        )

    if not instance or not provider_internal:
        ctx.emit_metrics(status.HTTP_404_NOT_FOUND, provider_label, instance_id)
        attempted = resolved_model or req.model or "<unspecified>"
        return problem_response(
            status.HTTP_404_NOT_FOUND,
            "model not found",
            detail=f"model '{attempted}' not available for tenant '{ctx.tenant_id}'",
            request=request,
        )

    provider_type = getattr(provider_internal, "type", None)
    base_url = _resolve_provider_base_url(provider_internal)
    ollama_provider = _is_ollama_provider(provider_internal)
    if not base_url:
        ctx.emit_metrics(status.HTTP_500_INTERNAL_SERVER_ERROR, provider_label, instance_id)
        return problem_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "provider missing base_url",
            detail="Provider misconfiguration",
            request=request,
        )

    if not _egress_allowed(base_url):
        ctx.emit_metrics(status.HTTP_403_FORBIDDEN, provider_label, instance_id)
        host_port = (urlparse(base_url).netloc or base_url).lower() or base_url
        return problem_response(
            status.HTTP_403_FORBIDDEN,
            "egress not allowed",
            detail=_egress_violation_detail(host_port or base_url),
            extra={"host": host_port or base_url, "allowlist": settings.EGRESS_ALLOWLIST},
            request=request,
        )

    try:  # pragma: no cover
        with httpx.Client(timeout=1.0) as client:
            candidate = base_url.rstrip("/") + "/models"
            try:
                client.get(candidate)
            except Exception:
                candidate = base_url.rstrip("/") + "/health"
                with suppress(Exception):
                    client.get(candidate)
    except Exception:
        pass

    timeout = _timeout_for_provider(provider_internal)
    headers = _build_upstream_headers(
        provider_internal, metadata=req.metadata if isinstance(req.metadata, dict) else None
    )

    request_payload: dict[str, Any] = {}
    upstream_url = ""
    usage = Usage()
    output_text = ""

    trace_meta = _build_trace_meta(
        ctx,
        resolved_model=resolved_model,
        instance_id=instance_id,
        provider_internal=provider_internal,
        default_source=default_source,
    )

    upstream_model_id = _resolve_upstream_model_id(provider_internal, resolved_model, req.model, instance)
    mapped_from = None
    try:
        mapped_from = (instance or {}).get("model_id") or resolved_model
    except Exception:
        mapped_from = resolved_model
    if ollama_provider and upstream_model_id and upstream_model_id != mapped_from:
        with suppress(Exception):
            logger.info(
                "model.completions.ollama_model_mapped",
                extra={"details": {**trace_meta, "logical_model": mapped_from, "mapped_model": upstream_model_id}},
            )

    def metrics_problem(
        status_code: int,
        title: str,
        detail: str,
        extra: dict[str, Any] | None = None,
        headers_override: dict[str, str] | None = None,
    ):
        ctx.emit_metrics(status_code, provider_label, instance_id)
        if ollama_provider:
            with suppress(Exception):
                logger.warning(
                    "model.completions.ollama_error",
                    extra={
                        "details": {
                            **trace_meta,
                            "status": status_code,
                            "title": title,
                            "detail": detail,
                            "extra": extra,
                        }
                    },
                )
        return problem_response(
            status_code, title, detail=detail, extra=extra, headers=headers_override, request=request
        )

    try:
        if provider_type == "openai_compatible":
            upstream_url = base_url.rstrip("/") + "/chat/completions"
            request_payload = {
                "model": upstream_model_id
                or (instance.get("model_id") if instance else resolved_model)
                or resolved_model,
                "messages": [{"role": "user", "content": req.prompt}],
            }
            if req.temperature is not None:
                request_payload["temperature"] = req.temperature
            if req.max_tokens is not None:
                request_payload["max_tokens"] = req.max_tokens
        elif provider_type == "custom":
            cfg = provider_internal.config or {}
            path = (cfg.get("paths", {}) or {}).get("completions") if isinstance(cfg.get("paths"), dict) else None
            if not path:
                return metrics_problem(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "custom provider missing path",
                    "config.paths.completions missing",
                )
            upstream_url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
            tmpl_src = (
                (cfg.get("request_templates", {}) or {}).get("completions")
                if isinstance(cfg.get("request_templates"), dict)
                else None
            )
            if not tmpl_src:
                return metrics_problem(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "custom provider missing template",
                    "request_templates.completions missing",
                )
            try:
                template = Template(tmpl_src)
                request_payload = _json.loads(
                    template.render(
                        prompt=req.prompt,
                        model_id=upstream_model_id
                        or (instance.get("model_id") if instance else resolved_model)
                        or resolved_model,
                        temperature=req.temperature,
                        max_tokens=req.max_tokens,
                        metadata=req.metadata,
                        tenant_id=ctx.tenant_id,
                        trace_id=_resolve_trace_id(request),
                    )
                )
            except Exception as te:
                return metrics_problem(status.HTTP_500_INTERNAL_SERVER_ERROR, "template render failed", str(te))
        else:
            return metrics_problem(
                status.HTTP_501_NOT_IMPLEMENTED,
                "provider type unsupported",
                f"Unsupported provider type '{provider_type}'",
            )

        async with httpx.AsyncClient(timeout=timeout) as client:
            attempt = 0
            max_attempts = 2 if ollama_provider else 1
            data = None
            while attempt < max_attempts:
                attempt += 1
                try:
                    start_time = time.perf_counter()
                    resp = await client.post(upstream_url, json=request_payload, headers=headers)
                    elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                    _debug_log_provider_call(
                        logger,
                        event="model.completions.provider_call",
                        trace_meta=trace_meta,
                        base_url=base_url,
                        resolved_model=resolved_model,
                        mapped_model=upstream_model_id,
                        elapsed_ms=elapsed_ms,
                        status_code=resp.status_code,
                        attempt=attempt,
                        extra={"url": upstream_url, "provider": provider_label},
                    )
                    if ollama_provider:
                        with suppress(Exception):
                            logger.info(
                                "model.completions.ollama_response",
                                extra={
                                    "details": {
                                        **trace_meta,
                                        "attempt": attempt,
                                        "status": resp.status_code,
                                        "elapsed_ms": elapsed_ms,
                                        "url": upstream_url,
                                    }
                                },
                            )
                except (httpx.ReadTimeout, httpx.WriteTimeout, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
                    elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                    error_detail = str(exc)
                    _debug_log_provider_call(
                        logger,
                        event="model.completions.provider_timeout",
                        trace_meta=trace_meta,
                        base_url=base_url,
                        resolved_model=resolved_model,
                        mapped_model=upstream_model_id,
                        elapsed_ms=elapsed_ms,
                        error=error_detail,
                        attempt=attempt,
                        extra={"url": upstream_url, "provider": provider_label},
                    )
                    if attempt < max_attempts:
                        continue
                    if ollama_provider:
                        with suppress(Exception):
                            logger.warning(
                                "model.completions.ollama_timeout",
                                extra={
                                    "details": {
                                        **trace_meta,
                                        "attempt": attempt,
                                        "url": upstream_url,
                                        "error": error_detail,
                                    }
                                },
                            )
                    try:  # pragma: no cover
                        logger.error(
                            "model.completions.timeout", extra={"details": {"error": error_detail, **trace_meta}}
                        )
                    except Exception:
                        pass
                    return metrics_problem(
                        status.HTTP_504_GATEWAY_TIMEOUT,
                        "upstream timeout",
                        error_detail,
                        extra={"error": error_detail},
                    )
                except httpx.RequestError as exc:
                    elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                    error_detail = str(exc)
                    _debug_log_provider_call(
                        logger,
                        event="model.completions.provider_error",
                        trace_meta=trace_meta,
                        base_url=base_url,
                        resolved_model=resolved_model,
                        mapped_model=upstream_model_id,
                        elapsed_ms=elapsed_ms,
                        error=error_detail,
                        attempt=attempt,
                        extra={"url": upstream_url, "provider": provider_label},
                    )
                    if attempt < max_attempts:
                        continue
                    if ollama_provider:
                        with suppress(Exception):
                            logger.warning(
                                "model.completions.ollama_request_error",
                                extra={
                                    "details": {
                                        **trace_meta,
                                        "attempt": attempt,
                                        "url": upstream_url,
                                        "error": error_detail,
                                    }
                                },
                            )
                    try:  # pragma: no cover
                        logger.error(
                            "model.completions.error", extra={"details": {"error": error_detail, **trace_meta}}
                        )
                    except Exception:
                        pass
                    return metrics_problem(
                        status.HTTP_502_BAD_GATEWAY,
                        "upstream connection error",
                        error_detail,
                        extra={"error": error_detail},
                    )

                if resp.status_code >= 400:
                    try:
                        body = resp.json()
                    except Exception:
                        body = {"raw": resp.text[:500]}
                    if resp.status_code == status.HTTP_404_NOT_FOUND:
                        return metrics_problem(
                            status.HTTP_404_NOT_FOUND,
                            "model not present in provider",
                            "model not configured for provider",
                            extra={
                                "url": upstream_url,
                                "resolved_model": resolved_model,
                                "mapped_model": upstream_model_id,
                            },
                        )
                    if status.HTTP_400_BAD_REQUEST <= resp.status_code < status.HTTP_500_INTERNAL_SERVER_ERROR:
                        return metrics_problem(
                            status.HTTP_424_FAILED_DEPENDENCY,
                            "upstream request failed",
                            "Provider returned error",
                            extra={
                                "status": resp.status_code,
                                "url": upstream_url,
                                "body": body if request.headers.get("X-Passthrough-Response") else None,
                            },
                        )
                    return metrics_problem(
                        status.HTTP_502_BAD_GATEWAY,
                        "provider request failed",
                        "Upstream provider error",
                        extra={"status": resp.status_code, "url": upstream_url},
                    )

                try:
                    data = resp.json()
                except Exception:
                    return metrics_problem(
                        status.HTTP_502_BAD_GATEWAY,
                        "provider request failed",
                        "Non-JSON upstream response",
                        extra={"snippet": resp.text[:200]},
                    )

                if provider_type == "openai_compatible":
                    choices = data.get("choices")
                    if not isinstance(choices, list) or not choices:
                        if attempt < max_attempts:
                            continue
                        return metrics_problem(
                            status.HTTP_424_FAILED_DEPENDENCY,
                            "upstream returned no choices",
                            f"Provider returned empty choices (provider={provider_internal.id}, instance={instance_id})",
                            extra={"url": upstream_url},
                        )
                    first = choices[0] or {}
                    msg = first.get("message") or {}
                    output_text = msg.get("content") or first.get("text") or ""
                    if not output_text:
                        return metrics_problem(
                            status.HTTP_424_FAILED_DEPENDENCY,
                            "upstream choice missing content",
                            "First choice lacks message.content/text",
                            extra={"url": upstream_url},
                        )
                    usage_data = data.get("usage") or {}
                    if isinstance(usage_data, dict):
                        usage = Usage(
                            prompt_tokens=int(usage_data.get("prompt_tokens") or 0),
                            completion_tokens=int(usage_data.get("completion_tokens") or 0),
                            total_tokens=int(usage_data.get("total_tokens") or 0),
                        )
                else:
                    cfg = provider_internal.config or {}
                    extract_cfg = (
                        (cfg.get("response_extract", {}) or {}).get("completions")
                        if isinstance(cfg.get("response_extract"), dict)
                        else None
                    )
                    if not extract_cfg or not isinstance(extract_cfg, dict):
                        return metrics_problem(
                            status.HTTP_500_INTERNAL_SERVER_ERROR,
                            "missing response extractor",
                            "response_extract.completions missing",
                        )
                    expr_output = extract_cfg.get("output")
                    if not expr_output:
                        return metrics_problem(
                            status.HTTP_500_INTERNAL_SERVER_ERROR,
                            "missing output extractor",
                            "response_extract.completions.output missing",
                        )
                    try:
                        output_text = jmespath.search(expr_output, data) or ""
                    except Exception as je:
                        return metrics_problem(
                            status.HTTP_500_INTERNAL_SERVER_ERROR, "output extraction failed", str(je)
                        )
                    if not output_text:
                        return metrics_problem(
                            status.HTTP_424_FAILED_DEPENDENCY,
                            "upstream returned no output",
                            "Extractor produced empty output",
                            extra={"expr": expr_output},
                        )
                    expr_usage = extract_cfg.get("usage")
                    if expr_usage:
                        with suppress(Exception):
                            u = jmespath.search(expr_usage, data) or {}
                            if isinstance(u, dict):
                                usage = Usage(
                                    prompt_tokens=int(u.get("prompt_tokens") or 0),
                                    completion_tokens=int(u.get("completion_tokens") or 0),
                                    total_tokens=int(u.get("total_tokens") or 0),
                                )
                break
    except Exception as exc:
        error_detail = str(exc)
        return metrics_problem(
            status.HTTP_502_BAD_GATEWAY,
            "provider request failed",
            "Unexpected provider error",
            extra={"error": error_detail},
        )

    latency_ms = ctx.emit_metrics(status.HTTP_200_OK, provider_label, instance_id)

    ev = record_provenance(
        actor="api",
        action="model.complete",
        resource="/v1/models/completions",
        input={"prompt": "<redacted>", **{k: v for k, v in req.model_dump().items() if k != "prompt"}},
        output={"len": len(output_text)},
        meta={**trace_meta, "latency_ms": latency_ms},
        success=True,
        duration_ms=latency_ms,
    )

    try:  # pragma: no cover
        logger.info(
            "model.completions.end",
            extra={"details": {**trace_meta, "latency_ms": latency_ms, "status_code": status.HTTP_200_OK}},
        )
    except Exception:
        pass

    return CompletionResponse(
        model=resolved_model,
        output=output_text,
        usage=usage,
        latency_ms=latency_ms,
        trace_id=ev.trace_id,
        event_id=ev.event_id,
    )


completions.__dict__.setdefault("__tags__", ["Completions"])


# ---------------- Utilities: embeddings & chat


# NOTE: EmbeddingRequest, EmbeddingVector, EmbeddingResponse already imported from schemas.models


@router.post(
    "/embeddings",
    response_model=EmbeddingResponse,
    summary="Create embeddings",
    description=(
        "Provider-aware embeddings endpoint supporting OpenAI-compatible and custom providers with Jinja+JMESPath mappings."
    ),
)
async def embeddings(
    req: EmbeddingRequest,
    request: Request,
    user: UserInfo = Depends(get_current_user),
) -> EmbeddingResponse:
    import json as _json
    import logging
    from urllib.parse import urljoin, urlparse

    import httpx
    import jmespath
    from jinja2 import Template

    logger = logging.getLogger("models.embeddings")
    ctx = RuntimeContext.create(request, user, "embeddings")

    try:  # pragma: no cover
        logger.info(
            "model.embeddings.start",
            extra={"details": {"tenant_id": ctx.tenant_id, "subject": ctx.subject, "has_model_param": bool(req.model)}},
        )
    except Exception:
        pass

    rl_response = ctx.check_rate_limit()
    if rl_response is not None:
        return rl_response

    resolved_model, default_source, instance, provider_internal = _resolve_runtime_targets(
        ctx, req.model, scope="embeddings"
    )
    if not resolved_model:
        ctx.emit_metrics(status.HTTP_404_NOT_FOUND)
        return problem_response(
            status.HTTP_404_NOT_FOUND,
            "model not found",
            detail=f"No default model available for tenant '{ctx.tenant_id}'",
            request=request,
        )

    provider_label = getattr(provider_internal, "id", None) or "n/a"
    instance_id = instance.get("id") if instance else resolved_model or "n/a"

    if (not instance or not provider_internal) and resolved_model == "demo-echo" and settings.DEMO_MODE:
        embedding = EmbeddingVector(index=0, embedding=[], model=resolved_model)
        latency_ms = ctx.emit_metrics(status.HTTP_200_OK, "demo", "demo")
        ev = record_provenance(
            actor="api",
            action="model.embeddings",
            resource="/v1/models/embeddings",
            input={"len": len(req.input)},
            output={"dim": len(embedding.embedding)},
            meta={"demo": True, "model": resolved_model},
            success=True,
            duration_ms=latency_ms,
        )
        return EmbeddingResponse(
            data=[embedding], latency_ms=latency_ms, trace_id=ev.trace_id, event_id=ev.event_id, usage=None
        )

    if not instance or not provider_internal:
        ctx.emit_metrics(status.HTTP_404_NOT_FOUND, provider_label, instance_id)
        attempted = resolved_model or req.model or "<unspecified>"
        return problem_response(
            status.HTTP_404_NOT_FOUND,
            "model not found",
            detail=f"model '{attempted}' not available for tenant '{ctx.tenant_id}'",
            request=request,
        )

    provider_type = getattr(provider_internal, "type", None)
    base_url = _resolve_provider_base_url(provider_internal)
    ollama_provider = _is_ollama_provider(provider_internal)
    if not base_url:
        ctx.emit_metrics(status.HTTP_500_INTERNAL_SERVER_ERROR, provider_label, instance_id)
        return problem_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "provider missing base_url",
            detail="Provider misconfiguration",
            request=request,
        )

    if not _egress_allowed(base_url):
        ctx.emit_metrics(status.HTTP_403_FORBIDDEN, provider_label, instance_id)
        host_port = (urlparse(base_url).netloc or base_url).lower() or base_url
        return problem_response(
            status.HTTP_403_FORBIDDEN,
            "egress not allowed",
            detail=_egress_violation_detail(host_port or base_url),
            extra={"host": host_port or base_url, "allowlist": settings.EGRESS_ALLOWLIST},
            request=request,
        )

    try:  # pragma: no cover
        with httpx.Client(timeout=1.0) as client:
            candidate = base_url.rstrip("/") + "/models"
            try:
                client.get(candidate)
            except Exception:
                candidate = base_url.rstrip("/") + "/health"
                with suppress(Exception):
                    client.get(candidate)
    except Exception:
        pass

    timeout = _timeout_for_provider(provider_internal)
    headers = _build_upstream_headers(provider_internal)

    request_payload: dict[str, Any] = {}
    upstream_url = ""
    usage: Usage | None = None

    trace_meta = _build_trace_meta(
        ctx,
        resolved_model=resolved_model,
        instance_id=instance_id,
        provider_internal=provider_internal,
        default_source=default_source,
    )

    upstream_model_id = _resolve_upstream_model_id(provider_internal, resolved_model, req.model, instance)
    mapped_from = None
    try:
        mapped_from = (instance or {}).get("model_id") or resolved_model
    except Exception:
        mapped_from = resolved_model
    if ollama_provider and upstream_model_id and upstream_model_id != mapped_from:
        with suppress(Exception):
            logger.info(
                "model.embeddings.ollama_model_mapped",
                extra={"details": {**trace_meta, "logical_model": mapped_from, "mapped_model": upstream_model_id}},
            )

    def metrics_problem(status_code: int, title: str, detail: str, extra: dict[str, Any] | None = None):
        ctx.emit_metrics(status_code, provider_label, instance_id)
        if ollama_provider:
            with suppress(Exception):
                logger.warning(
                    "model.embeddings.ollama_error",
                    extra={
                        "details": {
                            **trace_meta,
                            "status": status_code,
                            "title": title,
                            "detail": detail,
                            "extra": extra,
                        }
                    },
                )
        return problem_response(status_code, title, detail=detail, extra=extra, request=request)

    try:
        cfg = provider_internal.config or {}
        paths_cfg = cfg.get("paths") if isinstance(cfg.get("paths"), dict) else {}
        embeddings_path = None
        if isinstance(paths_cfg, dict):
            embeddings_path = paths_cfg.get("embeddings") or paths_cfg.get("chat_completions")

        if provider_type == "openai_compatible":
            base_path = embeddings_path or "/v1/embeddings"
            upstream_url = urljoin(base_url.rstrip("/") + "/", base_path.lstrip("/"))
            request_payload = {
                "model": upstream_model_id
                or (instance.get("model_id") if instance else resolved_model)
                or resolved_model,
                "input": req.input,
            }
        elif provider_type == "custom":
            base_path = embeddings_path or "/v1/embeddings"
            upstream_url = urljoin(base_url.rstrip("/") + "/", base_path.lstrip("/"))
            tmpl_src = (
                (cfg.get("request_templates", {}) or {}).get("embeddings")
                if isinstance(cfg.get("request_templates"), dict)
                else None
            )
            if not tmpl_src:
                return metrics_problem(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "custom provider missing template",
                    "request_templates.embeddings missing",
                )
            try:
                template = Template(tmpl_src)
                request_payload = _json.loads(
                    template.render(
                        input=req.input,
                        model_id=upstream_model_id
                        or (instance.get("model_id") if instance else resolved_model)
                        or resolved_model,
                        tenant_id=ctx.tenant_id,
                        trace_id=_resolve_trace_id(request),
                    )
                )
            except Exception as te:
                return metrics_problem(status.HTTP_500_INTERNAL_SERVER_ERROR, "template render failed", str(te))
        else:
            return metrics_problem(
                status.HTTP_501_NOT_IMPLEMENTED,
                "provider type unsupported",
                f"Unsupported provider type '{provider_type}'",
            )

        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                start_time = time.perf_counter()
                resp = await client.post(upstream_url, json=request_payload, headers=headers)
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                _debug_log_provider_call(
                    logger,
                    event="model.embeddings.provider_call",
                    trace_meta=trace_meta,
                    base_url=base_url,
                    resolved_model=resolved_model,
                    mapped_model=upstream_model_id,
                    elapsed_ms=elapsed_ms,
                    status_code=resp.status_code,
                    extra={"url": upstream_url, "provider": provider_label},
                )
                if ollama_provider:
                    with suppress(Exception):
                        logger.info(
                            "model.embeddings.ollama_response",
                            extra={
                                "details": {
                                    **trace_meta,
                                    "status": resp.status_code,
                                    "latency_ms": elapsed_ms,
                                    "url": upstream_url,
                                }
                            },
                        )
            except (httpx.ReadTimeout, httpx.WriteTimeout, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                error_detail = str(exc)
                _debug_log_provider_call(
                    logger,
                    event="model.embeddings.provider_timeout",
                    trace_meta=trace_meta,
                    base_url=base_url,
                    resolved_model=resolved_model,
                    mapped_model=upstream_model_id,
                    elapsed_ms=elapsed_ms,
                    error=error_detail,
                    extra={"url": upstream_url, "provider": provider_label},
                )
                try:  # pragma: no cover
                    logger.error("model.embeddings.timeout", extra={"details": {"error": error_detail, **trace_meta}})
                except Exception:
                    pass
                return metrics_problem(
                    status.HTTP_504_GATEWAY_TIMEOUT,
                    "upstream timeout",
                    error_detail,
                    extra={"error": error_detail},
                )
            except httpx.RequestError as exc:
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                error_detail = str(exc)
                _debug_log_provider_call(
                    logger,
                    event="model.embeddings.provider_error",
                    trace_meta=trace_meta,
                    base_url=base_url,
                    resolved_model=resolved_model,
                    mapped_model=upstream_model_id,
                    elapsed_ms=elapsed_ms,
                    error=error_detail,
                    extra={"url": upstream_url, "provider": provider_label},
                )
                try:  # pragma: no cover
                    logger.error("model.embeddings.error", extra={"details": {"error": error_detail, **trace_meta}})
                except Exception:
                    pass
                return metrics_problem(
                    status.HTTP_502_BAD_GATEWAY,
                    "upstream connection error",
                    error_detail,
                    extra={"error": error_detail},
                )

        if resp.status_code >= 400:
            try:
                body = resp.json()
            except Exception:
                body = {"raw": resp.text[:500]}
            if resp.status_code == status.HTTP_404_NOT_FOUND:
                return metrics_problem(
                    status.HTTP_404_NOT_FOUND,
                    "model not present in provider",
                    "model not configured for provider",
                    extra={
                        "url": upstream_url,
                        "resolved_model": resolved_model,
                        "mapped_model": upstream_model_id,
                    },
                )
            if status.HTTP_400_BAD_REQUEST <= resp.status_code < status.HTTP_500_INTERNAL_SERVER_ERROR:
                return metrics_problem(
                    status.HTTP_424_FAILED_DEPENDENCY,
                    "upstream request failed",
                    "Provider returned error",
                    extra={"status": resp.status_code, "url": upstream_url, "body": body},
                )
            return metrics_problem(
                status.HTTP_502_BAD_GATEWAY,
                "provider request failed",
                "Upstream provider error",
                extra={"status": resp.status_code, "url": upstream_url},
            )

        try:
            data = resp.json()
        except Exception:
            return metrics_problem(
                status.HTTP_502_BAD_GATEWAY,
                "provider request failed",
                "Non-JSON upstream response",
                extra={"snippet": resp.text[:200]},
            )

        embedding_values: list[float] = []
        if provider_type == "openai_compatible":
            data_array = data.get("data")
            if not isinstance(data_array, list) or not data_array:
                return metrics_problem(
                    status.HTTP_424_FAILED_DEPENDENCY,
                    "upstream returned no embeddings",
                    "Provider returned empty embeddings list",
                    extra={"url": upstream_url},
                )
            first = data_array[0] or {}
            embedding_values = first.get("embedding") or []
            if not isinstance(embedding_values, list) or not embedding_values:
                return metrics_problem(
                    status.HTTP_424_FAILED_DEPENDENCY,
                    "embedding missing",
                    "Embedding vector missing in provider response",
                    extra={"url": upstream_url},
                )
            usage_data = data.get("usage")
            if isinstance(usage_data, dict):
                usage = Usage(
                    prompt_tokens=int(usage_data.get("prompt_tokens") or 0),
                    completion_tokens=int(usage_data.get("completion_tokens") or 0),
                    total_tokens=int(usage_data.get("total_tokens") or 0),
                )
        else:
            extract_cfg = (
                (cfg.get("response_extract", {}) or {}).get("embeddings")
                if isinstance(cfg.get("response_extract"), dict)
                else None
            )
            if not extract_cfg:
                extract_cfg = (
                    (cfg.get("response_extract", {}) or {}).get("embedding")
                    if isinstance(cfg.get("response_extract"), dict)
                    else None
                )
            if not extract_cfg:
                return metrics_problem(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "missing response extractor",
                    "response_extract.embeddings missing",
                )
            expr_embedding = None
            if isinstance(extract_cfg, dict):
                expr_embedding = extract_cfg.get("embedding") or extract_cfg.get("output")
            if not expr_embedding:
                return metrics_problem(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "missing embedding extractor",
                    "response_extract.embeddings.embedding missing",
                )
            try:
                embedding_values = jmespath.search(expr_embedding, data) or []
            except Exception as je:
                return metrics_problem(status.HTTP_500_INTERNAL_SERVER_ERROR, "embedding extraction failed", str(je))
            if not isinstance(embedding_values, list) or not embedding_values:
                return metrics_problem(
                    status.HTTP_424_FAILED_DEPENDENCY,
                    "upstream returned no embeddings",
                    "Extractor produced empty embeddings",
                    extra={"expr": expr_embedding},
                )
            if isinstance(extract_cfg, dict):
                expr_usage = extract_cfg.get("usage")
                if expr_usage:
                    with suppress(Exception):
                        u = jmespath.search(expr_usage, data) or {}
                        if isinstance(u, dict):
                            usage = Usage(
                                prompt_tokens=int(u.get("prompt_tokens") or 0),
                                completion_tokens=int(u.get("completion_tokens") or 0),
                                total_tokens=int(u.get("total_tokens") or 0),
                            )
    except Exception as exc:
        error_detail = str(exc)
        return metrics_problem(
            status.HTTP_502_BAD_GATEWAY,
            "provider request failed",
            "Unexpected provider error",
            extra={"error": error_detail},
        )

    latency_ms = ctx.emit_metrics(status.HTTP_200_OK, provider_label, instance_id)

    embedding = EmbeddingVector(index=0, embedding=[float(x) for x in embedding_values], model=resolved_model)
    ev = record_provenance(
        actor="api",
        action="model.embeddings",
        resource="/v1/models/embeddings",
        input={"len": len(req.input)},
        output={"dim": len(embedding.embedding)},
        meta={**trace_meta, "latency_ms": latency_ms},
        success=True,
        duration_ms=latency_ms,
    )

    try:  # pragma: no cover
        logger.info(
            "model.embeddings.end",
            extra={"details": {**trace_meta, "latency_ms": latency_ms, "status_code": status.HTTP_200_OK}},
        )
    except Exception:
        pass

    return EmbeddingResponse(
        data=[embedding], latency_ms=latency_ms, trace_id=ev.trace_id, event_id=ev.event_id, usage=usage
    )


# NOTE: ChatRequest already imported from schemas.models


@router.post(
    "/chat/completions",
    summary="Chat completions",
    description=(
        "Multi-turn chat completion endpoint. POST a `ChatRequest` containing an ordered list of `messages` (each message is an object with `role` and `content`) and an optional `model`. "
        "The adapter may return a streaming response or a structured chat response; in this lightweight API we return a single JSON payload with one or more choices. If the chat adapter is not available a demo assistant reply is returned."
    ),
)
async def chat_completions(req: ChatRequest, request: Request, user: UserInfo = Depends(get_current_user)):
    """Produce a chat-style completion given a sequence of messages.

    Messages should follow the typical `{role: "user|assistant|system", content: "..."}` convention. Use this endpoint for conversational assistants and multi-turn dialogues.
    """
    import json as _json
    import logging
    from urllib.parse import urljoin

    import httpx
    import jmespath
    from jinja2 import Template

    logger = logging.getLogger("models.chat")
    ctx = RuntimeContext.create(request, user, "chat.completions")

    try:  # pragma: no cover
        logger.info(
            "model.chat.start",
            extra={
                "details": {
                    "tenant_id": ctx.tenant_id,
                    "subject": ctx.subject,
                    "messages": len(req.messages),
                    "has_model_param": bool(req.model),
                }
            },
        )
    except Exception:
        pass

    rl_response = ctx.check_rate_limit()
    if rl_response is not None:
        return rl_response

    resolved_model, default_source, instance, provider_internal = _resolve_runtime_targets(ctx, req.model)
    if not resolved_model:
        ctx.emit_metrics(status.HTTP_404_NOT_FOUND)
        return problem_response(
            status.HTTP_404_NOT_FOUND,
            "model not found",
            detail=f"No default model available for tenant '{ctx.tenant_id}'",
            request=request,
        )

    provider_label = getattr(provider_internal, "id", None) or "n/a"
    instance_id = instance.get("id") if instance else resolved_model or "n/a"

    if (not instance or not provider_internal) and resolved_model == "demo-echo" and settings.DEMO_MODE:
        latency_ms = ctx.emit_metrics(status.HTTP_200_OK, "demo", "demo")
        payload = {
            "id": "demo",
            "choices": [
                {"message": {"role": "assistant", "content": "(demo)"}},
            ],
            "latency_ms": latency_ms,
        }
        return payload

    if not instance or not provider_internal:
        ctx.emit_metrics(status.HTTP_404_NOT_FOUND, provider_label, instance_id)
        attempted = resolved_model or req.model or "<unspecified>"
        return problem_response(
            status.HTTP_404_NOT_FOUND,
            "model not found",
            detail=f"model '{attempted}' not available for tenant '{ctx.tenant_id}'",
            request=request,
        )

    provider_type = getattr(provider_internal, "type", None)
    base_url = _resolve_provider_base_url(provider_internal)
    ollama_provider = _is_ollama_provider(provider_internal)
    if not base_url:
        ctx.emit_metrics(status.HTTP_500_INTERNAL_SERVER_ERROR, provider_label, instance_id)
        return problem_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "provider missing base_url",
            detail="Provider misconfiguration",
            request=request,
        )

    if not _egress_allowed(base_url):
        ctx.emit_metrics(status.HTTP_403_FORBIDDEN, provider_label, instance_id)
        host_port = (urlparse(base_url).netloc or base_url).lower() or base_url
        return problem_response(
            status.HTTP_403_FORBIDDEN,
            "egress not allowed",
            detail=_egress_violation_detail(host_port or base_url),
            extra={"host": host_port or base_url, "allowlist": settings.EGRESS_ALLOWLIST},
            request=request,
        )

    timeout = _timeout_for_provider(provider_internal)
    headers = _build_upstream_headers(provider_internal)

    request_payload: dict[str, Any] = {}
    response_payload: dict[str, Any] = {}
    upstream_url = ""
    usage = Usage()

    trace_meta = _build_trace_meta(
        ctx,
        resolved_model=resolved_model,
        instance_id=instance_id,
        provider_internal=provider_internal,
        default_source=default_source,
    )

    upstream_model_id = _resolve_upstream_model_id(provider_internal, resolved_model, req.model, instance)
    mapped_from = None
    try:
        mapped_from = (instance or {}).get("model_id") or resolved_model
    except Exception:
        mapped_from = resolved_model
    if ollama_provider and upstream_model_id and upstream_model_id != mapped_from:
        with suppress(Exception):
            logger.info(
                "model.chat.ollama_model_mapped",
                extra={"details": {**trace_meta, "logical_model": mapped_from, "mapped_model": upstream_model_id}},
            )

    def metrics_problem(status_code: int, title: str, detail: str, extra: dict[str, Any] | None = None):
        ctx.emit_metrics(status_code, provider_label, instance_id)
        if ollama_provider:
            with suppress(Exception):
                logger.warning(
                    "model.chat.ollama_error",
                    extra={
                        "details": {
                            **trace_meta,
                            "status": status_code,
                            "title": title,
                            "detail": detail,
                            "extra": extra,
                        }
                    },
                )
        return problem_response(status_code, title, detail=detail, extra=extra, request=request)

    try:
        if provider_type == "openai_compatible":
            path_segment = "/v1/chat/completions"
            paths_cfg: dict[str, Any] = {}
            try:
                cfg = getattr(provider_internal, "config", None)
                if isinstance(cfg, dict):
                    raw_paths = cfg.get("paths")
                    if isinstance(raw_paths, dict):
                        paths_cfg = raw_paths
            except Exception:
                paths_cfg = {}
            candidate_path = None
            if isinstance(paths_cfg, dict):
                candidate_path = (
                    paths_cfg.get("chat_completions") or paths_cfg.get("chat") or paths_cfg.get("completions")
                )
            if candidate_path and isinstance(candidate_path, str) and candidate_path.strip():
                candidate_path = candidate_path.strip()
                if candidate_path.startswith("http://") or candidate_path.startswith("https://"):
                    upstream_url = candidate_path.rstrip("/")
                else:
                    upstream_url = urljoin(base_url.rstrip("/") + "/", candidate_path.lstrip("/"))
            else:
                upstream_url = urljoin(base_url.rstrip("/") + "/", path_segment.lstrip("/"))
            request_payload = {
                "model": upstream_model_id
                or (instance.get("model_id") if instance else resolved_model)
                or resolved_model,
                "messages": req.messages,
            }
        elif provider_type == "custom":
            cfg = provider_internal.config or {}
            paths_cfg = cfg.get("paths") if isinstance(cfg.get("paths"), dict) else {}
            chat_path = None
            if isinstance(paths_cfg, dict):
                chat_path = paths_cfg.get("chat_completions") or paths_cfg.get("chat") or paths_cfg.get("completions")
            if not chat_path:
                return metrics_problem(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "custom provider missing path",
                    "config.paths.chat_completions missing",
                )
            upstream_url = urljoin(base_url.rstrip("/") + "/", chat_path.lstrip("/"))
            tmpl_src = None
            templates_cfg = cfg.get("request_templates") if isinstance(cfg.get("request_templates"), dict) else {}
            if isinstance(templates_cfg, dict):
                tmpl_src = (
                    templates_cfg.get("chat")
                    or templates_cfg.get("chat_completions")
                    or templates_cfg.get("completions")
                )
            if not tmpl_src:
                return metrics_problem(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "custom provider missing template",
                    "request_templates.chat missing",
                )
            try:
                template = Template(tmpl_src)
                request_payload = _json.loads(
                    template.render(
                        messages=req.messages,
                        model_id=upstream_model_id
                        or (instance.get("model_id") if instance else resolved_model)
                        or resolved_model,
                        tenant_id=ctx.tenant_id,
                        trace_id=_resolve_trace_id(request),
                    )
                )
            except Exception as te:
                return metrics_problem(status.HTTP_500_INTERNAL_SERVER_ERROR, "template render failed", str(te))
        else:
            return metrics_problem(
                status.HTTP_501_NOT_IMPLEMENTED,
                "provider type unsupported",
                f"Unsupported provider type '{provider_type}'",
            )

        async with httpx.AsyncClient(timeout=timeout) as client:
            attempt = 0
            max_attempts = 2 if ollama_provider else 1
            data = None
            while attempt < max_attempts:
                attempt += 1
                try:
                    start_time = time.perf_counter()
                    resp = await client.post(upstream_url, json=request_payload, headers=headers)
                    elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                    _debug_log_provider_call(
                        logger,
                        event="model.chat.provider_call",
                        trace_meta=trace_meta,
                        base_url=base_url,
                        resolved_model=resolved_model,
                        mapped_model=upstream_model_id,
                        elapsed_ms=elapsed_ms,
                        status_code=resp.status_code,
                        attempt=attempt,
                        extra={"url": upstream_url, "provider": provider_label},
                    )
                    if ollama_provider:
                        with suppress(Exception):
                            logger.info(
                                "model.chat.ollama_response",
                                extra={
                                    "details": {
                                        **trace_meta,
                                        "attempt": attempt,
                                        "status": resp.status_code,
                                        "latency_ms": elapsed_ms,
                                        "url": upstream_url,
                                    }
                                },
                            )
                except (httpx.ReadTimeout, httpx.WriteTimeout, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
                    elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                    error_detail = str(exc)
                    _debug_log_provider_call(
                        logger,
                        event="model.chat.provider_timeout",
                        trace_meta=trace_meta,
                        base_url=base_url,
                        resolved_model=resolved_model,
                        mapped_model=upstream_model_id,
                        elapsed_ms=elapsed_ms,
                        error=error_detail,
                        attempt=attempt,
                        extra={"url": upstream_url, "provider": provider_label},
                    )
                    if attempt < max_attempts:
                        if ollama_provider:
                            with suppress(Exception):
                                logger.warning(
                                    "model.chat.ollama_timeout",
                                    extra={"details": {**trace_meta, "attempt": attempt, "error": error_detail}},
                                )
                        continue
                    return metrics_problem(
                        status.HTTP_504_GATEWAY_TIMEOUT,
                        "upstream timeout",
                        error_detail,
                        extra={"error": error_detail},
                    )
                except httpx.RequestError as exc:
                    elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                    error_detail = str(exc)
                    _debug_log_provider_call(
                        logger,
                        event="model.chat.provider_error",
                        trace_meta=trace_meta,
                        base_url=base_url,
                        resolved_model=resolved_model,
                        mapped_model=upstream_model_id,
                        elapsed_ms=elapsed_ms,
                        error=error_detail,
                        attempt=attempt,
                        extra={"url": upstream_url, "provider": provider_label},
                    )
                    if attempt < max_attempts:
                        if ollama_provider:
                            with suppress(Exception):
                                logger.warning(
                                    "model.chat.ollama_request_error",
                                    extra={"details": {**trace_meta, "attempt": attempt, "error": error_detail}},
                                )
                        continue
                    return metrics_problem(
                        status.HTTP_502_BAD_GATEWAY,
                        "upstream connection error",
                        error_detail,
                        extra={"error": error_detail},
                    )

                if resp.status_code >= 400:
                    try:
                        body = resp.json()
                    except Exception:
                        body = {"raw": resp.text[:500]}
                    if resp.status_code == status.HTTP_404_NOT_FOUND:
                        return metrics_problem(
                            status.HTTP_404_NOT_FOUND,
                            "model not present in provider",
                            "model not configured for provider",
                            extra={
                                "url": upstream_url,
                                "resolved_model": resolved_model,
                                "mapped_model": upstream_model_id,
                            },
                        )
                    if status.HTTP_400_BAD_REQUEST <= resp.status_code < status.HTTP_500_INTERNAL_SERVER_ERROR:
                        return metrics_problem(
                            status.HTTP_424_FAILED_DEPENDENCY,
                            "upstream request failed",
                            "Provider returned error",
                            extra={"status": resp.status_code, "url": upstream_url, "body": body},
                        )
                    return metrics_problem(
                        status.HTTP_502_BAD_GATEWAY,
                        "provider request failed",
                        "Upstream provider error",
                        extra={"status": resp.status_code, "url": upstream_url},
                    )

                try:
                    data = resp.json()
                except Exception:
                    return metrics_problem(
                        status.HTTP_502_BAD_GATEWAY,
                        "provider request failed",
                        "Non-JSON upstream response",
                        extra={"snippet": resp.text[:200]},
                    )

                if provider_type == "openai_compatible":
                    choices = data.get("choices")
                    if not isinstance(choices, list) or not choices:
                        if attempt < max_attempts:
                            continue
                        return metrics_problem(
                            status.HTTP_424_FAILED_DEPENDENCY,
                            "upstream returned no choices",
                            "Provider returned empty choices",
                            extra={"url": upstream_url},
                        )
                    first = choices[0] or {}
                    message = first.get("message") or {}
                    output_text = message.get("content") or first.get("text") or ""
                    if not output_text:
                        return metrics_problem(
                            status.HTTP_424_FAILED_DEPENDENCY,
                            "upstream choice missing content",
                            "First choice lacks message.content/text",
                            extra={"url": upstream_url},
                        )
                    role = message.get("role") or "assistant"
                    usage_data = data.get("usage")
                    if isinstance(usage_data, dict):
                        usage = Usage(
                            prompt_tokens=int(usage_data.get("prompt_tokens") or 0),
                            completion_tokens=int(usage_data.get("completion_tokens") or 0),
                            total_tokens=int(usage_data.get("total_tokens") or 0),
                        )
                    response_payload = {
                        "choices": [
                            {"message": {"role": role, "content": output_text}},
                        ]
                    }
                else:
                    cfg = provider_internal.config or {}
                    extract_cfg = (
                        (cfg.get("response_extract", {}) or {}).get("chat")
                        if isinstance(cfg.get("response_extract"), dict)
                        else None
                    )
                    if not extract_cfg and isinstance(cfg.get("response_extract"), dict):
                        extract_cfg = cfg.get("response_extract", {}).get("chat_completions") or cfg.get(
                            "response_extract", {}
                        ).get("completions")
                    if not extract_cfg:
                        return metrics_problem(
                            status.HTTP_500_INTERNAL_SERVER_ERROR,
                            "missing response extractor",
                            "response_extract.chat missing",
                        )
                    expr_output = None
                    role_expr = None
                    if isinstance(extract_cfg, dict):
                        expr_output = extract_cfg.get("output") or extract_cfg.get("message")
                        role_expr = extract_cfg.get("role")
                    if not expr_output:
                        return metrics_problem(
                            status.HTTP_500_INTERNAL_SERVER_ERROR,
                            "missing output extractor",
                            "response_extract.chat.output missing",
                        )
                    try:
                        output_text = jmespath.search(expr_output, data) or ""
                        role = (jmespath.search(role_expr, data) if role_expr else None) or "assistant"
                    except Exception as je:
                        return metrics_problem(
                            status.HTTP_500_INTERNAL_SERVER_ERROR, "output extraction failed", str(je)
                        )
                    if not output_text:
                        return metrics_problem(
                            status.HTTP_424_FAILED_DEPENDENCY,
                            "upstream returned no choices",
                            "Extractor produced empty output",
                            extra={"expr": expr_output},
                        )
                    expr_usage = None
                    if isinstance(extract_cfg, dict):
                        expr_usage = extract_cfg.get("usage")
                    if expr_usage:
                        with suppress(Exception):
                            u = jmespath.search(expr_usage, data) or {}
                            if isinstance(u, dict):
                                usage = Usage(
                                    prompt_tokens=int(u.get("prompt_tokens") or 0),
                                    completion_tokens=int(u.get("completion_tokens") or 0),
                                    total_tokens=int(u.get("total_tokens") or 0),
                                )
                    response_payload = {
                        "choices": [
                            {"message": {"role": role, "content": output_text}},
                        ]
                    }
                break
    except Exception as exc:
        error_detail = str(exc)
        return metrics_problem(
            status.HTTP_502_BAD_GATEWAY,
            "provider request failed",
            "Unexpected provider error",
            extra={"error": error_detail},
        )

    latency_ms = ctx.emit_metrics(status.HTTP_200_OK, provider_label, instance_id)

    ev = record_provenance(
        actor="api",
        action="model.chat.complete",
        resource="/v1/models/chat/completions",
        input={"messages": len(req.messages), "model": resolved_model},
        output={"choices": len(response_payload.get("choices", []))},
        meta={**trace_meta, "latency_ms": latency_ms},
        success=True,
        duration_ms=latency_ms,
    )

    try:  # pragma: no cover
        logger.info(
            "model.chat.end",
            extra={
                "details": {
                    **trace_meta,
                    "latency_ms": latency_ms,
                    "status_code": status.HTTP_200_OK,
                }
            },
        )
    except Exception:
        pass

    response_payload.setdefault("usage", usage.model_dump())
    response_payload.setdefault("model", resolved_model)
    response_payload["trace_id"] = ev.trace_id
    response_payload["event_id"] = ev.event_id
    response_payload["latency_ms"] = latency_ms
    return response_payload


# ---------------- Utilities ----------------
async def _maybe_await(value: Any) -> Any:
    import inspect

    if inspect.isawaitable(value):
        return await value  # type: ignore[misc]
    return value
