"""
MCP Tool: graph.generate_cypher

Generates safe, parameterized Cypher snippets (without executing them).

Why?
-----
- Keep execution concerns separate (use graph.query / graph.crud / graph.bulk to run).
- Produce portable Cypher for Memgraph/Neo4j-style engines.
- Encourage parameterization to avoid injection.

Supported actions
-----------------
- select
    Payload:
      {
        "label": "User",                 # optional
        "where": {"email":"a@b"},        # optional equality ANDed
        "return": ["orig_id","email"],   # optional; defaults to ["n"]
        "limit": 25                      # optional
      }
    → Returns a single query + params.

- insert_node
    Payload:
      {
        "labels": ["User"],              # required, non-empty
        "orig_id": "uuid-1",             # optional but recommended; used as MERGE key
        "props": {"firstName":"Ana"},    # optional
        "mode": "merge" | "create"       # default "merge"
      }

- update_node
    Payload:
      { "orig_id": "uuid-1", "props": {"email":"x@y"} }

- delete_node
    Payload:
      { "orig_id": "uuid-1", "detach": true }  # detach default true

- upsert_rel
    Payload:
      {
        "start_orig_id": "uuid-1",
        "end_orig_id":   "uuid-2",
        "type": "RUNS",
        "props": {"since":"2024-01-01"}
      }

- match_rel
    Payload:
      {
        "type": "RUNS",                   # optional
        "from_label": "User",             # optional
        "to_label": "Task",               # optional
        "from_where": {"user_id":"..."},  # optional equality ANDed
        "to_where": {"status":"Done"},    # optional equality ANDed
        "limit": 100
      }

- count_by_label
    Payload: {}
    → Returns label counts.

- schema_inventory
    Payload: {}
    → Returns a multi-statement "schema inventory" query (read-only), same shape
      as db/sample_queries.txt header inventory (portable, no APOC).

Return shape
------------
- For single statement:
  { ok, action, read_only, cypher, params }

- For multi statement:
  { ok, action, read_only, queries: [ {cypher, params, description?}, ... ] }
"""

from __future__ import annotations

from contextlib import suppress
import re
from typing import Any

# ── P0 Runtime Infrastructure ─────────────────────────────────────────────────
from src.mcp.runtime import ToolContext, mcp_tool
from src.mcp.schemas import GraphGenerateCypherPayload

# ── Logging (structlog-aware if configured) ───────────────────────────────────
with suppress(Exception):
    from src.logging_setup import get_logger  # type: ignore

    logger = get_logger(__name__)  # type: ignore[assignment]
if "logger" not in globals():
    import logging

    logger = logging.getLogger(__name__)

logger.info("mcp.graph_generate_cypher.loaded", file_path=__file__)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _q_label(label: str) -> str:
    return f"`{str(label).replace('`', '``')}`"


def _labels_expr(labels: list[str]) -> str:
    if not labels or not isinstance(labels, list):
        raise ValueError("labels must be a non-empty list")
    return ":".join(_q_label(l) for l in labels if str(l).strip())


def _build_where(var: str, where: dict[str, Any] | None) -> tuple[str, dict[str, Any]]:
    if not where:
        return "", {}
    parts: list[str] = []
    params: dict[str, Any] = {}
    i = 0
    for k, v in where.items():
        pname = f"{var}_w_{i}"
        parts.append(f"{var}.`{k}` = ${pname}")
        params[pname] = v
        i += 1
    return (" WHERE " + " AND ".join(parts), params)


def _return_expr(ret: list[str] | None) -> str:
    if not ret:
        return "n"
    fields: list[str] = []
    for r in ret:
        if r in {"n", "a", "b", "r"}:
            fields.append(r)
        else:
            # Treat as property on n by default (common case)
            fields.append(f"n.`{r}` AS {r}")
    return ", ".join(fields)


