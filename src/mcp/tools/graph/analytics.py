"""
MCP Tool: graph.analytics

Graph analytics operations over Memgraph with bounded computation.

Supported actions
-----------------
- degree_distribution
    Get degree distribution statistics for nodes.

    Payload:
      {
        "action": "degree_distribution",
        "label": "User",                     # optional label filter
        "row_limit": 1000,                   # max distribution buckets
        "timeout_ms": 5000,
        "principal": "user-123",
        "tenant": "tenant-1"
      }
    Returns:
      { ok, action, label, summary: {min, max, avg}, distribution: [{degree, count}] }

- shortest_path
    Find shortest path between two nodes.

    Payload:
      {
        "action": "shortest_path",
        "start_id": "user-1",                # required start node orig_id
        "end_id": "user-2",                  # required end node orig_id
        "max_depth": 5,                      # max hops (1-10)
        "timeout_ms": 5000,
        "principal": "user-123",
        "tenant": "tenant-1"
      }
    Returns:
      { ok, action, found, length, path: {nodes: [...], edges: [...]} }

- top_k_degree
    Get top-k nodes by degree (most connected).

    Payload:
      {
        "action": "top_k_degree",
        "label": "User",                     # optional label filter
        "k": 10,                             # number of top nodes (1-100)
        "timeout_ms": 5000,
        "principal": "user-123",
        "tenant": "tenant-1"
      }
    Returns:
      { ok, action, label, k, items: [{orig_id, labels, degree}] }

- label_counts
    Count nodes grouped by label.

    Payload:
      {
        "action": "label_counts",
        "timeout_ms": 5000,
        "principal": "user-123",
        "tenant": "tenant-1"
      }
    Returns:
      { ok, action, items: [{label, count}] }

- relationship_counts
    Count relationships grouped by type.

    Payload:
      {
        "action": "relationship_counts",
        "timeout_ms": 5000,
        "principal": "user-123",
        "tenant": "tenant-1"
      }
    Returns:
      { ok, action, items: [{type, count}] }

Notes
-----
- All operations are read-only; enforced by @mcp_tool decorator
- RBAC: requires tools:basic scope
- Bounded computations with timeout_ms, row_limit, max_depth, k constraints
- No vendor-specific procedures (portable Cypher only)
"""

from __future__ import annotations

from contextlib import suppress
from typing import Any

# ── MCP Runtime & Schemas ─────────────────────────────────────────────────────
from src.mcp.runtime import ToolContext, mcp_tool
from src.mcp.schemas import GraphAnalyticsPayload

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
    raise RuntimeError("Memgraph adapter is required for graph.analytics tool")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _safe_label(label: str | None) -> str:
    """Build safe label filter for Cypher."""
    if not label:
        return ""
    return f":`{str(label).replace('`', '``')}`"


# ─────────────────────────────────────────────────────────────────────────────
# Action implementations
# ─────────────────────────────────────────────────────────────────────────────


def _act_degree_distribution(db: MemgraphAdapter, payload: dict[str, Any]) -> dict[str, Any]:
    """Compute degree distribution for nodes."""
    label = payload.get("label")
    row_limit = int(payload.get("row_limit", 1000))
    timeout_ms = payload.get("timeout_ms", 5000)

    label_filter = _safe_label(label)

    # Get distribution
    dist_query = f"""
        MATCH (n{label_filter})
        WITH size((n)--()) AS degree
        RETURN degree, count(*) AS count
        ORDER BY degree ASC
        LIMIT {row_limit}
    """
    dist_rows = db.query(dist_query, {}, timeout_ms=timeout_ms)
    distribution = [{"degree": int(r["degree"]), "count": int(r["count"])} for r in dist_rows]

    # Get summary statistics
    summary_query = f"""
        MATCH (n{label_filter})
        WITH size((n)--()) AS degree
        RETURN min(degree) AS min, max(degree) AS max, avg(degree) AS avg
    """
    summary_rows = db.query(summary_query, {}, timeout_ms=timeout_ms)
    summary = {}
    if summary_rows:
        row = summary_rows[0]
        summary = {
            "min": int(row["min"]) if row["min"] is not None else 0,
            "max": int(row["max"]) if row["max"] is not None else 0,
            "avg": float(row["avg"]) if row["avg"] is not None else 0.0,
        }

    return {
        "ok": True,
        "action": "degree_distribution",
        "label": label,
        "summary": summary,
        "distribution": distribution,
    }


