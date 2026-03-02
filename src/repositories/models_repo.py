"""Models runtime persistence repository (Redis-backed with in-memory fallback).

Responsibilities:
- Providers CRUD (registry-only, no auto-discovery)
- Instances CRUD (referencing providers by id)
- Defaults (global + scoped e.g. chat)
- Hydration at startup + optional backfill if Redis empty but in-memory had prior data

Key schema:
  models:providers:{id} -> JSON { id, name, type, base_url, model, api_key?, tenant_id?, config?, created_at, updated_at }
  models:instances:{id} -> JSON { id, name, provider_id, model_id, model_uri?, parameters, created_at, updated_at, loaded?, enabled?, default? }
  models:defaults:{scope} -> JSON { scope, instance_id, provider_id, name, updated_at }

Index sets:
  models:providers:index -> set of provider ids
  models:instances:index -> set of instance ids

We keep a process-local mirror so reads are fast even if Redis latency spikes.
If Redis unavailable, operations affect only the mirror and a warning is logged once.
"""
from __future__ import annotations

import logging
import time
from contextlib import suppress
from dataclasses import asdict, dataclass
from typing import Any

from db.redis_cache.client import (
    cache_delete,
    cache_get_json,
    cache_set_json,
    get_redis,
    redis_available,
)

logger = logging.getLogger(__name__)

_TOP_LEVEL_SECRET_KEYS = {
    "api_key",
    "token",
    "authorization",
    "auth_token",
    "password",
}

_HEADER_SECRET_KEYS = {"authorization", "x-api-key"}
_AUTH_SECRET_KEYS = {"token", "api_key", "password"}


def _mask_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return "***"
    return "***"


def _redact_secrets(payload: Any) -> Any:
    if isinstance(payload, list):
        return [_redact_secrets(item) for item in payload]
    if isinstance(payload, tuple):
        return tuple(_redact_secrets(item) for item in payload)
    if not isinstance(payload, dict):
        return payload

    redacted: dict[str, Any] = {}
    for key, value in payload.items():
        key_lower = str(key).lower()
        if key_lower in _TOP_LEVEL_SECRET_KEYS or key_lower.endswith("_token"):
            redacted[key] = _mask_value(value)
            continue
        if isinstance(value, (dict, list, tuple)):
            redacted[key] = _redact_secrets(value)
        else:
            redacted[key] = value

    config = redacted.get("config")
    if isinstance(config, dict):
        headers = config.get("headers")
        if isinstance(headers, dict):
            for header_key in list(headers.keys()):
                if str(header_key).lower() in _HEADER_SECRET_KEYS:
                    headers[header_key] = _mask_value(headers[header_key])
        auth_cfg = config.get("auth")
        if isinstance(auth_cfg, dict):
            for auth_key in list(auth_cfg.keys()):
                auth_lower = str(auth_key).lower()
                if auth_lower in _AUTH_SECRET_KEYS or auth_lower.endswith("_token"):
                    auth_cfg[auth_key] = _mask_value(auth_cfg[auth_key])

    return redacted


# --------------- Data classes ---------------
@dataclass
class ProviderRecord:
    id: str
    name: str
    type: str
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None
    tenant_id: str | None = None
    config: dict[str, Any] | None = None
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self):
        return asdict(self)


@dataclass
class InstanceRecord:
    id: str
    name: str
    provider_id: str
    model_id: str | None = None
    model_uri: str | None = None
    parameters: dict[str, Any] = None
    loaded: bool | None = None
    enabled: bool | None = None
    default: bool = False
    tenant_id: str | None = None
    created_at: float = 0.0
    updated_at: float = 0.0
    description: str | None = None
    context_window: int | None = None
    modalities: list[str] | None = None

    def to_dict(self):
        d = asdict(self)
        if d.get("parameters") is None:
            d["parameters"] = {}
        if d.get("modalities") is None:
            d["modalities"] = ["text"]
        return d


@dataclass
class DefaultRecord:
    scope: str
    instance_id: str | None = None
    provider_id: str | None = None
    name: str | None = None
    tenant_id: str | None = None
    updated_at: float = 0.0

    def to_dict(self):
        return asdict(self)


# --------------- In-memory mirrors ---------------
_PROVIDERS: dict[str, ProviderRecord] = {}
_INSTANCES: dict[str, InstanceRecord] = {}
_DEFAULTS: dict[str, DefaultRecord] = {}
_PROVIDER_HEALTH: dict[str, dict[str, Any]] = {}

_warned_no_redis = False


def _now() -> float:
    return time.time()


# --------------- Key helpers ---------------
def KP(pid):
    return f"models:providers:{pid}"  # Provider key
def KI(iid):
    return f"models:instances:{iid}"  # Instance key
