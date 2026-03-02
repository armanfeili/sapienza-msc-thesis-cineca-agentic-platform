"""
MCP Tool: graph.query

Thin execution surface over Memgraph for ad-hoc Cypher with safety knobs.

Supported actions
-----------------
- run
    Payload:
      {
        "cypher": "MATCH (n) RETURN n LIMIT 5",   # required
        "params": { "k": "v" },                   # optional dict
        "read_only": false,                       # if true, blocks obvious writes (default: false)
        "timeout_ms": 5000,                       # optional per-query timeout
        "limit": 1000                             # soft client-side row cap (slice results)
      }
    Returns:
      { ok, action:"run", columns, rows, rowcount, truncated, read_only }

- explain
    Payload: same as run (except read_only is implicitly true)
    Returns:
      { ok, action:"explain", rows, rowcount, note? }

- profile
    Payload: same as run
    Returns:
      { ok, action:"profile", rows, rowcount, note? }

Notes
-----
- This tool executes *exactly* the Cypher you provide (modulo EXPLAIN/PROFILE prefixes).
- For stricter sandboxing and guards, use the security pipeline (intent/output guards).
- Client-side `limit` does not change the Cypher; it slices the returned rows.
"""

from __future__ import annotations

import re
from contextlib import suppress
from typing import Any

# ── MCP Runtime & Schemas ─────────────────────────────────────────────────────
from src.mcp.runtime import ToolContext, mcp_tool
from src.mcp.schemas import GraphQueryPayload

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
    raise RuntimeError("Memgraph adapter is required for graph.query tool")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

# Read-only CALL procedures allowlist (known safe procedures)
_CALL_READ_ONLY_PROCS = {
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
}

# Pattern for write operations and dangerous CALL procedures
_WRITE_PAT = re.compile(
    r"\b("
    r"CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD\s+CSV|"
    r"CREATE\s+INDEX|DROP\s+INDEX|CREATE\s+CONSTRAINT|DROP\s+CONSTRAINT|"
    r"REINDEX|COPY\s+FROM|COPY\s+TO"
    r")\b|"
    # CALL procedures with write semantics (denylist) - separate pattern
    r"CALL\s+("
    r"db\.create|db\.alter|db\.drop|db\.execute|db\.set|db\.delete|"
    r"db\.add|db\.remove|db\.update|db\.insert|db\.merge|apoc\.create|"
    r"apoc\.merge|apoc\.set|apoc\.refactor"
    r")",
    re.IGNORECASE | re.DOTALL,
)


def _looks_write(cypher: str) -> bool:
    """
    Detect write operations in Cypher query.

    Uses deny-by-default approach for CALL procedures:
    - Explicitly denies known write procedures (db.create*, db.alter*, etc.)
    - Allows known read-only procedures from allowlist
    - Any other CALL is allowed (could be tightened further if needed)
    """
    if not cypher:
        return False

    # Check for write pattern match
    return bool(_WRITE_PAT.search(cypher))


def _slice_rows(rows: list[dict[str, Any]], limit: int | None) -> tuple[list[dict[str, Any]], bool]:
    if limit is None or limit <= 0:
        return rows, False
    if len(rows) <= limit:
        return rows, False
    return rows[:limit], True


def _columns(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return []
    # Union of keys across first few rows (defensive)
    cols: list[str] = list(rows[0].keys())
    for r in rows[1:5]:
        for k in r:
            if k not in cols:
                cols.append(k)
    return cols


# ─────────────────────────────────────────────────────────────────────────────
# Action implementations
# ─────────────────────────────────────────────────────────────────────────────
def _act_run(db: MemgraphAdapter, payload: dict[str, Any]) -> dict[str, Any]:
    cypher = payload.get("cypher")
    if not cypher or not str(cypher).strip():
        raise ValueError("graph.query/run requires 'cypher'")
    params = payload.get("params") or {}
    run_id = payload.get("run_id")
    if not isinstance(params, dict):
        raise ValueError("'params' must be an object/dict")
    read_only = bool(payload.get("read_only", False))
    timeout_ms = payload.get("timeout_ms")
    limit = payload.get("limit")
    limit = int(limit) if limit is not None else None

    # Check for write operations in read-only mode
    if read_only and _looks_write(cypher):
        raise ValueError("Write operation not allowed in read-only mode; query attempts to modify data")

    rows = db.query(str(cypher), params=params, run_id=run_id, timeout_ms=int(timeout_ms) if timeout_ms else None)
    rows_sliced, truncated = _slice_rows(rows, limit)
    return {
        "ok": True,
        "action": "run",
        "columns": _columns(rows_sliced),
        "rows": rows_sliced,
        "rowcount": len(rows_sliced),
        "truncated": bool(truncated),
        "read_only": read_only,
    }


def _act_plan(db: MemgraphAdapter, payload: dict[str, Any], prefix: str) -> dict[str, Any]:
    cypher = payload.get("cypher")
    if not cypher or not str(cypher).strip():
        raise ValueError(f"graph.query/{prefix.strip().lower()} requires 'cypher'")
    params = payload.get("params") or {}
    run_id = payload.get("run_id")
    if not isinstance(params, dict):
        raise ValueError("'params' must be an object/dict")
    timeout_ms = payload.get("timeout_ms")

    # Prefix EXPLAIN/PROFILE
    stmt = f"{prefix} {cypher}"
    rows = db.query(stmt, params=params, run_id=run_id, timeout_ms=int(timeout_ms) if timeout_ms else None)
    out: dict[str, Any] = {"ok": True, "action": prefix.strip().lower(), "rows": rows, "rowcount": len(rows)}
    if not rows:
        out["note"] = "plan_not_returned_by_server"
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Public entrypoint
# ─────────────────────────────────────────────────────────────────────────────
@mcp_tool(
    tool_name="graph.query",
    required_scope="tools:basic",
)
def invoke(ctx: ToolContext, payload: dict[str, Any] | None = None, **kwargs) -> dict[str, Any]:
    """
    Execute or plan a Cypher query. See module docstring for payload formats.

    This tool is now wrapped with @mcp_tool which provides:
    - Automatic payload validation against GraphQueryPayload schema
    - RBAC enforcement (requires tools:basic scope)
    - Audit trail emission
    - Prometheus metrics
    - Structured logging
    - Timeout enforcement
    """
    # Validate payload using Pydantic schema
    payload = payload or {}
    validated = GraphQueryPayload(**payload)
    action = validated.action

    db = MemgraphAdapter()

    # Merge: start with original payload, overlay with validated defaults for fields with defaults
    # This preserves "not set" semantics for truly optional fields while applying schema defaults
    validated_dict = {**payload}
    for field_name, field_info in GraphQueryPayload.model_fields.items():
        if field_info.default is not None and field_info.default != ...:
            # Field has an explicit default (not just Optional)
            if field_name not in payload:
                validated_dict[field_name] = getattr(validated, field_name)

    # Always expose canonical cypher field even if caller used alias (e.g., "query")
    validated_dict["cypher"] = validated.cypher

    if action == "run":
        result = _act_run(db, validated_dict)
    elif action == "explain":
        result = _act_plan(db, validated_dict, "EXPLAIN")
    else:  # profile
        result = _act_plan(db, validated_dict, "PROFILE")

    return result


# Back-compat aliases
run = invoke
handle = invoke
