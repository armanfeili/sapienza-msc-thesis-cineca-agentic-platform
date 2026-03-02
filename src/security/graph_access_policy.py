"""
Graph Access Policy: Centralized RBAC enforcement for Cypher queries.

This module provides a unified security layer for validating Cypher queries
against principal permissions. It consolidates security checks that were
previously scattered across multiple modules.

Features:
- Read-only vs write detection
- Admin operation detection
- Dangerous operation detection
- Role-based access control (RBAC)
- Suggested rewrites for denied queries (e.g., EXPLAIN)
- Audit-friendly denial reasons
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import structlog

log = structlog.get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Pattern Definitions
# ─────────────────────────────────────────────────────────────────────────────

# Write operations - modify data
WRITE_PATTERNS = re.compile(
    r"\b(CREATE|MERGE|SET|REMOVE)\b",
    re.IGNORECASE
)

# Delete operations - separate from write for finer control
DELETE_PATTERNS = re.compile(
    r"\b(DELETE|DETACH\s+DELETE)\b",
    re.IGNORECASE
)

# Schema/Admin operations - modify database structure
ADMIN_PATTERNS = re.compile(
    r"\b(CREATE\s+INDEX|DROP\s+INDEX|CREATE\s+CONSTRAINT|DROP\s+CONSTRAINT|"
    r"REINDEX|ALTER|CREATE\s+TRIGGER|DROP\s+TRIGGER)\b",
    re.IGNORECASE
)

# Dangerous operations - should always be blocked or require EXPLAIN
DANGEROUS_PATTERNS = re.compile(
    r"\b(DROP\s+DATABASE|DROP\s+GRAPH|AUTH|TERMINATE|KILL|SHUTDOWN|"
    r"TRUNCATE|LOAD\s+CSV|COPY\s+FROM|COPY\s+TO)\b",
    re.IGNORECASE
)

# Operations that might be heavy (full scan, cartesian)
HEAVY_PATTERNS = re.compile(
    r"(-\[\*\]->|-\[\*\d+\.\.\]-)|"  # Unbounded variable-length paths
    r"\bMATCH\s*\([^)]+\)\s*,\s*\(",  # Multiple unconnected patterns (cartesian)
    re.IGNORECASE
)

# CALL procedures - check against allowlist
CALL_PATTERN = re.compile(
    r"\bCALL\s+([a-zA-Z_][a-zA-Z0-9_.]+)",
    re.IGNORECASE
)

# Safe read-only CALL procedures
SAFE_PROCEDURES = {
    "db.labels",
    "db.relationshipTypes", 
    "db.propertyKeys",
    "db.indexes",
    "db.constraints",
    "db.info",
    "db.stats",
    "show_labels",
    "show_relationship_types",
    "show_property_keys",
    "show_indexes",
    "show_constraints",
    "dbms.procedures",
    "dbms.functions",
}


# ─────────────────────────────────────────────────────────────────────────────
# Validation Result
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CypherValidation:
    """Result of Cypher query validation."""
    
    is_safe: bool  # True if query can be executed
    is_read_only: bool  # True if no write operations
    has_writes: bool  # True if CREATE/MERGE/SET/REMOVE
    has_deletes: bool  # True if DELETE/DETACH DELETE
    requires_admin: bool  # True if schema/admin operations
    is_dangerous: bool  # True if explicitly dangerous
    is_heavy: bool  # True if potentially expensive
    
    blocked_clauses: list[str] = field(default_factory=list)
    suggested_rewrite: str | None = None
    denial_reason: str | None = None
    
    # For audit trail
    validation_checks: dict[str, bool] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Policy Class
# ─────────────────────────────────────────────────────────────────────────────

class GraphAccessPolicy:
    """
    RBAC enforcement for Cypher queries.
    
    Usage:
        policy = GraphAccessPolicy()
        validation = policy.validate_cypher(cypher)
        
        if not validation.is_safe:
            # Handle denial
            print(validation.denial_reason)
            if validation.suggested_rewrite:
                print(f"Try: {validation.suggested_rewrite}")
    """
    
    def __init__(self, *, strict_mode: bool = True):
        """
        Initialize policy.
        
        Args:
            strict_mode: If True, deny on any suspicious pattern.
                        If False, allow more operations (for testing).
        """
        self.strict_mode = strict_mode
    
    def validate_cypher(self, cypher: str) -> CypherValidation:
        """
        Validate a Cypher query without considering principal.
        
        Returns validation result indicating query characteristics.
        """
        cypher = (cypher or "").strip()
        
        # Check for writes
        has_writes = bool(WRITE_PATTERNS.search(cypher))
        has_deletes = bool(DELETE_PATTERNS.search(cypher))
        requires_admin = bool(ADMIN_PATTERNS.search(cypher))
        is_dangerous = bool(DANGEROUS_PATTERNS.search(cypher))
        is_heavy = bool(HEAVY_PATTERNS.search(cypher))
        
        # Check CALL procedures
        unsafe_calls = self._check_unsafe_calls(cypher)
        if unsafe_calls:
            has_writes = True  # Treat unsafe CALL as write
        
        is_read_only = not (has_writes or has_deletes or requires_admin or is_dangerous)
        
        blocked_clauses = []
        if has_writes:
            blocked_clauses.extend(WRITE_PATTERNS.findall(cypher))
        if has_deletes:
            blocked_clauses.extend(DELETE_PATTERNS.findall(cypher))
        if requires_admin:
            blocked_clauses.extend(ADMIN_PATTERNS.findall(cypher))
        if is_dangerous:
            blocked_clauses.extend(DANGEROUS_PATTERNS.findall(cypher))
        if unsafe_calls:
            blocked_clauses.extend([f"CALL {c}" for c in unsafe_calls])
        
        # Determine if safe (without principal check)
        is_safe = is_read_only and not is_dangerous
        
        # Build denial reason
        denial_reason = None
        if not is_safe:
            if is_dangerous:
                denial_reason = "Query contains dangerous operations"
            elif requires_admin:
                denial_reason = "Query contains admin operations requiring elevated privileges"
            elif has_deletes:
                denial_reason = "Query contains DELETE operations requiring write permissions"
            elif has_writes:
                denial_reason = "Query contains write operations requiring write permissions"
        
        # Suggested rewrite for visibility
        suggested_rewrite = None
        if not is_safe and not cypher.strip().upper().startswith("EXPLAIN"):
            suggested_rewrite = f"EXPLAIN {cypher}"
        
        return CypherValidation(
            is_safe=is_safe,
            is_read_only=is_read_only,
            has_writes=has_writes,
            has_deletes=has_deletes,
            requires_admin=requires_admin,
            is_dangerous=is_dangerous,
            is_heavy=is_heavy,
            blocked_clauses=blocked_clauses,
            suggested_rewrite=suggested_rewrite,
            denial_reason=denial_reason,
            validation_checks={
                "read_only": is_read_only,
                "has_writes": has_writes,
                "has_deletes": has_deletes,
                "requires_admin": requires_admin,
                "is_dangerous": is_dangerous,
                "is_heavy": is_heavy,
            },
        )
    
    def validate_for_principal(
        self,
        cypher: str,
        principal: dict[str, Any] | None,
        tenant_id: str | None = None,
    ) -> CypherValidation:
        """
        Validate Cypher query against principal's permissions.
        
        Args:
            cypher: The Cypher query to validate
            principal: Principal dict with roles/permissions/scopes
            tenant_id: Tenant context (optional)
        
        Returns:
            CypherValidation with is_safe reflecting RBAC outcome
        """
        # Start with basic validation
        validation = self.validate_cypher(cypher)
        
        # Check principal permissions
        is_admin = self._is_admin(principal)
        has_write_perm = self._has_write_permission(principal)
        
        # Adjust safety based on permissions
        if validation.is_dangerous:
            # Dangerous always blocked, even for admin in strict mode
            if self.strict_mode:
                validation.is_safe = False
                validation.denial_reason = "Dangerous operations are not allowed"
            else:
                # In non-strict mode, admin can run dangerous queries
                validation.is_safe = is_admin
                if not is_admin:
                    validation.denial_reason = "Dangerous operations require admin role"
        
        elif validation.requires_admin:
            # Admin operations need admin role
            if is_admin:
                validation.is_safe = True
                validation.denial_reason = None
                validation.suggested_rewrite = None
            else:
                validation.is_safe = False
                validation.denial_reason = "Admin operations require admin role"
        
        elif validation.has_writes or validation.has_deletes:
            # Write operations need write permission
            if has_write_perm or is_admin:
                validation.is_safe = True
                validation.denial_reason = None
                validation.suggested_rewrite = None
            else:
                validation.is_safe = False
                validation.denial_reason = "Write operations require write permission or admin role"
        
        # Heavy queries get a warning but aren't blocked
        if validation.is_heavy and validation.is_safe:
            log.warning(
                "graph_access_policy.heavy_query",
                cypher_preview=cypher[:100],
                principal=self._principal_id(principal),
            )
        
        return validation
    
    def _check_unsafe_calls(self, cypher: str) -> list[str]:
        """Check for CALL procedures that are not in the safe list."""
        matches = CALL_PATTERN.findall(cypher)
        unsafe = []
        for proc in matches:
            if proc.lower() not in {s.lower() for s in SAFE_PROCEDURES}:
                unsafe.append(proc)
        return unsafe
    
    def _is_admin(self, principal: dict[str, Any] | None) -> bool:
        """Check if principal has admin privileges."""
        if not principal:
            return False
        
        # Check for explicit RBAC bypass
        if principal.get("rbac_enforced") is False:
            return True
        
        permissions = principal.get("permissions") or []
        roles = principal.get("roles") or []
        
        # Normalize to lists
        if isinstance(permissions, str):
            permissions = [permissions]
        if isinstance(roles, str):
            roles = [roles]
        
        return (
            "admin:all" in permissions
            or any(str(r).lower() == "admin" for r in roles)
        )
    
    def _has_write_permission(self, principal: dict[str, Any] | None) -> bool:
        """Check if principal has write permission."""
        if not principal:
            return False
        
        if principal.get("rbac_enforced") is False:
            return True
        
        permissions = principal.get("permissions") or []
        scopes = principal.get("scopes") or []
        
        # Normalize
        if isinstance(permissions, str):
            permissions = [permissions]
        if isinstance(scopes, str):
            scopes = scopes.split()
        
        # Check for write permissions
        write_indicators = [
            "tools:all",
            "tools:write",
            "graph:write",
            "admin:all",
        ]
        
        return any(
            perm in permissions or perm in scopes
            for perm in write_indicators
        )
    
    def _principal_id(self, principal: dict[str, Any] | None) -> str:
        """Extract principal identifier for logging."""
        if not principal:
            return "anonymous"
        return (
            principal.get("id")
            or principal.get("sub")
            or principal.get("user_id")
            or principal.get("email")
            or "unknown"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Convenience Functions
# ─────────────────────────────────────────────────────────────────────────────

_default_policy = GraphAccessPolicy(strict_mode=True)


def validate_cypher(cypher: str) -> CypherValidation:
    """Validate Cypher without principal (basic safety check)."""
    return _default_policy.validate_cypher(cypher)


def validate_for_principal(
    cypher: str,
    principal: dict[str, Any] | None,
    tenant_id: str | None = None,
) -> CypherValidation:
    """Validate Cypher against principal permissions."""
    return _default_policy.validate_for_principal(cypher, principal, tenant_id)


def is_read_only(cypher: str) -> bool:
    """Quick check if a Cypher query is read-only."""
    validation = _default_policy.validate_cypher(cypher)
    return validation.is_read_only


def requires_admin(cypher: str) -> bool:
    """Quick check if a Cypher query requires admin privileges."""
    validation = _default_policy.validate_cypher(cypher)
    return validation.requires_admin


def is_dangerous(cypher: str) -> bool:
    """Quick check if a Cypher query is dangerous."""
    validation = _default_policy.validate_cypher(cypher)
    return validation.is_dangerous


__all__ = [
    "CypherValidation",
    "GraphAccessPolicy",
    "validate_cypher",
    "validate_for_principal",
    "is_read_only",
    "requires_admin",
    "is_dangerous",
]