def _act_shortest_path(db: MemgraphAdapter, payload: dict[str, Any]) -> dict[str, Any]:
    """Find shortest path between two nodes."""
    start_id = payload.get("start_id")
    end_id = payload.get("end_id")
    max_depth = int(payload.get("max_depth", 5))
    timeout_ms = payload.get("timeout_ms", 5000)

    if not start_id or not end_id:
        raise ValueError("shortest_path requires both start_id and end_id")

    # Find shortest path with depth limit
    query = (
        """
        MATCH (start {orig_id: $start_id})
        MATCH (end {orig_id: $end_id})
        MATCH path = shortestPath((start)-[*..%d]-(end))
        RETURN
            length(path) AS length,
            [n IN nodes(path) | {orig_id: n.orig_id, labels: labels(n)}] AS nodes,
            [r IN relationships(path) | {type: type(r)}] AS edges
        LIMIT 1
    """
        % max_depth
    )

    params = {"start_id": start_id, "end_id": end_id}
    rows = db.query(query, params, timeout_ms=timeout_ms)

    if not rows:
        return {
            "ok": True,
            "action": "shortest_path",
            "found": False,
            "length": None,
            "path": None,
        }

    row = rows[0]
    return {
        "ok": True,
        "action": "shortest_path",
        "found": True,
        "length": int(row["length"]),
        "path": {
            "nodes": row["nodes"],
            "edges": row["edges"],
        },
    }


def _act_top_k_degree(db: MemgraphAdapter, payload: dict[str, Any]) -> dict[str, Any]:
    """Get top-k nodes by degree."""
    label = payload.get("label")
    k = int(payload.get("k", 10))
    timeout_ms = payload.get("timeout_ms", 5000)

    label_filter = _safe_label(label)

    query = f"""
        MATCH (n{label_filter})
        WITH n, size((n)--()) AS degree
        ORDER BY degree DESC
        LIMIT {k}
        RETURN n.orig_id AS orig_id, labels(n) AS labels, degree
    """

    rows = db.query(query, {}, timeout_ms=timeout_ms)
    items = [
        {
            "orig_id": row["orig_id"],
            "labels": row["labels"],
            "degree": int(row["degree"]),
        }
        for row in rows
    ]

    return {
        "ok": True,
        "action": "top_k_degree",
        "label": label,
        "k": k,
        "items": items,
    }


def _act_label_counts(db: MemgraphAdapter, payload: dict[str, Any]) -> dict[str, Any]:
    """Count nodes grouped by label."""
    timeout_ms = payload.get("timeout_ms", 5000)

    query = """
        MATCH (n)
        UNWIND labels(n) AS label
        RETURN label, count(*) AS count
        ORDER BY count DESC
    """

    rows = db.query(query, {}, timeout_ms=timeout_ms)
    items = [{"label": row["label"], "count": int(row["count"])} for row in rows]

    return {
        "ok": True,
        "action": "label_counts",
        "items": items,
    }


def _act_relationship_counts(db: MemgraphAdapter, payload: dict[str, Any]) -> dict[str, Any]:
    """Count relationships grouped by type."""
    timeout_ms = payload.get("timeout_ms", 5000)

    query = """
        MATCH ()-[r]->()
        RETURN type(r) AS type, count(*) AS count
        ORDER BY count DESC
    """

    rows = db.query(query, {}, timeout_ms=timeout_ms)
    items = [{"type": row["type"], "count": int(row["count"])} for row in rows]

    return {
        "ok": True,
        "action": "relationship_counts",
        "items": items,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public entrypoint
# ─────────────────────────────────────────────────────────────────────────────


@mcp_tool(
    tool_name="graph.analytics",
    required_scope="tools:basic",
)
def invoke(ctx: ToolContext, payload: dict[str, Any] | None = None, **kwargs) -> dict[str, Any]:
    """
    Graph analytics operations. See module docstring for payload formats.

    This tool is wrapped with @mcp_tool which provides:
    - Automatic payload validation against GraphAnalyticsPayload schema
    - RBAC enforcement (requires tools:basic scope)
    - Audit trail emission
    - Prometheus metrics
    - Structured logging
    - Timeout enforcement
    """
    # Validate payload using Pydantic schema
    payload = payload or {}
    validated = GraphAnalyticsPayload(**payload)
    action = validated.action

    # Merge: start with original payload, overlay with validated defaults
    validated_dict = {**payload}
    for field_name, field_info in GraphAnalyticsPayload.model_fields.items():
        if field_info.default is not None and field_info.default != ...:
            if field_name not in payload:
                validated_dict[field_name] = getattr(validated, field_name)

    db = MemgraphAdapter()

    # Execute action
    if action == "degree_distribution":
        result = _act_degree_distribution(db, validated_dict)
    elif action == "shortest_path":
        result = _act_shortest_path(db, validated_dict)
    elif action == "top_k_degree":
        result = _act_top_k_degree(db, validated_dict)
    elif action == "label_counts":
        result = _act_label_counts(db, validated_dict)
    else:  # relationship_counts
        result = _act_relationship_counts(db, validated_dict)

    return result


# Back-compat aliases
run = invoke
handle = invoke
