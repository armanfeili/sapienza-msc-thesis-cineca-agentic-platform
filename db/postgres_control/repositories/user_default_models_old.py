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
        tenant_id="acme-corp",
        created_by="auth0|123"
    )
"""
from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from uuid import UUID

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
        return f'"user-default-{hash_val}"'

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
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            query = """
                SELECT
                    udm.id,
                    udm.user_id,
                    udm.tenant_id,
                    udm.chat_instance_id,
                    udm.created_at,
                    udm.updated_at,
                    udm.created_by,
                    udm.etag,
                    mi.instance_name,
                    mi.model_id,
                    mi.provider_id,
                    mi.enabled
                FROM user_default_models udm
                JOIN model_instances mi ON udm.chat_instance_id = mi.id
                WHERE udm.user_id = %s
                  AND (udm.tenant_id = %s OR (udm.tenant_id IS NULL AND %s IS NULL))
                LIMIT 1
            """

            cursor.execute(query, (user_id, tenant_id, tenant_id))
            row = cursor.fetchone()

            if not row:
                return None

            # Build response
            default = {
                "id": str(row[0]),
                "user_id": row[1],
                "tenant_id": row[2],
                "chat_instance_id": str(row[3]),
                "created_at": row[4].isoformat() if row[4] else None,
                "updated_at": row[5].isoformat() if row[5] else None,
                "created_by": row[6],
                "etag": row[7],
                # Instance details (for convenience)
                "instance_name": row[8],
                "model_id": row[9],
                "provider_id": str(row[10]) if row[10] else None,
                "enabled": row[11],
            }

            return default

        except Exception as exc:
            logger.error(f"user_default.get.failed: {exc}", exc_info=True)
            raise
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def set_user_default(
        user_id: str, instance_id: str, tenant_id: str | None = None, created_by: str | None = None
    ) -> dict:
        """
        Set or update user's default model preference.

        Uses UPSERT (INSERT ... ON CONFLICT UPDATE) to handle create/update atomically.

        Args:
            user_id: User subject from JWT
            instance_id: Model instance ID to set as default
            tenant_id: Tenant ID for scoping (None = global user default)
            created_by: User subject who is setting this default

        Returns:
            Dict with updated default info

        Raises:
            ValueError: If instance_id is invalid or instance not found

        Example:
            >>> default = set_user_default(
            ...     user_id="auth0|123",
            ...     instance_id="6491b020-bbe3-47fe-991e-e7c21a15260c",
            ...     tenant_id="acme-corp",
            ...     created_by="auth0|123"
            ... )
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # Validate UUID format
            try:
                UUID(instance_id)
            except ValueError:
                raise ValueError(f"Invalid instance_id format: {instance_id}")

            # Check if instance exists
            cursor.execute("SELECT id, instance_name, enabled FROM model_instances WHERE id = %s", (instance_id,))
            instance_row = cursor.fetchone()

            if not instance_row:
                raise ValueError(f"Instance not found: {instance_id}")

            instance_name = instance_row[1]
            enabled = instance_row[2]

            # Compute initial ETag
            now = datetime.now(UTC)
            etag = UserDefaultModelRepo._compute_etag(user_id, tenant_id, instance_id, now)

            # UPSERT: Insert or update on conflict
            upsert_query = """
                INSERT INTO user_default_models (
                    user_id, tenant_id, chat_instance_id, created_by, etag, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, tenant_id)
                DO UPDATE SET
                    chat_instance_id = EXCLUDED.chat_instance_id,
                    updated_at = EXCLUDED.updated_at,
                    etag = EXCLUDED.etag
                RETURNING id, created_at, updated_at
            """

            cursor.execute(upsert_query, (user_id, tenant_id, instance_id, created_by or user_id, etag, now, now))

            result_row = cursor.fetchone()
            conn.commit()

            # Build response
            default = {
                "id": str(result_row[0]),
                "user_id": user_id,
                "tenant_id": tenant_id,
                "chat_instance_id": instance_id,
                "created_at": result_row[1].isoformat(),
                "updated_at": result_row[2].isoformat(),
                "created_by": created_by or user_id,
                "etag": etag,
                # Instance details (for convenience)
                "instance_name": instance_name,
                "enabled": enabled,
            }

            logger.info(f"user_default.set: user={user_id}, tenant={tenant_id}, instance={instance_id}")
            return default

        except Exception as exc:
            conn.rollback()
            logger.error(f"user_default.set.failed: {exc}", exc_info=True)
            raise
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def delete_user_default(user_id: str, tenant_id: str | None = None) -> bool:
        """
        Delete user's default model preference.

        Args:
            user_id: User subject from JWT
            tenant_id: Tenant ID for scoping (None = global user default)

        Returns:
            True if deleted, False if not found

        Example:
            >>> deleted = delete_user_default("auth0|123", "acme-corp")
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            query = """
                DELETE FROM user_default_models
                WHERE user_id = %s
                  AND (tenant_id = %s OR (tenant_id IS NULL AND %s IS NULL))
            """

            cursor.execute(query, (user_id, tenant_id, tenant_id))
            deleted_count = cursor.rowcount
            conn.commit()

            if deleted_count > 0:
                logger.info(f"user_default.delete: user={user_id}, tenant={tenant_id}")
                return True
            else:
                return False

        except Exception as exc:
            conn.rollback()
            logger.error(f"user_default.delete.failed: {exc}", exc_info=True)
            raise
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def cascade_clear_defaults(instance_id: str) -> int:
        """
        Clear all user defaults pointing to a deleted instance.

        This is automatically handled by FK CASCADE DELETE, but this method
        provides explicit control and logging for observability.

        Args:
            instance_id: Model instance ID being deleted

        Returns:
            Number of user defaults cleared

        Example:
            >>> cleared = cascade_clear_defaults("6491b020-bbe3-47fe-991e-e7c21a15260c")
            >>> print(f"Cleared {cleared} user defaults")
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # Count how many will be affected (for logging)
            cursor.execute("SELECT COUNT(*) FROM user_default_models WHERE chat_instance_id = %s", (instance_id,))
            count = cursor.fetchone()[0]

            if count > 0:
                # Delete (cascade will handle this automatically via FK, but explicit is good)
                cursor.execute("DELETE FROM user_default_models WHERE chat_instance_id = %s", (instance_id,))
                conn.commit()
                logger.info(f"user_default.cascade_clear: instance={instance_id}, cleared={count}")

            return count

        except Exception as exc:
            conn.rollback()
            logger.error(f"user_default.cascade_clear.failed: {exc}", exc_info=True)
            raise
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def list_user_defaults(user_id: str | None = None, tenant_id: str | None = None) -> list[dict]:
        """
        List user defaults with optional filtering.

        Args:
            user_id: Filter by specific user (None = all users)
            tenant_id: Filter by specific tenant (None = all tenants)

        Returns:
            List of user default dicts

        Example:
            >>> # List all defaults for a user across all tenants
            >>> defaults = list_user_defaults(user_id="auth0|123")
            >>>
            >>> # List all defaults for a tenant
            >>> defaults = list_user_defaults(tenant_id="acme-corp")
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            conditions = []
            params = []

            if user_id:
                conditions.append("udm.user_id = %s")
                params.append(user_id)

            if tenant_id:
                conditions.append("udm.tenant_id = %s")
                params.append(tenant_id)

            where_clause = " AND ".join(conditions) if conditions else "TRUE"

            query = f"""
                SELECT
                    udm.id,
                    udm.user_id,
                    udm.tenant_id,
                    udm.chat_instance_id,
                    udm.created_at,
                    udm.updated_at,
                    udm.created_by,
                    udm.etag,
                    mi.instance_name,
                    mi.model_id,
                    mi.enabled
                FROM user_default_models udm
                JOIN model_instances mi ON udm.chat_instance_id = mi.id
                WHERE {where_clause}
                ORDER BY udm.created_at DESC
            """

            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()

            defaults = []
            for row in rows:
                defaults.append(
                    {
                        "id": str(row[0]),
                        "user_id": row[1],
                        "tenant_id": row[2],
                        "chat_instance_id": str(row[3]),
                        "created_at": row[4].isoformat() if row[4] else None,
                        "updated_at": row[5].isoformat() if row[5] else None,
                        "created_by": row[6],
                        "etag": row[7],
                        "instance_name": row[8],
                        "model_id": row[9],
                        "enabled": row[10],
                    }
                )

            return defaults

        except Exception as exc:
            logger.error(f"user_default.list.failed: {exc}", exc_info=True)
            raise
        finally:
            cursor.close()
            conn.close()


# Singleton instance
user_default_repo = UserDefaultModelRepo()
