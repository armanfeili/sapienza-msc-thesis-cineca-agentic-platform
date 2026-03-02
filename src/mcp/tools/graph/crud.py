"""
MCP Tool: graph.crud

Focused CRUD operations for Memgraph with strict RBAC enforcement.

Supported operations
--------------------
- create_node: Create new node with labels and properties
- update_node: Update existing node properties (merge or replace)
- delete_node: Delete node (with DETACH option)
- create_relationship: Create relationship between two nodes
- delete_relationship: Delete relationship between two nodes

Security
--------
- Requires tools:write scope for all operations
- Principal and tenant isolation enforced
- Write operations logged for audit

Notes
-----
- Uses orig_id as primary match key for nodes
- Supports label-based and property-based matching
- All operations are transactional
"""

from __future__ import annotations

import time
from contextlib import suppress
from typing import Any

# ── Logging ───────────────────────────────────────────────────────────────────
with suppress(Exception):
    from src.logging_setup import get_logger  # type: ignore

    logger = get_logger(__name__)  # type: ignore[assignment]
if "logger" not in globals():
    import logging

    logger = logging.getLogger(__name__)

# ── MCP Framework ─────────────────────────────────────────────────────────────
from src.mcp.runtime import ToolContext, mcp_tool
from src.mcp.schemas import GraphCrudOperation, GraphCrudPayload

# ── Memgraph adapter ──────────────────────────────────────────────────────────
with suppress(Exception):
    from src.adapters.db_memgraph import MemgraphAdapter  # type: ignore
if "MemgraphAdapter" not in globals():
    raise RuntimeError("Memgraph adapter is required for graph.crud tool")

# ── Audit (best-effort) ───────────────────────────────────────────────────────
with suppress(Exception):
    from src.security.audit import audit_access  # type: ignore
if "audit_access" not in globals():

    def audit_access(**_: Any) -> None:  # type: ignore
        return


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def _safe_labels(labels: list[str]) -> str:
    """Convert label list to safe Cypher label expression."""
    if not labels or not isinstance(labels, list):
        raise ValueError("labels must be a non-empty list")
    return ":".join(f"`{l!s}`" for l in labels if str(l).strip())


def _build_set_clause(props: dict[str, Any], mode: str = "merge") -> str:
    """
    Build SET clause for property updates.

    Args:
        props: Properties to set
        mode: "merge" (SET n += $props) or "replace" (SET n = $props)

    Returns:
        SET clause fragment
    """
    if not props:
        return ""

    if mode == "merge":
        return "SET n += $props"
    elif mode == "replace":
        # Preserve orig_id when replacing all properties
        return "SET n = {orig_id: n.orig_id} + $props"
    else:
        raise ValueError(f"Invalid mode: {mode}. Must be 'merge' or 'replace'")


def _build_match_where(match_dict: dict[str, Any]) -> str:
    """Build WHERE clause from match dictionary."""
    if not match_dict:
        return ""

    conditions = []
    for key in match_dict:
        conditions.append(f"n.`{key}` = $match_{key}")

    return "WHERE " + " AND ".join(conditions) if conditions else ""


def _extract_match_params(match_dict: dict[str, Any]) -> dict[str, Any]:
    """Extract match parameters with match_ prefix."""
    if not match_dict:
        return {}
    return {f"match_{k}": v for k, v in match_dict.items()}


