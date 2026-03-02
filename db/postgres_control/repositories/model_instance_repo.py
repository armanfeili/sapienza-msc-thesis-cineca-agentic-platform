"""Repository for model instance operations."""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.postgres_control.database import get_db
from db.postgres_control.models.model_instance import (
    ModelDefault,
    ModelInstance,
    ModelInstanceEvent,
)
from db.postgres_control.models.provider import Provider
from db.redis_cache.client import get_redis, redis_available
from src.models.llm_config import LLMModelConfig

logger = logging.getLogger(__name__)


def _compute_etag(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _instance_to_dict(instance: ModelInstance) -> dict[str, Any]:
    return {
        "id": str(instance.id),
        "tenant_id": instance.tenant_id,
        "instance_name": instance.instance_name,
        "provider_id": str(instance.provider_id),
        "model_id": instance.model_id,
        "model_uri": instance.model_uri,
        "enabled": instance.enabled,
        "loaded": instance.loaded,
        "is_default": instance.is_default,
        "context_window": instance.context_window,
        "modalities": instance.modalities,
        "description": instance.description,
        "parameters": instance.parameters,
        "created_at": instance.created_at.isoformat() if instance.created_at else None,
        "updated_at": instance.updated_at.isoformat() if instance.updated_at else None,
        "etag": instance.etag,
    }


def list_instances(
    tenant_id: str | None = None,
    provider_id: str | None = None,
    loaded: bool | None = None,
    enabled: bool | None = None,
    page_size: int = 100,
    page_token: str | None = None,
) -> tuple[list[dict[str, Any]], str, str | None]:
    db: Session = next(get_db())
    try:
        query = select(ModelInstance)
        filters = []
        if tenant_id is not None:
            filters.append(ModelInstance.tenant_id == tenant_id)
        if provider_id:
            filters.append(ModelInstance.provider_id == provider_id)
        if loaded is not None:
            filters.append(ModelInstance.loaded == loaded)
        if enabled is not None:
            filters.append(ModelInstance.enabled == enabled)
        if filters:
            query = query.where(and_(*filters))
        query = query.order_by(ModelInstance.created_at.desc())
        offset = int(page_token) if page_token else 0
        query = query.offset(offset).limit(page_size)
        instances = db.execute(query).scalars().all()
        instance_dicts = [_instance_to_dict(inst) for inst in instances]
        etag = _compute_etag(json.dumps(instance_dicts, sort_keys=True))
        next_token = str(offset + page_size) if len(instances) == page_size else None
        return instance_dicts, etag, next_token
    finally:
        db.close()


def create_instance(
    provider_id: str,
    instance_name: str,
    model_id: str,
    tenant_id: str | None = None,
    model_uri: str | None = None,
    parameters: dict[str, Any] | None = None,
    context_window: int | None = None,
    modalities: list[str] | None = None,
    description: str | None = None,
    owner_sub: str = "",
    idempotency_key: str | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    db: Session = next(get_db())
    try:
        provider = db.execute(select(Provider).where(Provider.id == provider_id)).scalar_one_or_none()
        if not provider:
            raise ValueError(f"Provider not found: {provider_id}")

        # Check for existing instance with same name (idempotency)
        existing = db.execute(
            select(ModelInstance).where(
                and_(ModelInstance.tenant_id == tenant_id, ModelInstance.instance_name == instance_name)
            )
        ).scalar_one_or_none()

        if existing:
            # Idempotency: return existing instance
            return _instance_to_dict(existing)

        new_instance = ModelInstance(
            tenant_id=tenant_id,
            instance_name=instance_name,
            provider_id=provider_id,
            model_id=model_id,
            model_uri=model_uri,
            enabled=True,
            loaded=True,
            context_window=context_window,
            modalities=modalities,
            description=description,
            parameters=parameters or {},
            etag=_compute_etag(f"{instance_name}{model_id}{datetime.utcnow().isoformat()}"),
        )
        db.add(new_instance)
        db.flush()
        event = ModelInstanceEvent(
            instance_id=new_instance.id,
            event_type="loaded",
            event_json={"instance_name": instance_name},
            actor_sub=owner_sub,
            trace_id=trace_id,
        )
        db.add(event)
        db.commit()
        return _instance_to_dict(new_instance)
    except IntegrityError as exc:
        db.rollback()
        raise ValueError(f"Instance '{instance_name}' already exists") from exc
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_instance(instance_id: str) -> dict[str, Any] | None:
    """Get instance by ID (UUID) or name.

    Args:
        instance_id: Either a UUID string or instance name

    Returns:
        Instance dict if found, None otherwise
    """
    db: Session = next(get_db())
    try:
        # Try UUID lookup first
        try:
            uuid_obj = uuid.UUID(instance_id)
            instance = db.execute(select(ModelInstance).where(ModelInstance.id == uuid_obj)).scalar_one_or_none()
        except (ValueError, AttributeError):
            # Fall back to name lookup if not a valid UUID
            instance = db.execute(
                select(ModelInstance).where(ModelInstance.instance_name == instance_id)
            ).scalar_one_or_none()

        return _instance_to_dict(instance) if instance else None
    finally:
        db.close()


def delete_instance(instance_id: str, owner_sub: str = "", trace_id: str | None = None) -> bool:
    db: Session = next(get_db())
    try:
        instance = db.execute(
            select(ModelInstance).where(ModelInstance.id == uuid.UUID(instance_id))
        ).scalar_one_or_none()
        if not instance:
            return False
        event = ModelInstanceEvent(
            instance_id=instance.id,
            event_type="unloaded",
            event_json={"instance_name": instance.instance_name},
            actor_sub=owner_sub,
            trace_id=trace_id,
        )
        db.add(event)
        db.delete(instance)
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_default(scope: str = "global", tenant_id: str | None = None) -> LLMModelConfig | None:
    """Get default model instance with provider details for a given scope.
    
    Enforces single-default invariant: raises ValueError if multiple defaults exist
    for the same (scope, tenant_id) combination.
    
    Returns LLMModelConfig with:
    - instance_name: Human-readable instance name (canonical alias)
    - provider_model_id: Provider-specific model identifier (e.g., 'phi3:mini')
    - base_url: Provider base URL for API calls
    - provider_name: Provider name (e.g., 'Local Ollama')
    - provider_id: UUID of the provider
    - source: Always "db_default" (configuration source)
    
    Raises:
        ValueError: If multiple defaults exist for the same (scope, tenant_id)
    
    Example:
        >>> config = get_default(scope="global", tenant_id=None)
        >>> config.instance_name
        'phi3-mini'
        >>> config.provider_model_id
        'phi3:mini'
    """
    db: Session = next(get_db())
    try:
        # Build WHERE clause with NULL-safe comparison for tenant_id
        where_clause = ModelDefault.scope == scope
        if tenant_id is None:
            where_clause = and_(where_clause, ModelDefault.tenant_id.is_(None))
        else:
            where_clause = and_(where_clause, ModelDefault.tenant_id == tenant_id)

        # Check for multiple defaults (single-default invariant)
        defaults = db.execute(select(ModelDefault).where(where_clause)).scalars().all()
        if len(defaults) > 1:
            logger.error(
                "model_instance_repo.get_default.multiple_defaults",
                extra={
                    "scope": scope,
                    "tenant_id": tenant_id,
                    "count": len(defaults),
                    "instance_ids": [str(d.instance_id) for d in defaults]
                }
            )
            raise ValueError(
                f"Multiple default models configured for scope='{scope}', tenant_id='{tenant_id}'. "
                f"Found {len(defaults)} defaults. Database must have exactly one default per scope."
            )
        
        if not defaults:
            return None
        
        default = defaults[0]
        instance = db.execute(select(ModelInstance).where(ModelInstance.id == default.instance_id)).scalar_one_or_none()
        if not instance:
            return None
        
        # Join with provider to get base_url and other provider details
        provider = db.execute(select(Provider).where(Provider.id == instance.provider_id)).scalar_one_or_none()
        if not provider:
            logger.warning(
                "model_instance_repo.get_default.provider_missing",
                extra={"instance_id": str(instance.id), "provider_id": str(instance.provider_id)}
            )
            return None
        
        # Return type-safe LLMModelConfig instead of dict
        return LLMModelConfig(
            instance_id=str(instance.id),
            instance_name=instance.instance_name,
            provider_model_id=instance.model_id,
            base_url=provider.base_url,
            provider_name=provider.name,
            provider_id=str(instance.provider_id),
            source="db_default"
        )
    finally:
        db.close()


def set_default(
    instance_id: str, scope: str = "global", tenant_id: str | None = None, owner_sub: str = ""
) -> dict[str, Any]:
    db: Session = next(get_db())
    try:
        uuid_obj = uuid.UUID(instance_id)
        instance = db.execute(select(ModelInstance).where(ModelInstance.id == uuid_obj)).scalar_one_or_none()
        if not instance:
            raise ValueError(f"Instance not found: {instance_id}")
        if not instance.enabled:
            raise ValueError(f"Instance is not enabled: {instance_id}")

        # Build WHERE clause with NULL-safe comparison for tenant_id
        where_clause = ModelDefault.scope == scope
        if tenant_id is None:
            where_clause = and_(where_clause, ModelDefault.tenant_id.is_(None))
        else:
            where_clause = and_(where_clause, ModelDefault.tenant_id == tenant_id)

        existing = db.execute(select(ModelDefault).where(where_clause)).scalar_one_or_none()
        etag_val = _compute_etag(f"{scope}{tenant_id}{instance_id}{datetime.utcnow().isoformat()}")
        if existing:
            existing.instance_id = uuid.UUID(instance_id)
            existing.updated_at = datetime.utcnow()
            existing.etag = etag_val
        else:
            new_default = ModelDefault(
                scope=scope,
                tenant_id=tenant_id,
                instance_id=uuid.UUID(instance_id),
                etag=etag_val,
            )
            db.add(new_default)
        db.commit()
        return {
            "instance_id": str(instance.id),
            "instance_name": instance.instance_name,
            "etag": etag_val,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def acquire_instance_lock(instance_id: str, ttl: int = 15) -> bool:
    if not redis_available():
        return True
    try:
        redis = get_redis()
        return redis.set(f"models:instances:lock:{instance_id}", "1", nx=True, ex=ttl) or False
    except Exception:
        return True


def release_instance_lock(instance_id: str) -> None:
    if not redis_available():
        return
    try:
        redis = get_redis()
        redis.delete(f"models:instances:lock:{instance_id}")
    except Exception:
        pass


def record_test_event(
    instance_id: str,
    provider_name: str,
    success: bool,
    owner_sub: str = "",
    trace_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    db: Session = next(get_db())
    try:
        event = ModelInstanceEvent(
            instance_id=uuid.UUID(instance_id),
            event_type="tested",
            event_json={"provider_name": provider_name, "success": success, "details": details or {}},
            actor_sub=owner_sub,
            trace_id=trace_id,
        )
        db.add(event)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
