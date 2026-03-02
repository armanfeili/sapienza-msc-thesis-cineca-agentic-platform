"""
MCP Tool: graph.schema

Schema discovery utilities for Memgraph (portable Cypher wherever possible).

Supported actions
-----------------
- labels
    Payload: {}
    Returns: { ok, action, items: [ "User", "Task", ... ] }

- relationship_types
    Payload: {}
    Returns: { ok, action, items: [ "RUNS", "WORKS_AT", ... ] }

- node_properties
    Payload: { "label": "User" }   # optional filter
    Returns: { ok, action, label, items: [ "firstName", "email", ... ] }

- relationship_properties
    Payload: { "type": "RUNS" }    # optional filter
    Returns: { ok, action, type, items: [ "since", ... ] }

- node_counts
    Payload: {}
    Returns: { ok, action, items: [ {label, count}, ... ] }

- relationship_counts
    Payload: {}
    Returns: { ok, action, items: [ {type, count}, ... ] }

- indexes
    Payload: {}
    Returns: { ok, action, items: [ {label, properties?, type?, state?, ...}, ... ] }
    Notes: Uses `SHOW INDEX INFO` when available; falls back to a portable
           approximation (empty list) if not supported by the server.

- constraints
    Payload: {}
    Returns: { ok, action, items: [...] }
    Notes: Enterprise-only on Memgraph; returns empty array on community/fail.

- inventory
    Payload: {}
    Returns a portable, denormalized inventory similar to db/sample_queries.txt
    header query:
      { ok, action, columns:[...], rows:[{...}, ...], rowcount }

All queries are read-only.
"""

from __future__ import annotations

from contextlib import suppress
from typing import Any

# ── P0 Runtime Infrastructure ─────────────────────────────────────────────────
from src.mcp.runtime import ToolContext, mcp_tool
from src.mcp.schemas import GraphSchemaPayload

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
    raise RuntimeError("Memgraph adapter is required for graph.schema tool")

# ── Audit (best-effort) ──────────────────────────────────────────────────────
with suppress(Exception):
    from src.security.audit import audit_access  # type: ignore
if "audit_access" not in globals():

    def audit_access(**_: Any) -> None:  # type: ignore
        return


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _q_label(label: str) -> str:
    return f"`{str(label).replace('`', '``')}`"