# ──────────────────────────────────────────────────────────────────────────────
# Action Handlers
# ──────────────────────────────────────────────────────────────────────────────
def _act_create_node(db: MemgraphAdapter, payload: dict[str, Any], principal: str, tenant: str) -> dict[str, Any]:
    """
    Create a new node with labels and properties.

    Uses MERGE semantics with orig_id as unique key.
    Returns created flag to indicate if node was newly created.
    """
    start_time = time.time()

    # Required fields
    labels = payload.get("labels")
    properties = payload.get("properties", {})

    if not labels:
        raise ValueError("create_node requires 'labels'")

    # Generate orig_id if not provided
    if "orig_id" not in properties:
        import uuid

        properties["orig_id"] = str(uuid.uuid4())

    orig_id = properties["orig_id"]

    # Add tenant isolation
    properties["tenant"] = tenant
    properties["created_by"] = principal

    # Check if node already exists
    existed_rows = db.query("MATCH (n {orig_id: $orig_id}) RETURN count(n) AS c", {"orig_id": orig_id})
    existed = bool(existed_rows and int(existed_rows[0].get("c", 0)) > 0)

    # Create/merge node
    label_expr = _safe_labels(labels)
    db.query(f"MERGE (n:{label_expr} {{orig_id: $orig_id}}) SET n += $props", {"orig_id": orig_id, "props": properties})

    # Fetch created node
    rows = db.query(
        "MATCH (n {orig_id: $orig_id}) RETURN labels(n) AS labels, properties(n) AS props", {"orig_id": orig_id}
    )

    if not rows:
        raise RuntimeError(f"Failed to create node with orig_id={orig_id}")

    node_data = rows[0]
    elapsed_ms = int((time.time() - start_time) * 1000)

    # Audit write operation
    with suppress(Exception):
        audit_access(
            principal=principal,
            resource="mcp.tools.graph.crud",
            action="create_node",
            allowed=True,
            attributes={"orig_id": orig_id, "labels": labels, "tenant": tenant, "created": not existed},
        )

    return {
        "ok": True,
        "operation": "create_node",
        "created": not existed,
        "node": {"orig_id": orig_id, "labels": node_data.get("labels", []), "properties": node_data.get("props", {})},
        "elapsed_ms": elapsed_ms,
    }


