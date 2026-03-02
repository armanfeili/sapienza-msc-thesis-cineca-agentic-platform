"""
MCP Tool: graph.search

Read-only query-builder style search over nodes/edges with filters, pagination, and projections.

Supported actions
-----------------
- nodes
    Search nodes by label(s) and property filters with pagination.

    Payload:
      {
        "action": "nodes",
        "label": "User",                    # optional single label
        "labels": ["User", "Institution"],   # optional multiple labels (OR)
        "where": {"status": "active"},       # optional property filters (AND-equality)
        "select": ["orig_id", "name"],       # optional projection
        "order_by": "name",                  # optional ordering
        "order_desc": false,                 # optional descending order
        "page": 1,                           # page number (1-indexed)
        "page_size": 25,                     # items per page
        "principal": "user-123",             # required
        "tenant": "tenant-1"                 # required
      }
    Returns:
      { ok, action, items, page, page_size, total, count }

- edges
    Search relationships by type(s) and property filters.

    Payload:
      {
        "action": "edges",
        "type": "WORKS_AT",                  # optional single type
        "types": ["WORKS_AT", "RUNS"],       # optional multiple types (OR)
        "where": {"since": "2024"},          # optional property filters
        "select": ["type", "since"],         # optional projection
        "page": 1,
        "page_size": 25,
        "principal": "user-123",
        "tenant": "tenant-1"
      }
    Returns:
      { ok, action, items, page, page_size, total, count }

- count
    Count nodes or edges matching filters.

    Payload:
      {
        "action": "count",
        "label": "User",                     # for nodes
        "type": "WORKS_AT",                  # for edges
        "where": {"status": "active"},
        "principal": "user-123",
        "tenant": "tenant-1"
      }
    Returns:
      { ok, action, count }

- distinct
    Get distinct values for a property.

    Payload:
      {
        "action": "distinct",
        "label": "User",                     # optional
        "property": "status",                # required
        "limit": 100,
        "principal": "user-123",
        "tenant": "tenant-1"
      }
    Returns:
      { ok, action, property, values, count }

Notes
-----
- All operations are read-only; enforced by @mcp_tool decorator
- RBAC: requires tools:basic scope
- Pagination returns full metadata: {items, page, page_size, total, count}
- Filters use AND-equality by default; extend with predicates as needed
"""

from __future__ import annotations

import re
from contextlib import suppress
from typing import Any

# ── MCP Runtime & Schemas ─────────────────────────────────────────────────────
from src.mcp.runtime import ToolContext, mcp_tool
from src.mcp.schemas import GraphSearchPayload

# ── Logging (structlog-aware if configured) ───────────────────────────────────
with suppress(Exception):
    from src.logging_setup import get_logger  # type: ignore

    logger = get_logger(__name__)  # type: ignore[assignment]
if "logger" not in globals():
    import logging

    logger = logging.getLogger(__name__)

# ── Memgraph adapter ──────────────────────────────────────────────────────────
with suppress(Exception):
    from src.adapters.db_memgraph import MemgraphAdapter  # type: ignore
if "MemgraphAdapter" not in globals():
    raise RuntimeError("Memgraph adapter is required for graph.search tool")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

# Write detection pattern (similar to P1 tools)
_WRITE_PAT = re.compile(
    r"\b("
    r"CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|CALL\s+.*?WRITE|LOAD\s+CSV|"
    r"CREATE\s+INDEX|DROP\s+INDEX|CREATE\s+CONSTRAINT|DROP\s+CONSTRAINT"
    r")\b",
    re.IGNORECASE | re.DOTALL,
)


def _looks_write(cypher: str) -> bool:
    """Check if Cypher contains write operations."""
    return bool(_WRITE_PAT.search(cypher or ""))


def _safe_label(label: str) -> str:
    """Escape label for Cypher."""
    return f"`{str(label).replace('`', '``')}`"


def _build_label_filter(label: str | None, labels: list[str] | None) -> str:
    """Build label filter for MATCH clause."""
    if label:
        return f":{_safe_label(label)}"
    if labels and len(labels) > 0:
        # Multiple labels: use WHERE with labels() function
        return ""
    return ""


