"""
Tenants repository for PostgreSQL CRUD operations.

Provides database access layer with pagination, idempotency, ETag computation,
and JSONB metadata merging.
"""

from __future__ import annotations

import builtins
import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import and_, exc, func, or_, text
from sqlalchemy.orm import Session

from db.postgres_control.models.tenant import Tenant


class TenantsRepository:
    """Repository for tenant CRUD operations with PostgreSQL."""

    def __init__(self, db: Session):
        """
        Initialize repository with database session.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    @staticmethod
    def generate_tenant_id() -> str:
        """
        Generate unique tenant ID with 'tenant-' prefix.

        Returns:
            Tenant ID string (e.g., 'tenant-abc123de')
        """
        # Use first 8 chars of UUID4 hex for brevity
        return f"tenant-{uuid.uuid4().hex[:8]}"

    @staticmethod
    def compute_etag(tenant: Tenant) -> str:
        """
        Compute stable ETag from tenant data.

        Uses (id, updated_at, version) for uniqueness.

        Args:
            tenant: Tenant model instance

        Returns:
            ETag string (quoted hex hash)
        """
        # Stable hash of identifying fields
        data = f"{tenant.id}:{tenant.updated_at.isoformat()}:{tenant.version}"
        hash_digest = hashlib.sha256(data.encode()).hexdigest()[:16]
        return f'"{hash_digest}"'

    @staticmethod
    def compute_list_etag(tenants: builtins.list[Tenant]) -> str:
        """
        Compute ETag for a list of tenants.

        Args:
            tenants: List of tenant models

        Returns:
            ETag string for the collection
        """
        if not tenants:
            return '"empty"'

        # Hash concatenation of individual ETags
        combined = "".join(TenantsRepository.compute_etag(t).strip('"') for t in tenants)
        hash_digest = hashlib.sha256(combined.encode()).hexdigest()[:16]
        return f'"page-{hash_digest}"'

    def list(self, page_size: int = 100, page_token: str | None = None) -> tuple[builtins.list[Tenant], str | None, int]:
        """
        List tenants with keyset pagination.

        Args:
            page_size: Number of items per page (1-1000)
            page_token: Opaque pagination token from previous response

        Returns:
            Tuple of (items, next_page_token, total_count)
        """
        # Get total count
        total = self.db.query(func.count(Tenant.id)).scalar() or 0

        # Build base query ordered by created_at DESC, id ASC (for stability)
        query = self.db.query(Tenant).order_by(Tenant.created_at.desc(), Tenant.id.asc())

        # Decode page token (format: "created_at|id")
        if page_token:
            try:
                parts = page_token.split("|", 1)
                if len(parts) == 2:
                    last_created_str, last_id = parts
                    last_created = datetime.fromisoformat(last_created_str)

                    # Keyset pagination: WHERE (created_at, id) < (last_created, last_id)
                    query = query.filter(
                        or_(
                            Tenant.created_at < last_created,
                            and_(Tenant.created_at == last_created, Tenant.id > last_id),
                        )
                    )
            except (ValueError, AttributeError):
                # Invalid token - ignore and return first page
                pass

        # Fetch page_size + 1 to detect if there's a next page
        items = query.limit(page_size + 1).all()

        # Compute next_page_token
        has_more = len(items) > page_size
        if has_more:
            items = items[:page_size]
            last = items[-1]
            next_token = f"{last.created_at.isoformat()}|{last.id}"
        else:
            next_token = None

        return items, next_token, total

    def get_by_id(self, tenant_id: str) -> Tenant | None:
        """
        Retrieve tenant by ID.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Tenant model or None if not found
        """
        return self.db.query(Tenant).filter(Tenant.id == tenant_id).first()

    def get_by_name(self, name: str, case_insensitive: bool = True) -> Tenant | None:
        """
        Retrieve tenant by name.

        Args:
            name: Tenant name
            case_insensitive: Whether to do case-insensitive match

        Returns:
            Tenant model or None if not found
        """
        if case_insensitive:
            return self.db.query(Tenant).filter(func.lower(Tenant.name) == func.lower(name)).first()
        else:
            return self.db.query(Tenant).filter(Tenant.name == name).first()

    def create(self, name: str, admin_email: str, metadata: dict[str, Any] | None = None) -> tuple[Tenant, bool]:
        """
        Create a new tenant with idempotency support.

        If a tenant with the same name already exists:
        - If all fields match: returns (existing_tenant, False) [idempotent]
        - If fields differ: raises ValueError with conflict details

        Args:
            name: Tenant display name
            admin_email: Admin contact email
            metadata: Optional metadata dict

        Returns:
            Tuple of (tenant, created) where created=True for new, False for idempotent

        Raises:
            ValueError: If tenant name exists with different configuration
        """
        metadata = metadata or {}

        # Check for existing tenant with same name (case-insensitive)
        existing = self.get_by_name(name, case_insensitive=True)

        if existing:
            # Compare fields for idempotency
            conflicts = {}

            if existing.admin_email.lower() != admin_email.lower():
                conflicts["admin_email"] = {"existing": existing.admin_email, "requested": admin_email}

            if existing.metadata_ != metadata:
                conflicts["metadata"] = {"existing": existing.metadata_, "requested": metadata}

            if conflicts:
                # Not idempotent - return conflict
                raise ValueError(f"Tenant with name '{name}' already exists with different configuration", conflicts)
            else:
                # Idempotent - return existing
                return existing, False

        # Create new tenant
        tenant_id = self.generate_tenant_id()
        new_tenant = Tenant(
            id=tenant_id,
            name=name,
            admin_email=admin_email,
            metadata_=metadata,
        )

        try:
            self.db.add(new_tenant)
            self.db.commit()
            self.db.refresh(new_tenant)
            return new_tenant, True
        except exc.IntegrityError as e:
            self.db.rollback()
            # Race condition: another request created tenant with same name
            # Re-fetch and check idempotency
            existing = self.get_by_name(name, case_insensitive=True)
            if existing:
                # Check idempotency again
                conflicts = {}
                if existing.admin_email.lower() != admin_email.lower():
                    conflicts["admin_email"] = {"existing": existing.admin_email, "requested": admin_email}
                if existing.metadata_ != metadata:
                    conflicts["metadata"] = {"existing": existing.metadata_, "requested": metadata}

                if conflicts:
                    raise ValueError(
                        f"Tenant with name '{name}' already exists with different configuration", conflicts
                    )
                return existing, False

            # Some other integrity error
            raise ValueError(f"Database integrity error: {e}")

    def update_partial(
        self,
        tenant_id: str,
        name: str | None = None,
        admin_email: str | None = None,
        metadata_merge: dict[str, Any] | None = None,
    ) -> Tenant | None:
        """
        Apply partial update to tenant with JSONB metadata merging.

        Args:
            tenant_id: Tenant identifier
            name: New name (optional)
            admin_email: New admin email (optional)
            metadata_merge: Metadata to merge (optional)

        Returns:
            Updated tenant or None if not found

        Raises:
            ValueError: If update violates constraints
        """
        tenant = self.get_by_id(tenant_id)
        if not tenant:
            return None

        # Apply updates
        if name is not None:
            tenant.name = name

        if admin_email is not None:
            tenant.admin_email = admin_email

        if metadata_merge is not None:
            # Deep merge metadata using PostgreSQL JSONB || operator
            # This handles null values to delete keys

            stmt = text(
                """
                UPDATE tenants
                SET metadata = metadata || CAST(:patch AS jsonb)
                WHERE id = :tenant_id
            """
            )
            self.db.execute(stmt, {"patch": json.dumps(metadata_merge), "tenant_id": tenant_id})
            # Refresh to get updated metadata
            self.db.refresh(tenant)

        try:
            self.db.commit()
            self.db.refresh(tenant)
            return tenant
        except exc.IntegrityError as e:
            self.db.rollback()
            raise ValueError(f"Update failed: {e}")

    def delete(self, tenant_id: str) -> bool:
        """
        Delete tenant by ID.

        Args:
            tenant_id: Tenant identifier

        Returns:
            True if deleted, False if not found
        """
        tenant = self.get_by_id(tenant_id)
        if not tenant:
            return False

        self.db.delete(tenant)
        self.db.commit()
        return True

    def check_dependencies(self, tenant_id: str) -> builtins.list[dict[str, str]]:
        """
        Check if tenant has dependent resources.

        This is a placeholder - actual implementation would query
        providers, jobs, and other related tables.

        Args:
            tenant_id: Tenant identifier

        Returns:
            List of blockers (e.g., [{"type": "provider", "id": "...", "name": "..."}])
        """
        # TODO: Implement actual dependency checks when providers/jobs are migrated
        blockers = []

        # Example:
        # from src.models.provider import Provider
        # providers = self.db.query(Provider).filter(Provider.tenant_id == tenant_id).all()
        # for p in providers:
        #     blockers.append({"type": "provider", "id": p.id, "name": p.name})

        return blockers


__all__ = ["TenantsRepository"]