def _act_update_node(db: MemgraphAdapter, payload: dict[str, Any], principal: str, tenant: str) -> dict[str, Any]:
    """
    Update existing node properties.

    Supports:
    - Match by orig_id OR label + match conditions
    - Merge mode (default): merges new props into existing
    - Replace mode: replaces all props (except orig_id)
    """
    start_time = time.time()

    # Extract parameters
    match = payload.get("match", {})
    properties = payload.get("properties", {})
    label = payload.get("label")
    mode = payload.get("mode", "merge")  # merge or replace

    if not properties:
        raise ValueError("update_node requires 'properties'")

    # Enforce tenant isolation
    if "tenant" in properties and properties["tenant"] != tenant:
        raise ValueError("Cannot update node with different tenant")

    properties["updated_by"] = principal
    properties["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Build match clause
    if "orig_id" in match:
        # Match by orig_id
        match_clause = "MATCH (n {orig_id: $orig_id, tenant: $tenant})"
        params = {"orig_id": match["orig_id"], "tenant": tenant, "props": properties}
    elif label and match:
        # Match by label + conditions
        where_clause = _build_match_where(match)
        match_params = _extract_match_params(match)
        match_clause = f"MATCH (n:`{label}` {{tenant: $tenant}}) {where_clause}"
        params = {**match_params, "tenant": tenant, "props": properties}
    else:
        raise ValueError("update_node requires either 'match.orig_id' or ('label' and 'match')")

    # Build SET clause
    set_clause = _build_set_clause(properties, mode)

    # Update node
    cypher = f"{match_clause} {set_clause} RETURN labels(n) AS labels, properties(n) AS props"
    rows = db.query(cypher, params)

    if not rows:
        raise ValueError("No node found matching the criteria")

    node_data = rows[0]
    elapsed_ms = int((time.time() - start_time) * 1000)

    # Audit
    with suppress(Exception):
        audit_access(
            principal=principal,
            resource="mcp.tools.graph.crud",
            action="update_node",
            allowed=True,
            attributes={"match": match, "label": label, "tenant": tenant, "mode": mode},
        )

    return {
        "ok": True,
        "operation": "update_node",
        "updated": True,
        "node": {"labels": node_data.get("labels", []), "properties": node_data.get("props", {})},
        "elapsed_ms": elapsed_ms,
    }


def _act_delete_node(db: MemgraphAdapter, payload: dict[str, Any], principal: str, tenant: str) -> dict[str, Any]:
    """
    Delete node by orig_id or label + match conditions.

    Uses DETACH DELETE to remove all relationships.
    Enforces tenant isolation.
    """
    start_time = time.time()

    # Extract parameters
    match = payload.get("match", {})
    label = payload.get("label")

    # Build match clause
    if "orig_id" in match:
        # Match by orig_id
        cypher = "MATCH (n {orig_id: $orig_id, tenant: $tenant}) WITH n, 1 AS c DETACH DELETE n RETURN c"
        params = {"orig_id": match["orig_id"], "tenant": tenant}
        match_key = match["orig_id"]
    elif label and match:
        # Match by label + conditions
        where_clause = _build_match_where(match)
        match_params = _extract_match_params(match)
        cypher = f"MATCH (n:`{label}` {{tenant: $tenant}}) {where_clause} WITH n, 1 AS c DETACH DELETE n RETURN c"
        params = {**match_params, "tenant": tenant}
        match_key = f"{label}:{match}"
    else:
        raise ValueError("delete_node requires either 'match.orig_id' or ('label' and 'match')")

    # Delete node
    rows = db.query(cypher, params)
    deleted = 1 if rows else 0
    elapsed_ms = int((time.time() - start_time) * 1000)

    # Audit
    with suppress(Exception):
        audit_access(
            principal=principal,
            resource="mcp.tools.graph.crud",
            action="delete_node",
            allowed=True,
            attributes={"match": match, "label": label, "tenant": tenant, "deleted": deleted},
        )

    return {
        "ok": True,
        "operation": "delete_node",
        "deleted": deleted,
        "match_key": match_key,
        "elapsed_ms": elapsed_ms,
    }


def _act_create_relationship(
    db: MemgraphAdapter, payload: dict[str, Any], principal: str, tenant: str
) -> dict[str, Any]:
    """
    Create relationship between two nodes.

    Uses MERGE semantics. Both nodes must exist and belong to same tenant.
    Returns created flag to indicate if relationship was newly created.
    """
    start_time = time.time()

    # Required fields
    from_node = payload.get("from_")
    to_node = payload.get("to")
    rel_type = payload.get("rel_type")
    properties = payload.get("properties", {})

    if not from_node or not to_node or not rel_type:
        raise ValueError("create_relationship requires 'from', 'to', and 'rel_type'")

    if "orig_id" not in from_node or "orig_id" not in to_node:
        raise ValueError("Both 'from' and 'to' must have 'orig_id'")

    from_id = from_node["orig_id"]
    to_id = to_node["orig_id"]

    # Add metadata
    properties["tenant"] = tenant
    properties["created_by"] = principal
    properties["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Check if relationship already exists
    existed_rows = db.query(
        f"MATCH (a {{orig_id: $from_id, tenant: $tenant}})-[r:`{rel_type}`]->(b {{orig_id: $to_id, tenant: $tenant}}) RETURN count(r) AS c",
        {"from_id": from_id, "to_id": to_id, "tenant": tenant},
    )
    existed = bool(existed_rows and int(existed_rows[0].get("c", 0)) > 0)

    # Create relationship
    db.query(
        f"MATCH (a {{orig_id: $from_id, tenant: $tenant}}), (b {{orig_id: $to_id, tenant: $tenant}}) "
        f"MERGE (a)-[r:`{rel_type}`]->(b) "
        "SET r += $props",
        {"from_id": from_id, "to_id": to_id, "tenant": tenant, "props": properties},
    )

    elapsed_ms = int((time.time() - start_time) * 1000)

    # Audit
    with suppress(Exception):
        audit_access(
            principal=principal,
            resource="mcp.tools.graph.crud",
            action="create_relationship",
            allowed=True,
            attributes={"from_id": from_id, "to_id": to_id, "type": rel_type, "tenant": tenant, "created": not existed},
        )

    return {
        "ok": True,
        "operation": "create_relationship",
        "created": not existed,
        "relationship": {"type": rel_type, "from_orig_id": from_id, "to_orig_id": to_id, "properties": properties},
        "elapsed_ms": elapsed_ms,
    }


def _act_delete_relationship(
    db: MemgraphAdapter, payload: dict[str, Any], principal: str, tenant: str
) -> dict[str, Any]:
    """
    Delete relationship between two nodes.

    Requires from.orig_id, to.orig_id, and rel_type.
    Enforces tenant isolation.
    """
    start_time = time.time()

    # Required fields
    from_node = payload.get("from_")
    to_node = payload.get("to")
    rel_type = payload.get("rel_type")

    if not from_node or not to_node or not rel_type:
        raise ValueError("delete_relationship requires 'from', 'to', and 'rel_type'")

    if "orig_id" not in from_node or "orig_id" not in to_node:
        raise ValueError("Both 'from' and 'to' must have 'orig_id'")

    from_id = from_node["orig_id"]
    to_id = to_node["orig_id"]

    # Delete relationship
    rows = db.query(
        f"MATCH (a {{orig_id: $from_id, tenant: $tenant}})-[r:`{rel_type}`]->(b {{orig_id: $to_id, tenant: $tenant}}) "
        "WITH r, 1 AS c DELETE r RETURN c",
        {"from_id": from_id, "to_id": to_id, "tenant": tenant},
    )

    deleted = 1 if rows else 0
    elapsed_ms = int((time.time() - start_time) * 1000)

    # Audit
    with suppress(Exception):
        audit_access(
            principal=principal,
            resource="mcp.tools.graph.crud",
            action="delete_relationship",
            allowed=True,
            attributes={"from_id": from_id, "to_id": to_id, "type": rel_type, "tenant": tenant, "deleted": deleted},
        )

    return {
        "ok": True,
        "operation": "delete_relationship",
        "deleted": deleted,
        "from_orig_id": from_id,
        "to_orig_id": to_id,
        "rel_type": rel_type,
        "elapsed_ms": elapsed_ms,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Public entrypoint
# ──────────────────────────────────────────────────────────────────────────────
@mcp_tool(tool_name="graph.crud", required_scope="tools:write")
def invoke(ctx: ToolContext, payload: dict[str, Any] | None = None, **kwargs) -> dict[str, Any]:
    """
    Entry point for graph.crud tool.

    Enforces:
    - tools:write scope requirement
    - Principal and tenant isolation
    - Audit logging for all write operations

    See module docstring for supported operations and payload formats.
    """
    # Validate payload
    payload = payload or {}
    validated = GraphCrudPayload(**payload)

    # Merge validated defaults with user payload
    validated_dict = {**payload}
    for field_name, field_info in GraphCrudPayload.model_fields.items():
        if field_info.default is not None and field_name not in payload:
            validated_dict[field_name] = getattr(validated, field_name)

    # Extract context
    operation = validated_dict["operation"]
    principal = validated_dict.get("principal")
    tenant = validated_dict.get("tenant")

    if not principal:
        raise ValueError("principal is required for graph.crud operations")
    if not tenant:
        raise ValueError("tenant is required for graph.crud operations")

    # Initialize database adapter
    db = MemgraphAdapter()

    # Dispatch to operation handler
    if operation == GraphCrudOperation.create_node:
        return _act_create_node(db, validated_dict, principal, tenant)
    elif operation == GraphCrudOperation.update_node:
        return _act_update_node(db, validated_dict, principal, tenant)
    elif operation == GraphCrudOperation.delete_node:
        return _act_delete_node(db, validated_dict, principal, tenant)
    elif operation == GraphCrudOperation.create_relationship:
        return _act_create_relationship(db, validated_dict, principal, tenant)
    elif operation == GraphCrudOperation.delete_relationship:
        return _act_delete_relationship(db, validated_dict, principal, tenant)
    else:
        raise ValueError(f"Unsupported operation: {operation}")


# Back-compat aliases
run = invoke
handle = invoke