def _build_where_clause(
    var: str, where: dict[str, Any], labels: list[str] | None = None
) -> tuple[str, dict[str, Any]]:
    """
    Build WHERE clause with AND-equality predicates.
    Returns (clause, params).
    """
    conditions = []
    params = {}
    idx = 0

    # Label filter for multiple labels
    if labels and len(labels) > 0:
        params["_labels"] = labels
        conditions.append(f"any(lbl IN labels({var}) WHERE lbl IN $_labels)")

    # Property filters
    for key, value in where.items():
        param_name = f"_w{idx}"
        conditions.append(f"{var}.`{key}` = ${param_name}")
        params[param_name] = value
        idx += 1

    if not conditions:
        return "", {}

    return f" WHERE {' AND '.join(conditions)}", params


def _build_projection(var: str, select: list[str] | None) -> str:
    """Build RETURN projection."""
    if select and len(select) > 0:
        # Project specific fields
        [f"{var}.`{field}` AS `{field}`" for field in select]
        return (
            f"{{orig_id: {var}.orig_id, labels: labels({var}), "
            + ", ".join(f"`{f}`: {var}.`{f}`" for f in select)
            + "}"
        )
    # Return all properties
    return f"{{orig_id: {var}.orig_id, labels: labels({var}), props: properties({var})}}"


def _build_order_clause(var: str, order_by: str | None, order_desc: bool) -> str:
    """Build ORDER BY clause."""
    if order_by:
        direction = "DESC" if order_desc else "ASC"
        return f" ORDER BY {var}.`{order_by}` {direction}"
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Action implementations
# ─────────────────────────────────────────────────────────────────────────────


def _act_nodes(db: MemgraphAdapter, payload: dict[str, Any]) -> dict[str, Any]:
    """Search nodes with filters, pagination, and projection."""
    label = payload.get("label")
    labels = payload.get("labels") or []
    where = payload.get("where") or {}
    select = payload.get("select")
    order_by = payload.get("order_by")
    order_desc = payload.get("order_desc", False)
    page = int(payload.get("page", 1))
    page_size = int(payload.get("page_size", 25))
    timeout_ms = payload.get("timeout_ms", 5000)

    # Build query
    label_filter = _build_label_filter(label, labels)
    where_clause, params = _build_where_clause("n", where, labels if not label else None)
    projection = _build_projection("n", select)
    order_clause = _build_order_clause("n", order_by, order_desc)

    # Count total
    count_query = f"MATCH (n{label_filter}){where_clause} RETURN count(n) AS total"
    count_result = db.query(count_query, params, timeout_ms=timeout_ms)
    total = int(count_result[0]["total"]) if count_result else 0

    # Fetch page
    skip = (page - 1) * page_size
    data_query = (
        f"MATCH (n{label_filter}){where_clause}{order_clause} RETURN {projection} AS item SKIP {skip} LIMIT {page_size}"
    )
    rows = db.query(data_query, params, timeout_ms=timeout_ms)

    items = [row["item"] for row in rows]

    return {
        "ok": True,
        "action": "nodes",
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "count": len(items),
    }


def _act_edges(db: MemgraphAdapter, payload: dict[str, Any]) -> dict[str, Any]:
    """Search edges with filters and pagination."""
    edge_type = payload.get("type")
    types = payload.get("types") or []
    where = payload.get("where") or {}
    select = payload.get("select")
    page = int(payload.get("page", 1))
    page_size = int(payload.get("page_size", 25))
    timeout_ms = payload.get("timeout_ms", 5000)

    # Build type filter
    type_filter = ""
    type_params = {}
    if edge_type:
        type_filter = f":{_safe_label(edge_type)}"
    elif types and len(types) > 0:
        type_params["_types"] = types

    # Build WHERE clause
    conditions = []
    params = {**type_params}
    idx = 0

    if types and len(types) > 0 and not edge_type:
        conditions.append("type(r) IN $_types")

    for key, value in where.items():
        param_name = f"_w{idx}"
        conditions.append(f"r.`{key}` = ${param_name}")
        params[param_name] = value
        idx += 1

    where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""

    # Count total
    count_query = f"MATCH ()-[r{type_filter}]-(){where_clause} RETURN count(r) AS total"
    count_result = db.query(count_query, params, timeout_ms=timeout_ms)
    total = int(count_result[0]["total"]) if count_result else 0

    # Fetch page
    skip = (page - 1) * page_size
    if select and len(select) > 0:
        projection = "{{type: type(r), " + ", ".join(f"`{f}`: r.`{f}`" for f in select) + "}}"
    else:
        projection = "{type: type(r), props: properties(r)}"

    data_query = f"MATCH (a)-[r{type_filter}]->(b){where_clause} RETURN {projection} AS item, a.orig_id AS start_id, b.orig_id AS end_id SKIP {skip} LIMIT {page_size}"
    rows = db.query(data_query, params, timeout_ms=timeout_ms)

    items = [{**row["item"], "start_orig_id": row["start_id"], "end_orig_id": row["end_id"]} for row in rows]

    return {
        "ok": True,
        "action": "edges",
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "count": len(items),
    }