def _columns(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return []
    cols: list[str] = list(rows[0].keys())
    for r in rows[1:5]:
        for k in r:
            if k not in cols:
                cols.append(k)
    return cols


# ─────────────────────────────────────────────────────────────────────────────
# Actions
# ─────────────────────────────────────────────────────────────────────────────
def _act_labels(db: MemgraphAdapter) -> dict[str, Any]:
    rows = db.query(
        """
        MATCH (n)
        WITH DISTINCT labels(n) AS lbls
        UNWIND lbls AS label
        RETURN DISTINCT label
        ORDER BY label
        """
    )
    items = [r["label"] for r in rows if r.get("label") is not None]
    return {"ok": True, "action": "labels", "items": items}


def _act_relationship_types(db: MemgraphAdapter) -> dict[str, Any]:
    rows = db.query(
        """
        MATCH ()-[r]->()
        RETURN DISTINCT type(r) AS relationship_type
        ORDER BY relationship_type
        """
    )
    items = [r["relationship_type"] for r in rows if r.get("relationship_type") is not None]
    return {"ok": True, "action": "relationship_types", "items": items}


def _act_node_properties(db: MemgraphAdapter, payload: dict[str, Any]) -> dict[str, Any]:
    label = payload.get("label")
    if label:
        rows = db.query(
            f"""
            MATCH (n:{_q_label(label)})
            UNWIND keys(n) AS k
            RETURN DISTINCT k
            ORDER BY k
            """
        )
    else:
        rows = db.query(
            """
            MATCH (n)
            UNWIND keys(n) AS k
            RETURN DISTINCT k
            ORDER BY k
            """
        )
    items = [r["k"] for r in rows if r.get("k") is not None]
    return {"ok": True, "action": "node_properties", "label": label, "items": items}


def _act_relationship_properties(db: MemgraphAdapter, payload: dict[str, Any]) -> dict[str, Any]:
    typ = payload.get("type")
    if typ:
        rows = db.query(
            f"""
            MATCH ()-[r:`{typ}`]->()
            UNWIND keys(r) AS k
            RETURN DISTINCT k
            ORDER BY k
            """
        )
    else:
        rows = db.query(
            """
            MATCH ()-[r]->()
            UNWIND keys(r) AS k
            RETURN DISTINCT k
            ORDER BY k
            """
        )
    items = [r["k"] for r in rows if r.get("k") is not None]
    return {"ok": True, "action": "relationship_properties", "type": typ, "items": items}


def _act_node_counts(db: MemgraphAdapter) -> dict[str, Any]:
    rows = db.query(
        """
        MATCH (n)
        UNWIND labels(n) AS lbl
        RETURN lbl AS label, count(*) AS count
        ORDER BY count DESC
        """
    )
    items = [{"label": r["label"], "count": int(r["count"])} for r in rows]
    return {"ok": True, "action": "node_counts", "items": items}


def _act_relationship_counts(db: MemgraphAdapter) -> dict[str, Any]:
    rows = db.query(
        """
        MATCH ()-[r]->()
        RETURN type(r) AS type, count(r) AS count
        ORDER BY count DESC
        """
    )
    items = [{"type": r["type"], "count": int(r["count"])} for r in rows]
    return {"ok": True, "action": "relationship_counts", "items": items}


def _act_indexes(db: MemgraphAdapter) -> dict[str, Any]:
    # Try Memgraph ≥ 2.11
    try:
        rows = db.query("SHOW INDEX INFO")
        return {"ok": True, "action": "indexes", "items": rows}
    except Exception as e:  # pragma: no cover
        logger.debug("show_index_info_failed", error=str(e))
        # Fallback: return empty if unsupported
        return {"ok": True, "action": "indexes", "items": []}


def _act_constraints(db: MemgraphAdapter) -> dict[str, Any]:
    try:
        rows = db.query("SHOW CONSTRAINT INFO")
        return {"ok": True, "action": "constraints", "items": rows}
    except Exception as e:  # pragma: no cover
        logger.debug("show_constraint_info_failed", error=str(e))
        return {"ok": True, "action": "constraints", "items": []}


def _act_inventory(db: MemgraphAdapter) -> dict[str, Any]:
    cypher = r"""
CALL {

  MATCH (a)-[r]->(b)
  WITH
    type(r)                         AS _label,
    labels(a)[0]                    AS _property,
    count(*)                        AS _count,
    collect(DISTINCT labels(b)[0])  AS _targets
  RETURN
    _label          AS label,
    _property       AS property,
    _count          AS count,
    false           AS unique,
    false           AS index,
    false           AS existence,
    'RELATIONSHIP'  AS type,
    false           AS array,
    null            AS sample,
    1               AS left,
    0               AS right,
    '[' + reduce(s = '', x IN _targets |
           s + CASE s WHEN '' THEN '"' + x + '"' ELSE ', "' + x + '"' END) + ']'
                     AS other,
    '[]'            AS otherLabels,
    'relationship'  AS elementType

  UNION ALL

  MATCH (n)-[r]->(m)
  UNWIND labels(n) AS lbl
  WITH
    lbl                              AS _label,
    type(r)                          AS _property,
    count(*)                         AS _count,
    collect(DISTINCT labels(m)[0])   AS _targets
  RETURN
    _label          AS label,
    _property       AS property,
    _count          AS count,
    false           AS unique,
    false           AS index,
    false           AS existence,
    'RELATIONSHIP'  AS type,
    false           AS array,
    null            AS sample,
    size(_targets)  AS left,
    0               AS right,
    '[' + reduce(s = '', x IN _targets |
           s + CASE s WHEN '' THEN '"' + x + '"' ELSE ', "' + x + '"' END) + ']'
                     AS other,
    '[]'            AS otherLabels,
    'node'          AS elementType

  UNION ALL

  MATCH (n)
  UNWIND labels(n) AS lbl
  UNWIND keys(n)   AS prop
  WITH
    lbl             AS _label,
    prop            AS _property,
    count(*)        AS _count
  RETURN
    _label          AS label,
    _property       AS property,
    _count          AS count,
    false           AS unique,
    false           AS index,
    false           AS existence,
    'STRING'        AS type,
    false           AS array,
    null            AS sample,
    0               AS left,
    0               AS right,
    '[]'            AS other,
    '[]'            AS otherLabels,
    'node'          AS elementType
}

RETURN
  label,
  property,
  count,
  unique,
  index,
  existence,
  type,
  array,
  sample,
  left,
  right,
  other,
  otherLabels,
  elementType
ORDER BY elementType, label, property
"""
    rows = db.query(cypher)
    return {"ok": True, "action": "inventory", "columns": _columns(rows), "rows": rows, "rowcount": len(rows)}


# ─────────────────────────────────────────────────────────────────────────────
# Public entrypoint
# ─────────────────────────────────────────────────────────────────────────────
@mcp_tool(tool_name="graph.schema", required_scope="tools:basic")
def invoke(ctx: ToolContext, payload: dict[str, Any] | None = None, **kwargs) -> dict[str, Any]:
    """
    Schema discovery entrypoint. See module docstring for action list.
    """
    payload = payload or {}

    # Pydantic validation
    validated = GraphSchemaPayload(**payload)
    action = validated.action

    # Merge: start with original payload, overlay with validated defaults for fields with defaults
    validated_dict = {**payload}
    for field_name, field_info in GraphSchemaPayload.model_fields.items():
        if field_info.default is not None and field_info.default != ...:
            if field_name not in payload:
                validated_dict[field_name] = getattr(validated, field_name)

    db = MemgraphAdapter()

    if action == "labels":
        result = _act_labels(db)
    elif action == "relationship_types":
        result = _act_relationship_types(db)
    elif action == "node_properties":
        result = _act_node_properties(db, validated_dict)
    elif action == "relationship_properties":
        result = _act_relationship_properties(db, validated_dict)
    elif action == "node_counts":
        result = _act_node_counts(db)
    elif action == "relationship_counts":
        result = _act_relationship_counts(db)
    elif action == "indexes":
        result = _act_indexes(db)
    elif action == "constraints":
        result = _act_constraints(db)
    else:  # inventory
        result = _act_inventory(db)

    return result


# Back-compat aliases
run = invoke
handle = invoke
