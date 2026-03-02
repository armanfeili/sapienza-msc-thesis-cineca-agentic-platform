"""PostgreSQL repository for Provider management (authoritative source).

This module provides CRUD operations for providers with:
- PostgreSQL as authoritative source (all writes go to Postgres first)
- Redis as cache layer (short TTL, invalidated on writes)
- Secret encryption/decryption for api_keys
- Audit event logging for all mutations
- Multi-tenant scope support (global + tenant-scoped defaults)

Storage layers:
1. PostgreSQL: providers, provider_secrets, provider_defaults, provider_audit_events
2. Redis: Cache keys with TTLs (providers:by_id:{id}, providers:list:*, providers:default:*, providers:health:{id})

Redaction policy:
- API responses NEVER include raw api_key
- has_api_key boolean indicator provided instead
- config.headers.authorization, config.auth.token are masked
"""

from __future__ import annotations

import hashlib
import json
import logging
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from cryptography.fernet import Fernet
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.postgres_control.database import get_db
from db.postgres_control.models.provider import (
    Provider,
    ProviderAuditEvent,
    ProviderDefault,
    ProviderSecret,
)
from db.redis_cache.client import (
    cache_delete,
    cache_get_json,
    cache_set_json,
    get_redis,
    redis_available,
)
from src.config import settings

logger = logging.getLogger(__name__)

# Redis key templates
REDIS_PROVIDER_BY_ID = "providers:by_id:{}"
REDIS_PROVIDER_LIST = "providers:list:{}:{}"  # page_size:page_token
REDIS_PROVIDER_DEFAULT = "providers:default:{}"  # scope:tenant_id or 'global'
REDIS_PROVIDER_HEALTH = "providers:health:{}"
REDIS_PROVIDER_ETAG = "providers:etag:{}"
REDIS_LIST_ETAG = "providers:etag:list:{}"

# Cache TTLs (seconds)
TTL_PROVIDER = 300  # 5 minutes
TTL_LIST = 60  # 1 minute
TTL_DEFAULT = 600  # 10 minutes
TTL_HEALTH = 3600  # 1 hour (no background scheduler to refresh)
TTL_ETAG = 300  # 5 minutes

# Encryption key for api_key (should be stored in env/vault, not hardcoded)
# In production, use settings.PROVIDER_SECRET_KEY or a proper vault
_ENCRYPTION_KEY = None


def _get_encryption_key() -> bytes:
    """Get or generate encryption key for provider secrets."""
    global _ENCRYPTION_KEY
    if _ENCRYPTION_KEY is None:
        key_str = getattr(settings, "PROVIDER_SECRET_KEY", None)
        if key_str:
            _ENCRYPTION_KEY = key_str.encode() if isinstance(key_str, str) else key_str
        else:
            # Generate a key for development (INSECURE for production!)
            logger.warning("provider_repo.encryption.no_key - generating ephemeral key (INSECURE for production)")
            _ENCRYPTION_KEY = Fernet.generate_key()
    return _ENCRYPTION_KEY


def _encrypt_secret(plaintext: str | None) -> str | None:
    """Encrypt a secret value (e.g., api_key) for storage."""
    if not plaintext:
        return None
    try:
        f = Fernet(_get_encryption_key())
        encrypted = f.encrypt(plaintext.encode())
        return encrypted.decode()
    except Exception as exc:
        logger.error("provider_repo.encrypt.failed", extra={"error": str(exc)})
        raise


def _decrypt_secret(ciphertext: str | None) -> str | None:
    """Decrypt a secret value from storage."""
    if not ciphertext:
        return None
    try:
        f = Fernet(_get_encryption_key())
        decrypted = f.decrypt(ciphertext.encode())
        return decrypted.decode()
    except Exception as exc:
        logger.error("provider_repo.decrypt.failed", extra={"error": str(exc)})
        return None