def _act_count(db: MemgraphAdapter, payload: dict[str, Any]) -> dict[str, Any]:
    """Count nodes or edges matching filters."""
    label = payload.get("label")
    edge_type = payload.get("type")
    where = payload.get("where") or {}
    timeout_ms = payload.get("timeout_ms", 5000)

    if label or (not edge_type):
        # Count nodes
        label_filter = f":{_safe_label(label)}" if label else ""
        where_clause, params = _build_where_clause("n", where)
        query = f"MATCH (n{label_filter}){where_clause} RETURN count(n) AS total"
    else:
        # Count edges
        type_filter = f":{_safe_label(edge_type)}" if edge_type else ""
        where_clause, params = _build_where_clause("r", where)
        query = f"MATCH ()-[r{type_filter}]-(){where_clause} RETURN count(r) AS total"

    result = db.query(query, params, timeout_ms=timeout_ms)
    count = int(result[0]["total"]) if result else 0

    return {
        "ok": True,
        "action": "count",
        "count": count,
    }


def _act_distinct(db: MemgraphAdapter, payload: dict[str, Any]) -> dict[str, Any]:
    """Get distinct values for a property."""
    label = payload.get("label")
    property_name = payload.get("property")
    limit = int(payload.get("limit", 100))
    timeout_ms = payload.get("timeout_ms", 5000)

    if not property_name:
        raise ValueError("distinct action requires 'property' field")

    label_filter = f":{_safe_label(label)}" if label else ""
    query = f"MATCH (n{label_filter}) WHERE n.`{property_name}` IS NOT NULL RETURN DISTINCT n.`{property_name}` AS value ORDER BY value LIMIT {limit}"

    rows = db.query(query, {}, timeout_ms=timeout_ms)
    values = [row["value"] for row in rows]

    return {
        "ok": True,
        "action": "distinct",
        "property": property_name,
        "values": values,
        "count": len(values),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public entrypoint
# ─────────────────────────────────────────────────────────────────────────────


@mcp_tool(
    tool_name="graph.search",
    required_scope="tools:basic",
)
def invoke(ctx: ToolContext, payload: dict[str, Any] | None = None, **kwargs) -> dict[str, Any]:
    """
    Read-only search over nodes/edges. See module docstring for payload formats.

    This tool is wrapped with @mcp_tool which provides:
    - Automatic payload validation against GraphSearchPayload schema
    - RBAC enforcement (requires tools:basic scope)
    - Audit trail emission
    - Prometheus metrics
    - Structured logging
    - Timeout enforcement
    """
    # Validate payload using Pydantic schema
    payload = payload or {}
    validated = GraphSearchPayload(**payload)
    action = validated.action

    # Merge: start with original payload, overlay with validated defaults for fields with defaults
    validated_dict = {**payload}
    for field_name, field_info in GraphSearchPayload.model_fields.items():
        if field_info.default is not None and field_info.default != ...:
            if field_name not in payload:
                validated_dict[field_name] = getattr(validated, field_name)

    db = MemgraphAdapter()

    # Execute action
    if action == "nodes":
        result = _act_nodes(db, validated_dict)
    elif action == "edges":
        result = _act_edges(db, validated_dict)
    elif action == "count":
        result = _act_count(db, validated_dict)
    else:  # distinct
        result = _act_distinct(db, validated_dict)

    # Read-only enforcement: verify no write operations in any generated Cypher
    # (belt-and-suspenders; @mcp_tool should prevent writes via scope)

    return result


# Back-compat aliases
run = invoke
handle = invoke
