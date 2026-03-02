"""
Internal operations router for platform operators.

All endpoints require internal:all permission (service token or internal claim).
Platform admins (admin:all) cannot bypass this requirement.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from db.postgres_control.database import SessionLocal
from db.postgres_control.models.internal_ops_event import InternalOpsEvent
from db.redis_cache.async_client import get_async_redis
from src.config import settings
from src.security.internal import require_internal
from src.security.jwt import Principal

# D1: Use structlog for structured logging with proper field support
logger = structlog.get_logger(__name__)

router = APIRouter(tags=["internal"])


def _get_correlation_id(request: Request, x_correlation_id: str | None = Header(None)) -> str:
    """Extract or generate correlation ID for request tracking."""
    return x_correlation_id or str(uuid4())


def _add_observability_headers(response: Response, correlation_id: str) -> None:
    """Add observability headers to response."""
    response.headers["X-Request-Id"] = correlation_id
    response.headers["X-Trace-Id"] = correlation_id


def _emit_audit_log(
    actor: str,
    action: str,
    resource: str,
    correlation_id: str,
    params: dict,
    result: str,
    duration_ms: float,
) -> None:
    """Emit audit log for admin operations."""
    try:
        # Use structured logging
        logger.info(
            "admin_processes_audit",
            extra={
                "actor": actor,
                "action": action,
                "resource": resource,
                "correlation_id": correlation_id,
                "params": {k: v for k, v in params.items() if k not in ("token", "authorization")},
                "result": result,
                "duration_ms": duration_ms,
            },
        )
    except Exception as e:
        logger.warning(f"Failed to emit audit log: {e}")


def _emit_metric(metric_name: str, value: float, tags: dict) -> None:
    """Emit metric for observability."""
    try:
        # Placeholder for metrics system (e.g., StatsD, Prometheus)
        logger.debug(f"metric: {metric_name}={value} tags={tags}")
    except Exception:
        pass


# ---------------- Models ----------------
class AutoStartOverrideRequest(BaseModel):
    """Request to set auto-start override."""

    enabled: bool = Field(..., description="Enable or disable auto-start override")
    note: str | None = Field(
        None, max_length=200, description="Optional reason/note for this override (max 200 chars)"
    )


class AutoStartOverrideResponse(BaseModel):
    """Response from setting auto-start override."""

    allowed: bool = Field(..., description="Whether UI override is allowed by configuration")
    enabled: bool = Field(..., description="Current override value (false if not allowed)")
    ttl_seconds: int = Field(..., description="TTL of the override in seconds (0 if not allowed or on error)")
    error: str | None = Field(
        None, description="Error code if operation failed gracefully (e.g., 'cache_unavailable')"
    )


class PreviewStagedItem(BaseModel):
    """A single staged manifest preview item."""

    manifest_id: str
    manifest_version: str | None = None
    model_id: str
    est_mem_mb: int
    reason: str
    allowed: bool
    overridden_by_ui: bool
    concurrency_ok: bool
    whitelist_ok: bool
    resources_ok: bool
    ts: str


class PreviewStagedResponse(BaseModel):
    """Response from previewing staged manifests."""

    items: list[PreviewStagedItem]
    count: int
    timestamp: str


# ---------------- Endpoints ----------------


@router.post(
    "/auto-start-override",
    response_model=AutoStartOverrideResponse,
    summary="Override auto-start behavior for built-in models",
    description="Internal endpoint to enable/disable auto-start for built-in models on platform startup",
    responses={
        200: {
            "description": "Override setting successful or gracefully declined",
            "content": {
                "application/json": {
                    "examples": {
                        "success": {
                            "summary": "Override enabled successfully",
                            "value": {"allowed": True, "enabled": True, "ttl_seconds": 600, "error": None},
                        },
                        "disabled": {
                            "summary": "Override feature disabled by config",
                            "value": {"allowed": False, "enabled": False, "ttl_seconds": 0, "error": None},
                        },
                        "cache_error": {
                            "summary": "Redis unavailable",
                            "value": {"allowed": True, "enabled": True, "ttl_seconds": 0, "error": "cache_unavailable"},
                        },
                    }
                }
            },
        },
        403: {"description": "Forbidden - requires internal:all permission or service token"},
        422: {"description": "Validation Error - invalid request body"},
    },
)
async def auto_start_override(
    request_body: AutoStartOverrideRequest,
    response: Response,
    principal: Principal = Depends(require_internal()),
    request_id: str | None = Header(None, alias="X-Request-ID"),
    correlation_id: str | None = Header(None, alias="X-Correlation-Id"),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> AutoStartOverrideResponse:
    """
    POST /auto-start-override

    Override auto-start behavior for built-in models.

    **Security:** Internal only (service token or internal:all scope). Admin tokens rejected with 403.
    **Config:** Controlled by INTERNAL_UI_OVERRIDE_ALLOWED env var (defaults to "1" = enabled).
    **Storage:** Redis key `internal:auto_start_override` with configurable TTL.
    **Idempotency:** Supported via Idempotency-Key header (24h cache).

    **Returns 200** in all cases (even config disabled or Redis failure) with appropriate payload.
    """
    start_time = time.time()
    req_id = request_id or correlation_id or f"req_{uuid.uuid4().hex[:12]}"
    actor_sub = principal.sub if hasattr(principal, "sub") else str(principal)

    # Add standard observability headers
    response.headers["X-Request-Id"] = req_id
    response.headers["X-Correlation-Id"] = req_id
    response.headers["X-Subject"] = actor_sub

    # Check if UI override feature is enabled via config
    override_allowed = (
        settings.INTERNAL_UI_OVERRIDE_ALLOWED if hasattr(settings, "INTERNAL_UI_OVERRIDE_ALLOWED") else True
    )
    if isinstance(override_allowed, str):
        override_allowed = override_allowed not in ("0", "false", "False", "no", "")

    # If feature disabled, return 200 with allowed=false
    if not override_allowed:
        logger.info(f"[{req_id}] UI override disabled by config")
        _emit_audit_log(
            actor=actor_sub,
            action="auto_start_override",
            resource="/internal/ops/auto-start-override",
            correlation_id=req_id,
            params={"enabled": request_body.enabled, "note": request_body.note},
            result="config_disabled",
            duration_ms=(time.time() - start_time) * 1000,
        )
        return AutoStartOverrideResponse(allowed=False, enabled=False, ttl_seconds=0, error=None)

    # Get TTL from config (default 600s = 10 minutes)
    ttl_seconds = getattr(settings, "INTERNAL_UI_OVERRIDE_TTL_SECONDS", 600)
    if isinstance(ttl_seconds, str):
        try:
            ttl_seconds = int(ttl_seconds)
        except ValueError:
            ttl_seconds = 600

    # Check idempotency cache first (24h TTL)
    if idempotency_key:
        try:
            redis = await get_async_redis()
            idem_key = f"idemp:/internal/ops/auto-start-override:{idempotency_key}"
            cached = await redis.get(idem_key)
            if cached:
                logger.info(f"[{req_id}] Returning cached response for idempotency key: {idempotency_key[:16]}...")
                response.headers["Idempotency-Replayed"] = "true"
                return AutoStartOverrideResponse.model_validate_json(cached)
        except Exception as e:
            logger.warning(f"[{req_id}] Idempotency cache check failed: {e}")
            # Continue without idempotency

    # Attempt to write override to Redis
    redis_error = None
    try:
        redis = await get_async_redis()
        override_key = "internal:auto_start_override"

        # Store as JSON for structured data
        override_data = {
            "enabled": request_body.enabled,
            "note": request_body.note,
            "set_by_sub": actor_sub,
            "set_at": datetime.now(UTC).isoformat(),
            "ttl_seconds": ttl_seconds,
        }

        await redis.setex(override_key, ttl_seconds, json.dumps(override_data))
        logger.info(f"[{req_id}] Auto-start override set: enabled={request_body.enabled}, ttl={ttl_seconds}s")

        # Cache response for idempotency (24h = 86400s)
        if idempotency_key:
            result = AutoStartOverrideResponse(
                allowed=True, enabled=request_body.enabled, ttl_seconds=ttl_seconds, error=None
            )
            try:
                await redis.setex(idem_key, 86400, result.model_dump_json())
                logger.debug(f"[{req_id}] Cached idempotency response for 24h")
            except Exception as e:
                logger.warning(f"[{req_id}] Failed to cache idempotency response: {e}")

    except Exception as e:
        logger.error(f"[{req_id}] Redis write failed: {e}", exc_info=True)
        redis_error = "cache_unavailable"

    # Audit to PostgreSQL (best effort, don't fail request if this fails)
    try:
        db = SessionLocal()
        try:
            event = InternalOpsEvent(
                kind="auto_start_override",
                sub=actor_sub,
                enabled=request_body.enabled,
                note=request_body.note,
                data_json={"ttl_seconds": ttl_seconds, "redis_error": redis_error},
            )
            db.add(event)
            db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"[{req_id}] Audit log to PostgreSQL failed: {e}")

    # Emit structured audit log
    _emit_audit_log(
        actor=actor_sub,
        action="auto_start_override",
        resource="/internal/ops/auto-start-override",
        correlation_id=req_id,
        params={"enabled": request_body.enabled, "note": request_body.note},
        result="success" if not redis_error else "cache_error",
        duration_ms=(time.time() - start_time) * 1000,
    )

    # Always return 200, even if Redis failed
    return AutoStartOverrideResponse(
        allowed=True, enabled=request_body.enabled, ttl_seconds=ttl_seconds if not redis_error else 0, error=redis_error
    )


@router.get(
    "/preview-staged",
    response_model=PreviewStagedResponse,
    summary="Preview staged built-in manifests before deployment",
    description="Internal endpoint to inspect which built-in models will be deployed on next restart",
    responses={
        200: {"description": "Preview generated successfully"},
        403: {"description": "Forbidden - requires internal:all permission or service token"},
    },
)
async def preview_staged(
    response: Response,
    principal: Principal = Depends(require_internal()),
    request_id: str | None = Header(None, alias="X-Request-ID"),
    correlation_id: str | None = Header(None, alias="X-Correlation-Id"),
    force_refresh: bool = Query(False, description="Force refresh from disk, bypass cache"),
) -> PreviewStagedResponse:
    """
    GET /preview-staged

    Preview which built-in manifests are staged for deployment.

    **Security:** Internal only (service token or internal:all scope). Admin tokens rejected with 403.
    **Storage:** Redis cache (30-60s TTL), reads from /app/run/builtins/ directory
    **Behavior:**
      - Reads auto-start override from `internal:auto_start_override` if present
      - Sets `overridden_by_ui=true` when override changes allow/deny decision
      - Returns list with allow/deny reasons for each manifest
    """
    start_time = time.time()
    req_id = request_id or correlation_id or f"req_{uuid.uuid4().hex[:12]}"
    actor_sub = principal.sub if hasattr(principal, "sub") else str(principal)

    # Add standard observability headers
    response.headers["X-Request-Id"] = req_id
    response.headers["X-Correlation-Id"] = req_id
    response.headers["X-Subject"] = actor_sub

    cache_key = "internal:preview-staged:v1"

    # Check cache unless force_refresh
    if not force_refresh:
        try:
            redis = await get_async_redis()
            cached_data = await redis.get(cache_key)
            if cached_data:
                # Parse cached data to check if it's still valid
                try:
                    cached_obj = json.loads(cached_data)
                    cached_mtime = cached_obj.get("_cache_metadata", {}).get("dir_mtime")

                    # Check if builtins directory has been modified since cache
                    builtins_dir = Path("/app/run/builtins")
                    if builtins_dir.exists():
                        current_mtime = builtins_dir.stat().st_mtime
                        if cached_mtime and abs(current_mtime - cached_mtime) < 1.0:
                            # Directory hasn't been modified, cache is still valid
                            logger.debug(f"[{req_id}] Returning cached preview (mtime valid)")
                            response.headers["X-Cache-Status"] = "hit"
                            _emit_audit_log(
                                actor=actor_sub,
                                action="preview_staged",
                                resource="/internal/ops/preview-staged",
                                correlation_id=req_id,
                                params={"force_refresh": force_refresh},
                                result="cache_hit",
                                duration_ms=(time.time() - start_time) * 1000,
                            )
                            # Return cached response without metadata
                            del cached_obj["_cache_metadata"]
                            return PreviewStagedResponse.model_validate(cached_obj)
                except Exception as e:
                    logger.debug(f"[{req_id}] Cache validation failed: {e}")
                    # Fall through to generate fresh response
        except Exception as e:
            logger.warning(f"[{req_id}] Cache read failed: {e}")
            # Continue to generate fresh response

    response.headers["X-Cache-Status"] = "miss" if not force_refresh else "refresh"

    # Read UI override setting if present
    ui_override = None
    try:
        redis = await get_async_redis()
        override_data = await redis.get("internal:auto_start_override")
        if override_data:
            ui_override = json.loads(override_data)
            logger.info(f"[{req_id}] UI override active: {ui_override}")
    except Exception as e:
        logger.warning(f"[{req_id}] Failed to read UI override: {e}")

    try:
        # Read manifests from disk
        builtins_dir = Path("/app/run/builtins")
        items = []

        if builtins_dir.exists():
            for manifest_file in builtins_dir.glob("*.json"):
                try:
                    with open(manifest_file) as f:
                        data = json.load(f)

                    manifest_id = data.get("manifest_id", manifest_file.stem)
                    model_id = data.get("model_id", manifest_id)
                    auto_start_default = data.get("auto_start", False)
                    est_mem_mb = data.get("est_mem_mb", 0)

                    # Determine if allowed based on various checks
                    # (Simplified logic - real implementation would check concurrency, whitelist, resources)
                    allowed_by_policy = auto_start_default
                    overridden_by_ui = False

                    # Apply UI override if present
                    if ui_override:
                        ui_enabled = ui_override.get("enabled", False)
                        if ui_enabled != auto_start_default:
                            allowed_by_policy = ui_enabled
                            overridden_by_ui = True

                    # Build reason string
                    reasons = []
                    if overridden_by_ui:
                        reasons.append(f"UI_override={'allow' if allowed_by_policy else 'deny'}")
                    if auto_start_default:
                        reasons.append("default_auto_start=true")

                    reason = "; ".join(reasons) if reasons else "default_auto_start=false"

                    items.append(
                        PreviewStagedItem(
                            manifest_id=manifest_id,
                            manifest_version=data.get("version"),
                            model_id=model_id,
                            est_mem_mb=est_mem_mb,
                            reason=reason,
                            allowed=allowed_by_policy,
                            overridden_by_ui=overridden_by_ui,
                            concurrency_ok=True,  # Simplified - real check would be here
                            whitelist_ok=True,  # Simplified
                            resources_ok=True,  # Simplified
                            ts=datetime.now(UTC).isoformat(),
                        )
                    )
                except Exception as e:
                    logger.warning(f"[{req_id}] Failed to parse {manifest_file.name}: {e}")
                    continue

        response_data = PreviewStagedResponse(items=items, count=len(items), timestamp=datetime.now(UTC).isoformat())

        # Cache for configured TTL (default 60s)
        cache_ttl = getattr(settings, "INTERNAL_PREVIEW_CACHE_TTL_SECONDS", 60)
        try:
            redis = await get_async_redis()
            # Include metadata for cache coherence
            cache_obj = response_data.model_dump()
            cache_obj["_cache_metadata"] = {
                "dir_mtime": builtins_dir.stat().st_mtime if builtins_dir.exists() else 0,
                "cached_at": datetime.now(UTC).isoformat(),
            }
            await redis.setex(cache_key, cache_ttl, json.dumps(cache_obj))
            logger.debug(f"[{req_id}] Cached preview for {cache_ttl}s")
        except Exception as e:
            logger.warning(f"[{req_id}] Failed to cache preview: {e}")

        _emit_audit_log(
            actor=actor_sub,
            action="preview_staged",
            resource="/internal/ops/preview-staged",
            correlation_id=req_id,
            params={"force_refresh": force_refresh, "manifest_count": len(items)},
            result="success",
            duration_ms=(time.time() - start_time) * 1000,
        )

        logger.info(f"[{req_id}] Preview staged: {len(items)} manifests found")
        return response_data

    except Exception as e:
        logger.error(f"[{req_id}] Failed to preview staged manifests: {e}", exc_info=True)
        # Return empty list rather than 500
        return PreviewStagedResponse(items=[], count=0, timestamp=datetime.now(UTC).isoformat())


# ---------------- E14: LLM Smoke Test Endpoint ----------------


class LLMSmokeTestResponse(BaseModel):
    """Response from LLM smoke test endpoint."""

    status: str = Field(..., description="Status of smoke test: success, error, or timeout")
    model: str = Field(..., description="Model name used for test")
    prompt: str = Field(..., description="Test prompt sent to LLM")
    response_text: str | None = Field(None, description="LLM response (truncated to 500 chars)")
    latency_ms: int = Field(..., description="End-to-end latency in milliseconds")
    tokens_input: int | None = Field(None, description="Input tokens (if available)")
    tokens_output: int | None = Field(None, description="Output tokens (if available)")
    error: str | None = Field(None, description="Error message if test failed")
    device: str = Field(..., description="Device used for inference (cpu/cuda/mps)")
    api_base: str = Field(..., description="LLM API base URL")
    # DB-driven configuration info (Step D.12)
    instance_name: str | None = Field(None, description="Model instance name from DB (canonical alias)")
    provider_model_id: str | None = Field(None, description="Provider-specific model identifier")
    config_source: str = Field("env", description="Configuration source: db_default, env, or fallback")
    provider_name: str | None = Field(None, description="LLM provider name (e.g., ollama-local)")


class ToolsSmokeTestResponse(BaseModel):
    data_quality: dict
    graph_schema: dict
    principal_used: dict


# Configurable smoke test timeout (seconds) - defaults to 180s but can be raised for slow CPUs
SMOKE_TEST_TIMEOUT_SECONDS = int(os.getenv("LLM_SMOKE_TIMEOUT_SECONDS", "180"))


@router.post(
    "/llm-smoke-test",
    response_model=LLMSmokeTestResponse,
    summary="Run LLM smoke test with latency reporting",
    description=(
        "E14: Internal endpoint for LLM connectivity and latency smoke test.\n\n"
        "Sends a minimal prompt to the LLM provider and reports:\n"
        "- End-to-end latency (ms)\n"
        "- Token usage (input/output)\n"
        "- Response snippet (500 chars max)\n"
        "- Error details if test fails\n\n"
        "Useful for:\n"
        "- Verifying LLM provider connectivity before test runs\n"
        "- Benchmarking CPU vs GPU inference latency\n"
        "- Diagnosing slow LLM responses\n\n"
        "Requires internal:all permission."
    ),
)
async def llm_smoke_test(
    request: Request,
    principal: Principal = Depends(require_internal),
    x_correlation_id: str | None = Header(None),
) -> LLMSmokeTestResponse:
    """
    E14: Run LLM smoke test with detailed latency reporting.
    
    This endpoint sends a minimal prompt to the LLM provider and measures:
    - Connection time
    - Inference time
    - Token usage
    - Response quality
    
    Used by operators to verify LLM health before running test suites.
    """
    req_id = _get_correlation_id(request, x_correlation_id)
    actor_sub = getattr(principal, "sub", "unknown")
    start_time = time.time()
    
    logger.info(f"[{req_id}] LLM smoke test requested by {actor_sub}")
    
    try:
        # Import LLM adapter and DB repositories
        from src.adapters.llm import LLMClient
        from db.postgres_control.repositories import model_instance_repo
        
        # Get DB-driven default model configuration (Step D.12)
        default_config = None
        config_source = "env"
        provider_name: str | None = None
        try:
            default_config = model_instance_repo.get_default(scope="global", tenant_id=None)
            if default_config:
                config_source = "db_default"
                provider_name = default_config.provider_name
                logger.info(
                    f"[{req_id}] Using DB default model",
                    instance_name=default_config.instance_name,
                    model_id=default_config.provider_model_id,
                    provider=default_config.provider_name
                )
        except Exception as e:
            logger.warning(f"[{req_id}] Could not load DB default model: {e}")
        
        # Require DB config for smoke test (no env fallback)
        if not default_config:
            error_msg = "No default model configured in database (model_defaults table)"
            logger.error(f"[{req_id}] {error_msg}")
            return LLMSmokeTestResponse(
                status="error",
                model="unknown",
                prompt=test_prompt,
                response_text=None,
                latency_ms=0,
                tokens_input=None,
                tokens_output=None,
                error=error_msg,
                device="unknown",
                api_base="unknown",
                instance_name=None,
                provider_model_id=None,
                config_source="missing",
                provider_name=provider_name or "unknown",
            )
        
        # Build smoke test prompt (minimal)
        test_prompt = "Say 'OK' if you can read this message."
        
        # Initialize LLM client with DB config (using LLMModelConfig dataclass)
        llm_client = LLMClient(
            model=default_config.provider_model_id,  # Provider-specific ID (e.g., phi3:mini)
            base_url=default_config.base_url,
            api_key=None,
        )
        model_name = default_config.instance_name  # Canonical alias
        provider_model_id = default_config.provider_model_id
        provider_name = provider_name or default_config.provider_name
        api_base = default_config.base_url
        
        # Measure latency
        llm_start = time.time()
        
        try:
            # Call LLM (returns string response)
            response_text = await llm_client.complete(
                prompt=test_prompt,
                temperature=0.0,
                max_tokens=10,  # Minimal output
                metadata={"run_id": req_id, "prompt_type": "smoke_test"},
                timeout_seconds=SMOKE_TEST_TIMEOUT_SECONDS,
            )
            
            llm_latency_ms = int((time.time() - llm_start) * 1000)
            
            # Token usage not available from simple complete() - would need access to raw response
            tokens_input = None
            tokens_output = None
            
            # Success
            result = LLMSmokeTestResponse(
                status="success",
                model=model_name,
                prompt=test_prompt,
                response_text=response_text[:500] if response_text else "(empty)",
                latency_ms=llm_latency_ms,
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                error=None,
                device=os.getenv("LLM_DEVICE", "cpu"),
                api_base=api_base,
                instance_name=default_config.instance_name if default_config else None,
                provider_model_id=provider_model_id,
                config_source=config_source,
                provider_name=provider_name or "unknown",
            )
            
            logger.info(
                f"[{req_id}] LLM smoke test SUCCESS: {llm_latency_ms}ms, "
                f"response={response_text[:50]}"
            )
            
            _emit_audit_log(
                actor=actor_sub,
                action="llm_smoke_test",
                resource="/internal/llm-smoke-test",
                correlation_id=req_id,
                params={
                    "model": model_name,
                    "device": os.getenv("LLM_DEVICE", "cpu"),
                },
                result="success",
                duration_ms=(time.time() - start_time) * 1000,
            )
            
            return result
            
        except TimeoutError:
            llm_latency_ms = int((time.time() - llm_start) * 1000)
            
            logger.error(f"[{req_id}] LLM smoke test TIMEOUT after {llm_latency_ms}ms")
            
            _emit_audit_log(
                actor=actor_sub,
                action="llm_smoke_test",
                resource="/internal/llm-smoke-test",
                correlation_id=req_id,
                params={
                    "model": model_name,
                    "device": os.getenv("LLM_DEVICE", "cpu"),
                },
                result="timeout",
                duration_ms=(time.time() - start_time) * 1000,
            )
            
            return LLMSmokeTestResponse(
                status="timeout",
                model=model_name,
                prompt=test_prompt,
                response_text=None,
                latency_ms=llm_latency_ms,
                tokens_input=None,
                tokens_output=None,
                error=f"LLM request timed out after {llm_latency_ms}ms",
                device=os.getenv("LLM_DEVICE", "cpu"),
                api_base=api_base,
                instance_name=default_config.instance_name if default_config else None,
                provider_model_id=provider_model_id,
                config_source=config_source,
                provider_name=provider_name or "unknown",
            )
            
        except Exception as llm_error:
            llm_latency_ms = int((time.time() - llm_start) * 1000)
            error_msg = str(llm_error)
            
            logger.error(f"[{req_id}] LLM smoke test ERROR: {error_msg}", exc_info=True)
            
            _emit_audit_log(
                actor=actor_sub,
                action="llm_smoke_test",
                resource="/internal/llm-smoke-test",
                correlation_id=req_id,
                params={
                    "model": model_name,
                    "device": os.getenv("LLM_DEVICE", "cpu"),
                },
                result="error",
                duration_ms=(time.time() - start_time) * 1000,
            )
            
            return LLMSmokeTestResponse(
                status="error",
                model=model_name,
                prompt=test_prompt,
                response_text=None,
                latency_ms=llm_latency_ms,
                tokens_input=None,
                tokens_output=None,
                error=error_msg[:500],  # Truncate long errors
                device=os.getenv("LLM_DEVICE", "cpu"),
                api_base=api_base,
                instance_name=default_config.instance_name if default_config else None,
                provider_model_id=provider_model_id,
                config_source=config_source,
                provider_name=provider_name or "unknown",
            )
    
    except Exception as e:
        # Configuration or setup error
        logger.error(f"[{req_id}] LLM smoke test setup failed: {e}", exc_info=True)
        
        return LLMSmokeTestResponse(
            status="error",
            model="unknown",
            prompt=test_prompt if 'test_prompt' in locals() else "(not sent)",
            response_text=None,
            latency_ms=int((time.time() - start_time) * 1000),
            tokens_input=None,
            tokens_output=None,
            error=f"Setup error: {str(e)[:500]}",
            device=os.getenv("OLLAMA_DEVICE", "unknown"),
            api_base=os.getenv("ORCHESTRATOR_API_BASE", "unknown"),
            provider_name="unknown",
        )


@router.post(
    "/tools-smoke-test",
    response_model=ToolsSmokeTestResponse,
    summary="Run MCP tools smoke test (data.quality + graph.schema)",
    description="Verifies principal propagation and MCP RBAC by executing data.quality and graph.schema with a test principal.",
)
async def tools_smoke_test(
    request: Request,
    principal: Principal = Depends(require_internal),
    x_correlation_id: str | None = Header(None),
) -> ToolsSmokeTestResponse:
    req_id = _get_correlation_id(request, x_correlation_id)
    actor_sub = getattr(principal, "sub", "unknown")
    start_time = time.time()

    from src.services.orchestrator import get_orchestrator_instance

    orch = get_orchestrator_instance()
    test_principal = {
        "id": actor_sub or "tools-smoke-test",
        "sub": actor_sub or "tools-smoke-test",
        "tenant_id": getattr(principal, "tenant_id", "tenant-ops"),
        "scopes": ["tools:read", "tools:basic"],
        "permissions": ["admin:all"],
        "roles": ["admin"],
    }

    dq = await orch.execute_tool(
        "data.quality",
        payload={"action": "default", "principal": test_principal, "tenant": test_principal["tenant_id"]},
        principal=test_principal,
        tenant=test_principal["tenant_id"],
        trace_id=req_id,
    )
    schema = await orch.execute_tool(
        "graph.schema",
        payload={"action": "default", "principal": test_principal, "tenant": test_principal["tenant_id"]},
        principal=test_principal,
        tenant=test_principal["tenant_id"],
        trace_id=req_id,
    )

    duration_ms = int((time.time() - start_time) * 1000)
    _emit_audit_log(
        actor=actor_sub,
        action="tools_smoke_test",
        resource="internal_ops",
        correlation_id=req_id,
        params={},
        result="success",
        duration_ms=duration_ms,
    )

    return ToolsSmokeTestResponse(
        data_quality=dq, graph_schema=schema, principal_used=test_principal
    )