def _redact_secrets(data: dict[str, Any]) -> dict[str, Any]:
    """Redact secrets in provider data for API responses.

    Masks:
    - api_key → None (has_api_key boolean provided separately)
    - config.headers.authorization → "***"
    - config.auth.token → "***"
    """
    redacted = dict(data)

    # Top-level api_key should never appear (stored separately), but mask if present
    if "api_key" in redacted:
        redacted["api_key"] = None

    # Mask secrets in config.headers and config.auth
    config = redacted.get("config_json") or redacted.get("config")
    if isinstance(config, dict):
        headers = config.get("headers")
        if isinstance(headers, dict):
            for key in list(headers.keys()):
                if key.lower() in ("authorization", "x-api-key"):
                    headers[key] = "***"

        auth = config.get("auth")
        if isinstance(auth, dict):
            for key in list(auth.keys()):
                if key.lower() in ("token", "api_key", "password"):
                    auth[key] = "***"

    return redacted


def _redis_invalidate_provider(provider_id: str) -> None:
    """Invalidate all Redis cache keys related to a provider."""
    if not redis_available():
        return

    try:
        r = get_redis()
        # Invalidate by_id cache
        cache_delete(REDIS_PROVIDER_BY_ID.format(provider_id))
        # Invalidate ETags
        cache_delete(REDIS_PROVIDER_ETAG.format(provider_id))
        # Invalidate all list caches (brute force: delete all matching patterns)
        for key in r.scan_iter(match=REDIS_PROVIDER_LIST.format("*", "*")):
            cache_delete(key)
        for key in r.scan_iter(match=REDIS_LIST_ETAG.format("*")):
            cache_delete(key)
        # Invalidate health
        cache_delete(REDIS_PROVIDER_HEALTH.format(provider_id))
    except Exception as exc:
        logger.warning("provider_repo.redis.invalidate.failed", extra={"provider_id": provider_id, "error": str(exc)})


def _redis_invalidate_defaults(scope: str = "chat", tenant_id: str | None = None) -> None:
    """Invalidate default-related Redis keys."""
    if not redis_available():
        return

    try:
        key_suffix = f"{scope}:{tenant_id or 'global'}"
        cache_delete(REDIS_PROVIDER_DEFAULT.format(key_suffix))
        # Also invalidate global default if tenant-specific was changed
        if tenant_id:
            cache_delete(REDIS_PROVIDER_DEFAULT.format(f"{scope}:global"))
    except Exception as exc:
        logger.warning("provider_repo.redis.invalidate_defaults.failed", extra={"error": str(exc)})


def _compute_etag(data: Any) -> str:
    """Compute ETag hash for caching (deterministic)."""
    if isinstance(data, (list, dict)):
        serialized = json.dumps(data, sort_keys=True, default=str)
    else:
        serialized = str(data)
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]


def _audit_event(
    db: Session,
    action: str,
    provider_id: str | None,
    actor: str,
    tenant_id: str | None = None,
    payload: dict[str, Any] | None = None,
    trace_id: str | None = None,
    event_id: str | None = None,
) -> ProviderAuditEvent:
    """Record an audit event for provider changes."""
    event = ProviderAuditEvent(
        provider_id=provider_id,
        actor=actor,
        action=action,
        tenant_id=tenant_id,
        payload=payload,
        trace_id=trace_id,
        event_id=event_id,
    )
    db.add(event)
    db.flush()
    return event


# ==================== Validation ====================


def _validate_tenant_id(tenant_id: str | None) -> str | None:
    """Validate and normalize tenant_id.

    Rules:
    - tenant_id cannot be the string "global" (use None for global scope)
    - None is valid and represents global scope
    - Any other string is valid as a tenant identifier

    Raises:
        ValueError: If tenant_id is the string "global"
    """
    if tenant_id == "global":
        raise ValueError(
            "tenant_id cannot be 'global'; use null/None for global scope. "
            "The string 'global' is reserved and should not be used as a tenant identifier."
        )
    return tenant_id


# ==================== CRUD Operations ====================