def KD(scope):
    return f"models:defaults:{scope}"  # Legacy global default key
def KD_T(scope, tenant):
    return f"models:defaults:{scope}:{tenant or 'global'}"  # Tenant-scoped default key
PROV_INDEX = "models:providers:index"
INST_INDEX = "models:instances:index"

# --------------- Redis helper wrappers ---------------


def _redis_safe() -> bool:
    global _warned_no_redis
    if not redis_available():
        if not _warned_no_redis:
            logger.warning("models_repo.redis.unavailable - operating in memory-only mode")
            _warned_no_redis = True
        return False
    return True


# --------------- Providers ---------------


def create_provider(id: str, name: str, type: str, base_url: str | None, **extra) -> tuple[bool, ProviderRecord]:
    if id in _PROVIDERS:
        raise ValueError("provider exists")
    ts = _now()
    rec = ProviderRecord(
        id=id,
        name=name,
        type=type,
        base_url=base_url,
        created_at=ts,
        updated_at=ts,
        **{k: v for k, v in extra.items() if k in ProviderRecord.__annotations__},
    )
    _PROVIDERS[id] = rec
    if _redis_safe():
        try:
            r = get_redis()
            # Prevent duplicates with EXISTS
            if r.exists(KP(id)):
                _PROVIDERS.pop(id, None)
                raise ValueError("provider exists")
            cache_set_json(KP(id), rec.to_dict())
            r.sadd(PROV_INDEX, id)
        except Exception as exc:
            logger.warning("models_repo.provider.persist.failed", extra={"id": id, "error": str(exc)})
    return True, rec


def list_providers() -> list[dict[str, Any]]:
    """List providers with secrets redacted via centralized utility."""
    out: list[dict[str, Any]] = []
    for p in _PROVIDERS.values():
        raw = p.to_dict()
        redacted = _redact_secrets(raw)
        h = _PROVIDER_HEALTH.get(p.id)
        if h is not None:
            try:
                redacted.setdefault("health", {})
                redacted["health"].update(h)  # type: ignore[arg-type]
            except Exception:
                redacted["health"] = h  # type: ignore[assignment]
        out.append(redacted)
    return out


def get_provider(id: str) -> dict[str, Any] | None:
    rec = _PROVIDERS.get(id)
    if not rec:
        return None
    return _redact_secrets(rec.to_dict())


def get_provider_internal(id: str) -> ProviderRecord | None:
    """Return the raw ProviderRecord (non-redacted) for internal runtime use.

    WARNING: Do not expose this directly via public/admin APIs. Intended only for
    runtime routing where secrets (api_key, auth tokens, headers) are required to
    construct outbound requests.
    """
    return _PROVIDERS.get(id)


def patch_provider(id: str, **updates) -> ProviderRecord:
    rec = _PROVIDERS.get(id)
    if not rec:
        raise KeyError("provider missing")
    changed = False
    for k, v in updates.items():
        if v is None:
            continue
        if k in ProviderRecord.__annotations__ and getattr(rec, k) != v:
            setattr(rec, k, v)
            changed = True
    if changed:
        rec.updated_at = _now()
        if _redis_safe():
            try:
                cache_set_json(KP(id), rec.to_dict())
            except Exception as exc:
                logger.warning("models_repo.provider.patch.persist.failed", extra={"id": id, "error": str(exc)})
        # Recompute health asynchronously on next tick
        with suppress(Exception):
            _PROVIDER_HEALTH.pop(id, None)
    return rec


def delete_provider(id: str, *, forbid_if_default: bool = True, forbid_if_referenced: bool = True) -> bool:
    if forbid_if_referenced:
        for inst in _INSTANCES.values():
            if inst.provider_id == id:
                raise ValueError("provider in use by instance")
    if forbid_if_default:
        for d in _DEFAULTS.values():
            if d.provider_id == id:
                raise ValueError("provider is default")
    rec = _PROVIDERS.pop(id, None)
    _PROVIDER_HEALTH.pop(id, None)
    if rec and _redis_safe():
        with suppress(Exception):
            cache_delete(KP(id))
            get_redis().srem(PROV_INDEX, id)
    return rec is not None


# --------------- Instances ---------------


def create_instance(id: str, name: str, provider_id: str, **extra) -> tuple[bool, InstanceRecord]:
    if id in _INSTANCES:
        raise ValueError("instance exists")
    if provider_id not in _PROVIDERS:
        raise ValueError("provider not found")
    ts = _now()
    rec = InstanceRecord(
        id=id,
        name=name,
        provider_id=provider_id,
        created_at=ts,
        updated_at=ts,
        **{k: v for k, v in extra.items() if k in InstanceRecord.__annotations__},
    )
    _INSTANCES[id] = rec
    if _redis_safe():
        try:
            r = get_redis()
            if r.exists(KI(id)):
                _INSTANCES.pop(id, None)
                raise ValueError("instance exists")
            cache_set_json(KI(id), rec.to_dict())
            r.sadd(INST_INDEX, id)
        except Exception as exc:
            logger.warning("models_repo.instance.persist.failed", extra={"id": id, "error": str(exc)})
    return True, rec


