from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class Tenant:
    id: str
    name: str
    admin_email: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


_TENANTS: dict[str, Tenant] = {}
# Test dependency injection - maps tenant_id -> list of blockers
_TEST_DEPENDENCIES: dict[str, list[dict[str, Any]]] = {}


def _generate_tenant_id() -> str:
    """Generate a unique tenant ID (slug-friendly)."""
    # Generate a short UUID-based ID
    uid = str(uuid.uuid4())[:8]
    return f"tenant-{uid}"


def _deep_merge_dict(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    """Deep merge updates into base dictionary.

    - Existing keys in base are preserved unless explicitly updated
    - New keys from updates are added
    - Nested dicts are recursively merged
    - None values in updates remove keys from base
    """
    result = base.copy()
    for key, value in updates.items():
        if value is None:
            # None means remove the key
            result.pop(key, None)
        elif key in result and isinstance(result[key], dict) and isinstance(value, dict):
            # Recursively merge nested dicts
            result[key] = _deep_merge_dict(result[key], value)
        else:
            # Replace or add the value
            result[key] = value
    return result


def list_tenants() -> list[dict]:
    """List all tenants sorted by ID."""
    return [vars(t) for _, t in sorted(_TENANTS.items())]


def create_tenant(name: str, admin_email: str, metadata: dict | None = None, id: str | None = None) -> dict:
    """Create a new tenant with server-generated ID.

    Args:
        name: Tenant display name
        admin_email: Admin contact email (validated by caller)
        metadata: Optional metadata dict
        id: Optional explicit ID (for testing/migration); if None, auto-generated

    Returns:
        Tenant dict

    Raises:
        ValueError: If tenant with same ID already exists with different config
    """
    # Generate ID if not provided
    tenant_id = id or _generate_tenant_id()

    # Check for existing tenant (idempotency)
    existing = _TENANTS.get(tenant_id)
    if existing:
        # Compare configs for idempotency
        same_config = (
            existing.name == name and existing.admin_email == admin_email and existing.metadata == (metadata or {})
        )

        if same_config:
            # Idempotent: return existing
            return vars(existing)
        else:
            # Conflict: same ID, different config
            raise ValueError(f"Tenant '{tenant_id}' already exists with different configuration")

    # Create new tenant
    t = Tenant(id=tenant_id, name=name, admin_email=admin_email, metadata=metadata or {})
    _TENANTS[tenant_id] = t
    return vars(t)


def get_tenant(id: str) -> dict | None:
    """Get tenant by ID."""
    t = _TENANTS.get(id)
    return vars(t) if t else None


def update_tenant(id: str, **patch) -> dict:
    """Update tenant with partial fields.

    Supports deep-merge for metadata field.
    """
    t = _TENANTS.get(id)
    if not t:
        raise KeyError("tenant not found")

    # Handle metadata merge specially
    if "metadata" in patch and patch["metadata"] is not None:
        t.metadata = _deep_merge_dict(t.metadata, patch["metadata"])
        patch = {k: v for k, v in patch.items() if k != "metadata"}

    # Update other fields
    for k, v in patch.items():
        if hasattr(t, k) and v is not None:
            setattr(t, k, v)

    t.updated_at = datetime.now(UTC).isoformat()
    return vars(t)


def delete_tenant(id: str, check_dependencies: bool = True) -> None:
    """Delete tenant by ID.

    Args:
        id: Tenant ID to delete
        check_dependencies: If True, check for dependent resources before deletion

    Raises:
        KeyError: If tenant not found
        ValueError: If tenant has dependencies (check_dependencies=True)
    """
    if id not in _TENANTS:
        raise KeyError("tenant not found")

    if check_dependencies:
        # Check for dependent resources
        blockers = _check_tenant_dependencies(id)
        if blockers:
            # Format blocker details for error message
            blocker_summary = ", ".join(f"{b['type']}:{b['id']}" for b in blockers)
            raise ValueError(f"Cannot delete tenant with dependencies: {blocker_summary}", blockers)

    del _TENANTS[id]


def _check_tenant_dependencies(tenant_id: str) -> list[dict[str, Any]]:
    """Check if tenant has any dependent resources.

    Returns:
        List of blocker dicts with type, id, name, status
    """
    blockers = []

    # Check test dependencies first (for testing)
    if tenant_id in _TEST_DEPENDENCIES:
        return _TEST_DEPENDENCIES[tenant_id]

    # Check providers (would query provider service in real implementation)
    # For now, stub - would be implemented when provider-tenant relationship exists

    # Check jobs (would query job service)
    # For now, stub - would be implemented when job-tenant relationship exists

    # Check other resources (defaults, etc.)
    # Stub for now

    return blockers


def set_test_dependencies(tenant_id: str, blockers: list[dict[str, Any]]) -> None:
    """Set test dependencies for a tenant (test helper function).

    Args:
        tenant_id: Tenant ID
        blockers: List of blocker dicts (type, id, name, status, etc.)
    """
    _TEST_DEPENDENCIES[tenant_id] = blockers


def clear_test_dependencies() -> None:
    """Clear all test dependencies (test helper function)."""
    _TEST_DEPENDENCIES.clear()