# ─────────────────────────────────────────────────────────────────────────────
# Action builders
# ─────────────────────────────────────────────────────────────────────────────
def _act_select(payload: dict[str, Any]) -> dict[str, Any]:
    label = payload.get("label")
    where = payload.get("where") or {}
    ret = payload.get("return")
    # Support both 'limit' and 'limit_hint' for catalog compatibility
    limit = int(payload.get("limit") or payload.get("limit_hint") or 25)
    # Support random sampling via ORDER BY rand()
    needs_random = payload.get("random", False)

    lbl = f":{_q_label(label)}" if label else ""
    clause, params = _build_where("n", where)
    
    # Build optional ORDER BY clause for random sampling
    order_clause = " ORDER BY rand()" if needs_random else ""
    
    cypher = f"MATCH (n{lbl}){clause} RETURN {_return_expr(ret)}{order_clause} LIMIT $limit"
    params["limit"] = limit
    return {"ok": True, "action": "select", "read_only": True, "cypher": cypher, "params": params}


def _act_insert_node(payload: dict[str, Any]) -> dict[str, Any]:
    labels = payload.get("labels") or []
    props = payload.get("props") or {}
    mode = (payload.get("mode") or "merge").lower()
    lab = _labels_expr(labels)

    orig_id = payload.get("orig_id")
    if mode not in {"merge", "create"}:
        raise ValueError("mode must be 'merge' or 'create'")

    if orig_id:
        if mode == "merge":
            cypher = f"MERGE (n:{lab} {{orig_id:$orig_id}}) SET n += $props RETURN n"
        else:  # create
            cypher = f"CREATE (n:{lab} {{orig_id:$orig_id}}) SET n += $props RETURN n"
        params = {"orig_id": orig_id, "props": props}
    else:
        if mode == "merge":
            # Without a key merge is ambiguous; fall back to CREATE semantics
            mode = "create"
        cypher = f"CREATE (n:{lab}) SET n = $props RETURN n"
        params = {"props": props}

    return {"ok": True, "action": "insert_node", "read_only": False, "cypher": cypher, "params": params}


def _act_update_node(payload: dict[str, Any]) -> dict[str, Any]:
    orig_id = payload.get("orig_id")
    props = payload.get("props") or {}
    if not orig_id:
        raise ValueError("update_node requires 'orig_id'")
    cypher = "MATCH (n {orig_id:$id}) SET n += $props RETURN n"
    params = {"id": orig_id, "props": props}
    return {"ok": True, "action": "update_node", "read_only": False, "cypher": cypher, "params": params}


def _act_delete_node(payload: dict[str, Any]) -> dict[str, Any]:
    orig_id = payload.get("orig_id")
    detach = bool(payload.get("detach", True))
    if not orig_id:
        raise ValueError("delete_node requires 'orig_id'")
    if detach:
        cypher = "MATCH (n {orig_id:$id}) DETACH DELETE n"
    else:
        cypher = "MATCH (n {orig_id:$id}) DELETE n"
    params = {"id": orig_id}
    return {"ok": True, "action": "delete_node", "read_only": False, "cypher": cypher, "params": params}


def _act_upsert_rel(payload: dict[str, Any]) -> dict[str, Any]:
    a = payload.get("start_orig_id")
    b = payload.get("end_orig_id")
    typ = payload.get("type")
    props = payload.get("props") or {}
    if not (a and b and typ):
        raise ValueError("upsert_rel requires start_orig_id, end_orig_id, and type")
    cypher = (
        "MATCH (x {orig_id:$a}), (y {orig_id:$b}) "
        f"MERGE (x)-[r:`{typ}`]->(y) "
        "SET r += $props "
        "RETURN type(r) AS type, properties(r) AS props"
    )
    params = {"a": a, "b": b, "props": props}
    return {"ok": True, "action": "upsert_rel", "read_only": False, "cypher": cypher, "params": params}