def list_instances() -> list[dict[str, Any]]:
    return [i.to_dict() for i in _INSTANCES.values()]


def get_instance(id: str) -> dict[str, Any] | None:
    rec = _INSTANCES.get(id)
    return rec.to_dict() if rec else None


def delete_instance(id: str) -> bool:
    rec = _INSTANCES.pop(id, None)
    if rec and _redis_safe():
        with suppress(Exception):
            cache_delete(KI(id))
            get_redis().srem(INST_INDEX, id)
    # remove defaults referencing it (all tenants)
    for _key, d in list(_DEFAULTS.items()):
        if d.instance_id == id:
            d.instance_id = None
            d.name = None
            d.provider_id = None
            if _redis_safe():
                with suppress(Exception):
                    cache_set_json(KD_T(d.scope, d.tenant_id), d.to_dict())
                    if not d.tenant_id:
                        cache_set_json(KD(d.scope), d.to_dict())
    return rec is not None


# --------------- Defaults ---------------


def set_default(scope: str, instance_id: str | None, tenant_id: str | None = None) -> DefaultRecord:
    if instance_id and instance_id not in _INSTANCES:
        raise ValueError("instance not found")
    inst = _INSTANCES.get(instance_id) if instance_id else None
    key = f"{scope}:{tenant_id or 'global'}"
    rec = _DEFAULTS.get(key) or DefaultRecord(scope=scope, tenant_id=tenant_id, updated_at=_now())
    rec.instance_id = instance_id
    rec.provider_id = inst.provider_id if inst else None
    rec.name = inst.name if inst else None
    rec.tenant_id = tenant_id
    rec.updated_at = _now()
    _DEFAULTS[key] = rec
    if _redis_safe():
        with suppress(Exception):
            cache_set_json(KD_T(scope, tenant_id), rec.to_dict())
            if not tenant_id:
                cache_set_json(KD(scope), rec.to_dict())
    # Update instance flags (only one default per scope for now -> 'chat')
    if scope == "chat":
        for i in _INSTANCES.values():
            i.default = i.id == instance_id
            if _redis_safe():
                with suppress(Exception):
                    cache_set_json(KI(i.id), i.to_dict())
    return rec


def get_default(scope: str, tenant_id: str | None = None) -> dict[str, Any] | None:
    key = f"{scope}:{tenant_id or 'global'}"
    rec = _DEFAULTS.get(key)
    return rec.to_dict() if rec else None


def get_defaults() -> dict[str, Any]:
    # Back-compat: return only global defaults keyed by scope
    out: dict[str, Any] = {}
    for key, rec in _DEFAULTS.items():
        try:
            scope, tenant = key.split(":", 1)
        except ValueError:
            scope = key
            tenant = "global"
        if tenant == "global":
            out[scope] = rec.to_dict()
    # If empty, try legacy Redis key and hydrate memory
    if not out and _redis_safe():
        with suppress(Exception):
            for scope in ["chat"]:
                data = cache_get_json(KD(scope))
                if isinstance(data, dict):
                    out[scope] = data
                    _DEFAULTS[f"{scope}:global"] = DefaultRecord(**data)
    return out


def set_provider_default(scope: str, provider_id: str, tenant_id: str | None = None) -> DefaultRecord:
    if provider_id and provider_id not in _PROVIDERS:
        raise ValueError("provider not found")
    key = f"{scope}:{tenant_id or 'global'}"
    rec = _DEFAULTS.get(key) or DefaultRecord(scope=scope, tenant_id=tenant_id, updated_at=_now())
    rec.instance_id = None
    rec.provider_id = provider_id
    rec.name = None
    rec.tenant_id = tenant_id
    rec.updated_at = _now()
    _DEFAULTS[key] = rec
    if _redis_safe():
        with suppress(Exception):
            cache_set_json(KD_T(scope, tenant_id), rec.to_dict())
            if not tenant_id:
                cache_set_json(KD(scope), rec.to_dict())
            # ALSO update orchestrator's cache key format for compatibility
            # Orchestrator expects: tenant:{tenant_id}:main_llm = provider_name
            if tenant_id:
                cache_set(f"tenant:{tenant_id}:main_llm", provider_id, ex=86400)
            else:
                # For global default, also set a global cache key
                cache_set("global:main_llm", provider_id, ex=86400)
    return rec