def create_provider(
    name: str,
    type: str,
    base_url: str | None,
    model: str | None = None,
    api_key: str | None = None,
    tenant_id: str | None = None,
    config: dict[str, Any] | None = None,
    actor: str = "api",
    trace_id: str | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    """Create a new provider (PostgreSQL authoritative).

    Steps:
    1. Validate tenant_id (prevent "global" string)
    2. Insert into providers table
    3. Insert encrypted api_key into provider_secrets (if provided)
    4. Log audit event
    5. Invalidate Redis caches
    6. Return redacted provider dict
    """
    # Validate tenant_id
    tenant_id = _validate_tenant_id(tenant_id)

    db: Session = next(get_db())
    provider_id = name  # Use name as ID for simplicity

    try:
        # Check for existing provider (unique constraint enforcement)
        existing = db.execute(
            select(Provider).where(and_(Provider.tenant_id == tenant_id, Provider.name == name))
        ).scalar_one_or_none()

        if existing:
            raise ValueError(f"Provider '{name}' already exists for tenant '{tenant_id or 'global'}'")

        # Create provider record
        provider = Provider(
            id=provider_id,
            name=name,
            type=type,
            base_url=base_url,
            model=model,
            tenant_id=tenant_id,
            config_json=config,
            has_api_key=bool(api_key),
        )
        db.add(provider)
        db.flush()

        # Store encrypted api_key if provided
        if api_key:
            encrypted = _encrypt_secret(api_key)
            secret = ProviderSecret(
                provider_id=provider_id,
                api_key_encrypted=encrypted,
            )
            db.add(secret)
            db.flush()

        # Audit event
        _audit_event(
            db,
            action="provider.register",
            provider_id=provider_id,
            actor=actor,
            tenant_id=tenant_id,
            payload={
                "name": name,
                "type": type,
                "base_url": base_url,
                "model": model,
                "has_api_key": bool(api_key),
                "config": config,
            },
            trace_id=trace_id,
            event_id=event_id,
        )

        db.commit()

        # Invalidate Redis caches
        _redis_invalidate_provider(provider_id)

        # Return redacted dict
        result = {
            "id": provider.id,
            "name": provider.name,
            "type": provider.type,
            "base_url": provider.base_url,
            "model": provider.model,
            "tenant_id": provider.tenant_id,
            "config_json": provider.config_json,
            "has_api_key": provider.has_api_key,
            "created_at": provider.created_at.isoformat(),
            "updated_at": provider.updated_at.isoformat(),
        }

        return _redact_secrets(result)

    except IntegrityError as exc:
        db.rollback()
        logger.error("provider_repo.create.integrity_error", extra={"name": name, "error": str(exc)})
        raise ValueError(f"Provider '{name}' already exists") from exc
    except Exception as exc:
        db.rollback()
        logger.error("provider_repo.create.failed", extra={"name": name, "error": str(exc)})
        raise
    finally:
        db.close()


def list_providers(tenant_id: str | None = None) -> list[dict[str, Any]]:
    """List all providers (admin sees all, filtered by tenant if specified).

    Returns redacted provider dicts (no secrets).
    Caches result in Redis with short TTL.
    """
    # Try Redis cache first
    cache_key = REDIS_PROVIDER_LIST.format("all", tenant_id or "global")
    if redis_available():
        cached = cache_get_json(cache_key)
        if cached:
            return cached

    db: Session = next(get_db())
    try:
        query = select(Provider)
        if tenant_id:
            # Filter to global + specified tenant
            query = query.where(or_(Provider.tenant_id is None, Provider.tenant_id == tenant_id))

        providers = db.execute(query).scalars().all()

        result = []
        for p in providers:
            data = {
                "id": p.id,
                "name": p.name,
                "type": p.type,
                "base_url": p.base_url,
                "model": p.model,
                "tenant_id": p.tenant_id,
                "config_json": p.config_json,
                "has_api_key": p.has_api_key,
                "created_at": p.created_at.isoformat(),
                "updated_at": p.updated_at.isoformat(),
            }
            result.append(_redact_secrets(data))

        # Cache in Redis
        if redis_available():
            with suppress(Exception):
                cache_set_json(cache_key, result, ex=TTL_LIST)

        return result

    except Exception as exc:
        logger.error("provider_repo.list.failed", extra={"error": str(exc)})
        return []
    finally:
        db.close()


def get_provider(provider_id: str, include_secrets: bool = False) -> dict[str, Any] | None:
    """Get provider by ID (redacted by default).

    Args:
        provider_id: Provider identifier
        include_secrets: If True, decrypt and include api_key (internal use only, NEVER expose via API)

    Returns:
        Redacted provider dict (or with secrets if include_secrets=True)
    """
    # Try Redis cache first (only for redacted version)
    if not include_secrets and redis_available():
        cache_key = REDIS_PROVIDER_BY_ID.format(provider_id)
        cached = cache_get_json(cache_key)
        if cached:
            return cached

    db: Session = next(get_db())
    try:
        provider = db.execute(select(Provider).where(Provider.id == provider_id)).scalar_one_or_none()

        if not provider:
            return None

        data = {
            "id": provider.id,
            "name": provider.name,
            "type": provider.type,
            "base_url": provider.base_url,
            "model": provider.model,
            "tenant_id": provider.tenant_id,
            "config_json": provider.config_json,
            "has_api_key": provider.has_api_key,
            "created_at": provider.created_at.isoformat(),
            "updated_at": provider.updated_at.isoformat(),
        }

        # Include decrypted api_key if requested (internal use only)
        if include_secrets:
            secret = db.execute(
                select(ProviderSecret).where(ProviderSecret.provider_id == provider_id)
            ).scalar_one_or_none()
            if secret and secret.api_key_encrypted:
                data["api_key"] = _decrypt_secret(secret.api_key_encrypted)
            else:
                data["api_key"] = None
            return data  # Return with secrets (no redaction)

        # Redact and cache
        result = _redact_secrets(data)
        if redis_available():
            with suppress(Exception):
                cache_set_json(REDIS_PROVIDER_BY_ID.format(provider_id), result, ex=TTL_PROVIDER)

        return result

    except Exception as exc:
        logger.error("provider_repo.get.failed", extra={"provider_id": provider_id, "error": str(exc)})
        return None
    finally:
        db.close()


def patch_provider(
    provider_id: str,
    base_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    tenant_id: str | None = None,
    config: dict[str, Any] | None = None,
    actor: str = "api",
    trace_id: str | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    """Patch/update provider (merge config, update fields).

    Config is deep-merged (not replaced). api_key is updated in provider_secrets if provided.
    """
    # Validate tenant_id if provided
    if tenant_id is not None:
        tenant_id = _validate_tenant_id(tenant_id)

    db: Session = next(get_db())
    try:
        provider = db.execute(select(Provider).where(Provider.id == provider_id)).scalar_one_or_none()

        if not provider:
            raise ValueError(f"Provider '{provider_id}' not found")

        # Track changes for audit
        before = {
            "base_url": provider.base_url,
            "model": provider.model,
            "tenant_id": provider.tenant_id,
            "config_json": provider.config_json,
        }

        # Apply updates
        if base_url is not None:
            provider.base_url = base_url
        if model is not None:
            provider.model = model
        if tenant_id is not None:
            provider.tenant_id = tenant_id
        if config is not None:
            # Deep merge config
            existing_config = provider.config_json or {}
            merged = {**existing_config, **config}
            provider.config_json = merged

        # Update api_key if provided
        if api_key is not None:
            provider.has_api_key = bool(api_key)
            encrypted = _encrypt_secret(api_key) if api_key else None

            # Upsert ProviderSecret
            secret = db.execute(
                select(ProviderSecret).where(ProviderSecret.provider_id == provider_id)
            ).scalar_one_or_none()

            if secret:
                secret.api_key_encrypted = encrypted
                secret.updated_at = datetime.now(UTC)
            elif encrypted:
                secret = ProviderSecret(
                    provider_id=provider_id,
                    api_key_encrypted=encrypted,
                )
                db.add(secret)

        provider.updated_at = datetime.now(UTC)
        db.flush()

        # Audit event
        after = {
            "base_url": provider.base_url,
            "model": provider.model,
            "tenant_id": provider.tenant_id,
            "config_json": provider.config_json,
        }
        _audit_event(
            db,
            action="provider.patch",
            provider_id=provider_id,
            actor=actor,
            tenant_id=provider.tenant_id,
            payload={"before": before, "after": after, "has_api_key_updated": api_key is not None},
            trace_id=trace_id,
            event_id=event_id,
        )

        db.commit()

        # Invalidate Redis caches
        _redis_invalidate_provider(provider_id)

        # Return redacted result
        result = {
            "id": provider.id,
            "name": provider.name,
            "type": provider.type,
            "base_url": provider.base_url,
            "model": provider.model,
            "tenant_id": provider.tenant_id,
            "config_json": provider.config_json,
            "has_api_key": provider.has_api_key,
            "created_at": provider.created_at.isoformat(),
            "updated_at": provider.updated_at.isoformat(),
        }

        return _redact_secrets(result)

    except Exception as exc:
        db.rollback()
        logger.error("provider_repo.patch.failed", extra={"provider_id": provider_id, "error": str(exc)})
        raise
    finally:
        db.close()


def delete_provider(
    provider_id: str,
    actor: str = "api",
    trace_id: str | None = None,
    event_id: str | None = None,
) -> bool:
    """Delete provider (CASCADE deletes secrets and clears defaults).

    Policy: Auto-clear any defaults pointing to this provider before deletion.
    """
    db: Session = next(get_db())
    try:
        provider = db.execute(select(Provider).where(Provider.id == provider_id)).scalar_one_or_none()

        if not provider:
            return False

        # Clear any defaults referencing this provider (all scopes/tenants)
        defaults = db.execute(select(ProviderDefault).where(ProviderDefault.provider_id == provider_id)).scalars().all()

        for default in defaults:
            db.delete(default)
            _redis_invalidate_defaults(default.scope, default.tenant_id)

        # Delete provider (CASCADE will delete provider_secrets)
        db.delete(provider)
        db.flush()

        # Audit event
        _audit_event(
            db,
            action="provider.delete",
            provider_id=provider_id,
            actor=actor,
            tenant_id=provider.tenant_id,
            payload={"name": provider.name, "type": provider.type, "defaults_cleared": len(defaults)},
            trace_id=trace_id,
            event_id=event_id,
        )

        db.commit()

        # Invalidate Redis caches
        _redis_invalidate_provider(provider_id)

        return True

    except Exception as exc:
        db.rollback()
        logger.error("provider_repo.delete.failed", extra={"provider_id": provider_id, "error": str(exc)})
        raise
    finally:
        db.close()


# ==================== Defaults Management ====================


def set_provider_default(
    scope: str,
    provider_id: str,
    tenant_id: str | None = None,
    actor: str = "api",
    trace_id: str | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    """Set provider as default for scope/tenant.

    Upserts provider_defaults row. Invalidates Redis default cache.
    """
    db: Session = next(get_db())
    try:
        # Verify provider exists
        provider = db.execute(select(Provider).where(Provider.id == provider_id)).scalar_one_or_none()

        if not provider:
            raise ValueError(f"Provider '{provider_id}' not found")

        tenant_key = tenant_id or "global"

        # Upsert default
        existing = db.execute(
            select(ProviderDefault).where(and_(ProviderDefault.scope == scope, ProviderDefault.tenant_id == tenant_key))
        ).scalar_one_or_none()

        if existing:
            existing.provider_id = provider_id
            existing.updated_at = datetime.now(UTC)
            default = existing
        else:
            default = ProviderDefault(
                scope=scope,
                tenant_id=tenant_key,
                provider_id=provider_id,
            )
            db.add(default)

        db.flush()

        # Audit event
        _audit_event(
            db,
            action="provider.set_default",
            provider_id=provider_id,
            actor=actor,
            tenant_id=tenant_id,
            payload={"scope": scope, "tenant_id": tenant_key, "provider_id": provider_id},
            trace_id=trace_id,
            event_id=event_id,
        )

        db.commit()

        # Invalidate Redis defaults cache
        _redis_invalidate_defaults(scope, tenant_id)

        return {
            "scope": default.scope,
            "tenant_id": default.tenant_id,
            "provider_id": default.provider_id,
            "updated_at": default.updated_at.isoformat(),
        }

    except Exception as exc:
        db.rollback()
        logger.error(
            "provider_repo.set_default.failed", extra={"scope": scope, "provider_id": provider_id, "error": str(exc)}
        )
        raise
    finally:
        db.close()


def get_provider_default(scope: str, tenant_id: str | None = None) -> dict[str, Any] | None:
    """Get default provider for scope/tenant.

    Resolution precedence:
    1. Tenant-scoped default (if tenant_id provided)
    2. Global default
    3. None
    """
    # Try Redis cache first
    cache_key = REDIS_PROVIDER_DEFAULT.format(f"{scope}:{tenant_id or 'global'}")
    if redis_available():
        cached = cache_get_json(cache_key)
        if cached:
            return cached

    db: Session = next(get_db())
    try:
        # Try tenant-specific first
        if tenant_id:
            tenant_default = db.execute(
                select(ProviderDefault).where(
                    and_(ProviderDefault.scope == scope, ProviderDefault.tenant_id == tenant_id)
                )
            ).scalar_one_or_none()

            if tenant_default:
                result = {
                    "scope": tenant_default.scope,
                    "tenant_id": tenant_default.tenant_id,
                    "provider_id": tenant_default.provider_id,
                    "updated_at": tenant_default.updated_at.isoformat(),
                }
                # Cache result
                if redis_available():
                    with suppress(Exception):
                        cache_set_json(cache_key, result, ex=TTL_DEFAULT)
                return result

        # Fallback to global default
        global_default = db.execute(
            select(ProviderDefault).where(and_(ProviderDefault.scope == scope, ProviderDefault.tenant_id == "global"))
        ).scalar_one_or_none()

        if global_default:
            result = {
                "scope": global_default.scope,
                "tenant_id": global_default.tenant_id,
                "provider_id": global_default.provider_id,
                "updated_at": global_default.updated_at.isoformat(),
            }
            # Cache result
            if redis_available():
                with suppress(Exception):
                    cache_set_json(cache_key, result, ex=TTL_DEFAULT)
            return result

        return None

    except Exception as exc:
        logger.error(
            "provider_repo.get_default.failed", extra={"scope": scope, "tenant_id": tenant_id, "error": str(exc)}
        )
        return None
    finally:
        db.close()


# ==================== Health Management ====================


def set_provider_health(provider_id: str, health: dict[str, Any]) -> None:
    """Store provider health snapshot in Redis (short TTL, non-authoritative)."""
    if not redis_available():
        return

    try:
        cache_key = REDIS_PROVIDER_HEALTH.format(provider_id)
        cache_set_json(cache_key, health, ex=TTL_HEALTH)
    except Exception as exc:
        logger.warning("provider_repo.set_health.failed", extra={"provider_id": provider_id, "error": str(exc)})


def get_provider_health(provider_id: str) -> dict[str, Any] | None:
    """Get cached provider health (Redis only, no persistence)."""
    if not redis_available():
        return None

    try:
        cache_key = REDIS_PROVIDER_HEALTH.format(provider_id)
        return cache_get_json(cache_key)
    except Exception as exc:
        logger.warning("provider_repo.get_health.failed", extra={"provider_id": provider_id, "error": str(exc)})
        return None


# ==================== ETag Management ====================


def compute_provider_etag(provider_id: str) -> str:
    """Compute ETag for a provider (based on updated_at + redacted fields)."""
    provider = get_provider(provider_id, include_secrets=False)
    if not provider:
        return ""
    return _compute_etag(provider)


def compute_list_etag(providers: list[dict[str, Any]]) -> str:
    """Compute ETag for provider list (deterministic hash)."""
    return _compute_etag(providers)


__all__ = [
    "compute_list_etag",
    "compute_provider_etag",
    "create_provider",
    "delete_provider",
    "get_provider",
    "get_provider_default",
    "get_provider_health",
    "list_providers",
    "patch_provider",
    "set_provider_default",
    "set_provider_health",
]