def _act_match_rel(payload: dict[str, Any]) -> dict[str, Any]:
    typ = payload.get("type")
    from_label = payload.get("from_label")
    to_label = payload.get("to_label")
    from_where = payload.get("from_where") or {}
    to_where = payload.get("to_where") or {}
    limit = int(payload.get("limit") or 100)

    a_lbl = f":{_q_label(from_label)}" if from_label else ""
    b_lbl = f":{_q_label(to_label)}" if to_label else ""
    rel = f":`{typ}`" if typ else ""
    a_clause, a_params = _build_where("a", from_where)
    b_clause, b_params = _build_where("b", to_where)

    # When both sides have WHERE, combine with AND
    where_suffix = ""
    if a_clause and b_clause:
        where_suffix = a_clause + " AND " + b_clause.replace(" WHERE ", "")
    else:
        where_suffix = a_clause or b_clause

    cypher = (
        f"MATCH (a{a_lbl})-[r{rel}]->(b{b_lbl})"
        f"{where_suffix} "
        "RETURN labels(a) AS from_labels, a.orig_id AS from_id, "
        "type(r) AS rel_type, properties(r) AS rel_props, "
        "labels(b) AS to_labels, b.orig_id AS to_id "
        "LIMIT $limit"
    )
    params = {**a_params, **b_params, "limit": limit}
    return {"ok": True, "action": "match_rel", "read_only": True, "cypher": cypher, "params": params}


def _act_count_by_label() -> dict[str, Any]:
    cypher = "MATCH (n) UNWIND labels(n) AS lbl " "RETURN lbl AS label, count(*) AS count " "ORDER BY count DESC"
    return {"ok": True, "action": "count_by_label", "read_only": True, "cypher": cypher, "params": {}}


def _act_schema_inventory() -> dict[str, Any]:
    # Portable inventory query derived from db/sample_queries.txt
    inv = r"""
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
    return {"ok": True, "action": "schema_inventory", "read_only": True, "cypher": inv.strip(), "params": {}}


def _infer_label_from_goal(goal: str | None) -> str | None:
    """Extract :Label from a natural-language goal string."""
    if not goal:
        return None
    match = re.search(r":([A-Za-z][A-Za-z0-9_]*)", goal)
    if match:
        return match.group(1)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Public entrypoint
# ─────────────────────────────────────────────────────────────────────────────
@mcp_tool(tool_name="graph.generate_cypher", required_scope="tools:basic")
def invoke(ctx: ToolContext, payload: dict[str, Any] | None = None, **kwargs) -> dict[str, Any]:
    """
    Generate Cypher for the requested action. See module docstring for payloads.
    """
    payload = dict(payload or {})
    goal_text = payload.get("goal") or payload.get("prompt")
    if goal_text and not payload.get("label") and not payload.get("query"):
        inferred = _infer_label_from_goal(goal_text)
        if inferred:
            payload["label"] = inferred

    # Validate payload with Pydantic schema
    validated = GraphGenerateCypherPayload(**payload)
    action = validated.action

    # Merge: start with original payload, overlay with validated defaults for fields with defaults
    validated_dict = {**payload}
    for field_name, field_info in GraphGenerateCypherPayload.model_fields.items():
        if field_info.default is not None and field_info.default != ...:
            if field_name not in payload:
                validated_dict[field_name] = getattr(validated, field_name)

    if action == "select":
        result = _act_select(validated_dict)
    elif action == "insert_node":
        result = _act_insert_node(validated_dict)
    elif action == "update_node":
        result = _act_update_node(validated_dict)
    elif action == "delete_node":
        result = _act_delete_node(validated_dict)
    elif action == "upsert_rel":
        result = _act_upsert_rel(validated_dict)
    elif action == "match_rel":
        result = _act_match_rel(validated_dict)
    elif action == "count_by_label":
        result = _act_count_by_label()
    else:  # schema_inventory
        result = _act_schema_inventory()

    return result


# Back-compat aliases
run = invoke
handle = invoke