# --------------- Hydration & Backfill ---------------


def hydrate_from_redis() -> None:
    if not _redis_safe():
        return
    try:
        r = get_redis()
        # Providers
        prov_ids = r.smembers(PROV_INDEX) or []
        for pid in prov_ids:
            data = cache_get_json(KP(pid))
            if isinstance(data, dict):
                _PROVIDERS[pid] = ProviderRecord(**data)
                # No persisted health, will be recomputed lazily
        # Instances
        inst_ids = r.smembers(INST_INDEX) or []
        for iid in inst_ids:
            data = cache_get_json(KI(iid))
            if isinstance(data, dict):
                _INSTANCES[iid] = InstanceRecord(**data)
        # Defaults (legacy global only; tenant-scoped keys are optional and not scanned here)
        for scope in ["chat"]:
            data = cache_get_json(KD(scope))
            if isinstance(data, dict):
                d = DefaultRecord(**data)
                key = f"{scope}:{d.tenant_id or 'global'}"
                _DEFAULTS[key] = d
    except Exception as exc:
        logger.warning("models_repo.hydrate.failed", extra={"error": str(exc)})


def backfill_to_redis_if_empty() -> None:
    if not _redis_safe():
        return
    try:
        r = get_redis()
        # If index sets are empty, push current memory state
        if not r.exists(PROV_INDEX):
            for pid, rec in _PROVIDERS.items():
                cache_set_json(KP(pid), rec.to_dict())
                r.sadd(PROV_INDEX, pid)
        if not r.exists(INST_INDEX):
            for iid, rec in _INSTANCES.items():
                cache_set_json(KI(iid), rec.to_dict())
                r.sadd(INST_INDEX, iid)
        # Defaults
        for scope, rec in _DEFAULTS.items():
            if r.get(KD(scope)) is None:
                cache_set_json(KD(scope), rec.to_dict())
    except Exception as exc:
        logger.warning("models_repo.backfill.failed", extra={"error": str(exc)})


# --------------- Orchestrator sync ---------------


def sync_providers_to_orchestrator():
    try:
        from src.services.orchestrator import get_orchestrator_instance

        orch = get_orchestrator_instance()
        for prov in _PROVIDERS.values():
            try:
                orch.register_llm(
                    name=prov.id,
                    base_url=prov.base_url,
                    model=prov.model,
                    api_key=prov.api_key,
                    tenant_id=prov.tenant_id,
                )
            except Exception as exc:
                logger.warning("models_repo.orch.register.failed", extra={"id": prov.id, "error": str(exc)})
    except Exception as exc:
        logger.warning("models_repo.sync_providers.unavailable", extra={"error": str(exc)})


# --------------- Provider health (cached, best-effort) ---------------
def _http_get(url: str, timeout: float = 1.0) -> tuple[int, Any]:
    try:
        import httpx

        with httpx.Client(timeout=timeout) as http:
            r = http.get(url)
            try:
                body = r.json()
            except Exception:
                body = r.text[:2048]
            return r.status_code, body
    except Exception as exc:
        return 0, str(exc)


def refresh_provider_health(id: str) -> dict[str, Any]:
    rec = _PROVIDERS.get(id)
    if not rec:
        raise KeyError("provider missing")
    base = rec.base_url or ((rec.config or {}).get("base_url") if rec.config else None)
    reachable = False
    status = None
    try:
        if base:
            base = base.rstrip("/")
            # Try OpenAI-compatible /models first
            status, _ = _http_get(base + "/models", timeout=1.0)
            if status == 404:
                # Some providers expose /api/tags (ollama)
                status, _ = _http_get(base.rsplit("/v1", 1)[0] + "/api/tags", timeout=1.0)
            reachable = bool(status and status > 0)
    except Exception:
        reachable = False
    health = {"reachable": reachable, "status": status}
    _PROVIDER_HEALTH[id] = health
    return health


def get_provider_health(id: str) -> dict[str, Any]:
    h = _PROVIDER_HEALTH.get(id)
    if h is None:
        with suppress(Exception):
            return refresh_provider_health(id)
        return {"reachable": False}
    return h


# Convenience read API for external modules


def provider_count() -> int:
    return len(_PROVIDERS)


__all__ = [
    "backfill_to_redis_if_empty",
    "create_instance",
    "create_provider",
    "delete_instance",
    "delete_provider",
    "get_defaults",
    "get_instance",
    "get_provider",
    "get_provider_internal",
    "hydrate_from_redis",
    "list_instances",
    "list_providers",
    "patch_provider",
    "provider_count",
    "set_default",
    "sync_providers_to_orchestrator",
]
