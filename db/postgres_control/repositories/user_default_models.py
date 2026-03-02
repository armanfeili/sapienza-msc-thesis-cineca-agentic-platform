"""
User Default Models Repository

Manages per-user default model preferences with tenant scoping and precedence resolution.

Resolution Precedence (highest to lowest):
1. User default (user_id + tenant_id) - Specific user in specific tenant
2. Tenant default (tenant_id only) - Tenant-wide default from model_instances
3. Global default (tenant_id=None) - System-wide default from model_instances
4. 404 Not Found - No default configured at any level

Example:
    # Get user's default with automatic precedence
    default = user_default_repo.get_user_default(user_id="auth0|123", tenant_id="acme-corp")

    # Set user's default
    result = user_default_repo.set_user_default(
        user_id="auth0|123",
        instance_id="6491b020-bbe3-47fe-991e-e7c21a15260c",
        tenant_id="acme-corp"
    )
"""
from __future__ import annotations

import hashlib
import logging
import uuid as uuid_lib
from datetime import UTC, datetime

from sqlalchemy import and_, delete as sql_delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from db.postgres_control.database import get_db
from db.postgres_control.models.model_instance import ModelInstance
from db.postgres_control.models.user_default_model import UserDefaultModel

logger = logging.getLogger(__name__)


class UserDefaultModelRepo:
    """Repository for user-scoped default model preferences."""

    @staticmethod
    def _compute_etag(user_id: str, tenant_id: str | None, instance_id: str, updated_at: datetime) -> str:
        """
        Compute ETag for user default.

        Args:
            user_id: User subject
            tenant_id: Tenant ID (can be None)
            instance_id: Model instance ID
            updated_at: Last update timestamp

        Returns:
            ETag string for HTTP cache validation
        """
        # Include all relevant fields in ETag computation
        data = f"{user_id}:{tenant_id or 'global'}:{instance_id}:{updated_at.isoformat()}"
        hash_val = hashlib.sha256(data.encode()).hexdigest()[:16]
        return hash_val

    @staticmethod
    def get_user_default(user_id: str, tenant_id: str | None = None) -> dict | None:
        """
        Get user's default model preference.

        Returns only user-scoped defaults from user_default_models table.
        Does NOT implement fallback precedence (that's done at the route level).

        Args:
            user_id: User subject from JWT
            tenant_id: Tenant ID for scoping (None = global user default)

        Returns:
            Dict with user default info, or None if not set

        Example:
            >>> default = get_user_default("auth0|123", "acme-corp")
            >>> if default:
            >>>     print(default['chat_instance_id'])
        """
        db: Session = next(get_db())
        try:
            # Build query with JOIN to get instance details
            query = select(UserDefaultModel).join(UserDefaultModel.instance).where(UserDefaultModel.user_id == user_id)

            # Handle tenant_id filtering (including None)
            if tenant_id is None:
                query = query.where(UserDefaultModel.tenant_id.is_(None))
            else:
                query = query.where(UserDefaultModel.tenant_id == tenant_id)

            # Use joinedload to eagerly load the instance relationship
            query = query.options(joinedload(UserDefaultModel.instance))

            default = db.execute(query).scalar_one_or_none()

            if not default:
                return None

            # Validate instance is loaded and enabled
            if not default.instance:
                logger.warning(f"User default {default.id} references missing instance {default.chat_instance_id}")
                return None

            if not default.instance.enabled:
                logger.warning(f"User default {default.id} references disabled instance {default.chat_instance_id}")
                return None

            # Build normalized response dict (matches model_instance_repo.get_default format)
            return {
                "instance_id": str(default.chat_instance_id),
                "instance_name": default.instance.instance_name,
                "provider_id": str(default.instance.provider_id),
                "model_id": default.instance.model_id,
                "etag": default.etag,
                # Legacy fields for backward compatibility
                "id": str(default.id),
                "user_id": default.user_id,
                "tenant_id": default.tenant_id,
                "chat_instance_id": str(default.chat_instance_id),
                "created_at": default.created_at.isoformat() if default.created_at else None,
                "updated_at": default.updated_at.isoformat() if default.updated_at else None,
                "created_by": default.created_by,
            }

        except Exception as e:
            logger.error(f"Error getting user default: {e}")
            raise
        finally:
            db.close()

    @staticmethod
    def set_user_default(
        user_id: str, instance_id: str, tenant_id: str | None = None, created_by: str | None = None
    ) -> dict:
        """
        Set or update user's default model preference.

        Uses SQLAlchemy to handle create/update logic.

        Args:
            user_id: User subject from JWT
            instance_id: Model instance ID to set as default
            tenant_id: Tenant ID for scoping (None = global user default)
            created_by: User subject who is setting this default

        Returns:
            Dict with updated default info

        Raises:
            ValueError: If instance_id is invalid or instance not found
            IntegrityError: If database constraint violation

        Example:
            >>> default = set_user_default(
            >>>     user_id="auth0|123",
            >>>     instance_id="abc-123",
            >>>     tenant_id="acme-corp",
            >>>     created_by="auth0|123"
            >>> )
            >>> print(default['etag'])
        """
        db: Session = next(get_db())
        try:
            # Verify instance exists
            instance = db.execute(select(ModelInstance).where(ModelInstance.id == instance_id)).scalar_one_or_none()

            if not instance:
                raise ValueError(f"Model instance not found: {instance_id}")

            # Check if default already exists
            existing = db.execute(
                select(UserDefaultModel).where(
                    and_(
                        UserDefaultModel.user_id == user_id,
                        UserDefaultModel.tenant_id == tenant_id if tenant_id else UserDefaultModel.tenant_id.is_(None),
                    )
                )
            ).scalar_one_or_none()

            if existing:
                # Update existing
                existing.chat_instance_id = instance_id
                existing.updated_at = datetime.now(UTC)
                existing.etag = uuid_lib.uuid4().hex
                db.commit()
                db.refresh(existing)

                return {
                    "id": str(existing.id),
                    "user_id": existing.user_id,
                    "tenant_id": existing.tenant_id,
                    "chat_instance_id": str(existing.chat_instance_id),
                    "instance_id": str(existing.chat_instance_id),  # Alias for compatibility
                    "instance_name": instance.instance_name,  # Add instance name from looked-up instance
                    "provider_id": str(instance.provider_id),
                    "model_id": instance.model_id,
                    "created_at": existing.created_at.isoformat(),
                    "updated_at": existing.updated_at.isoformat(),
                    "created_by": existing.created_by,
                    "etag": existing.etag,
                }
            else:
                # Create new
                new_default = UserDefaultModel(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    chat_instance_id=instance_id,
                    created_by=created_by or user_id,
                )
                db.add(new_default)
                db.commit()
                db.refresh(new_default)

                return {
                    "id": str(new_default.id),
                    "user_id": new_default.user_id,
                    "tenant_id": new_default.tenant_id,
                    "chat_instance_id": str(new_default.chat_instance_id),
                    "instance_id": str(new_default.chat_instance_id),  # Alias for compatibility
                    "instance_name": instance.instance_name,  # Add instance name from looked-up instance
                    "provider_id": str(instance.provider_id),
                    "model_id": instance.model_id,
                    "created_at": new_default.created_at.isoformat(),
                    "updated_at": new_default.updated_at.isoformat(),
                    "created_by": new_default.created_by,
                    "etag": new_default.etag,
                }

        except IntegrityError as e:
            db.rollback()
            logger.error(f"Integrity error setting user default: {e}")
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error setting user default: {e}")
            raise
        finally:
            db.close()

    @staticmethod
    def delete_user_default(user_id: str, tenant_id: str | None = None) -> bool:
        """
        Delete user's default model preference.

        Args:
            user_id: User subject from JWT
            tenant_id: Tenant ID for scoping

        Returns:
            True if deleted, False if not found

        Example:
            >>> deleted = delete_user_default("auth0|123", "acme-corp")
            >>> if deleted:
            >>>     print("Default removed")
        """
        db: Session = next(get_db())
        try:
            stmt = sql_delete(UserDefaultModel).where(
                and_(
                    UserDefaultModel.user_id == user_id,
                    UserDefaultModel.tenant_id == tenant_id if tenant_id else UserDefaultModel.tenant_id.is_(None),
                )
            )

            result = db.execute(stmt)
            db.commit()

            return result.rowcount > 0

        except Exception as e:
            db.rollback()
            logger.error(f"Error deleting user default: {e}")
            raise
        finally:
            db.close()

    @staticmethod
    def cascade_clear_defaults(instance_id: str) -> int:
        """
        Clear all user defaults pointing to a specific model instance.

        Called when a model instance is deleted (CASCADE handled by FK).
        This is informational - actual cascade is done by database FK.

        Args:
            instance_id: Model instance ID being deleted

        Returns:
            Number of user defaults that were cleared

        Example:
            >>> count = cascade_clear_defaults("abc-123")
            >>> print(f"Cleared {count} user defaults")
        """
        db: Session = next(get_db())
        try:
            stmt = sql_delete(UserDefaultModel).where(UserDefaultModel.chat_instance_id == instance_id)

            result = db.execute(stmt)
            db.commit()

            return result.rowcount

        except Exception as e:
            db.rollback()
            logger.error(f"Error cascading user defaults: {e}")
            raise
        finally:
            db.close()

    @staticmethod
    def list_user_defaults(user_id: str, tenant_id: str | None = None) -> list[dict]:
        """
        List all default model preferences for a user.

        Args:
            user_id: User subject from JWT
            tenant_id: Optional tenant filter

        Returns:
            List of user default dicts

        Example:
            >>> defaults = list_user_defaults("auth0|123")
            >>> for d in defaults:
            >>>     print(d['tenant_id'], d['chat_instance_id'])
        """
        db: Session = next(get_db())
        try:
            query = select(UserDefaultModel).where(UserDefaultModel.user_id == user_id)

            if tenant_id is not None:
                query = query.where(UserDefaultModel.tenant_id == tenant_id)

            query = query.options(joinedload(UserDefaultModel.instance))

            defaults = db.execute(query).scalars().all()

            return [
                {
                    "id": str(d.id),
                    "user_id": d.user_id,
                    "tenant_id": d.tenant_id,
                    "chat_instance_id": str(d.chat_instance_id),
                    "created_at": d.created_at.isoformat(),
                    "updated_at": d.updated_at.isoformat(),
                    "created_by": d.created_by,
                    "etag": d.etag,
                }
                for d in defaults
            ]

        except Exception as e:
            logger.error(f"Error listing user defaults: {e}")
            raise
        finally:
            db.close()


# Singleton instance
user_default_repo = UserDefaultModelRepo()
