"""
MCP Tool: data.archive

Soft-delete (archive), restore, purge, and inspect archived nodes in Memgraph.

Actions
-------
- mark
    Payload:
      {
        "label": "User",               # optional; restrict to label
        "where": {"user_id": "..."},   # optional; exact-match filters (ANDed)
        "orig_ids": ["...","..."]      # optional; match by orig_id list
      }
    Effect: SET n.archived = true, n.archived_at = <epoch_seconds>

- restore
    Payload: same shape as "mark"
    Effect: SET n.archived = false, REMOVE n.archived_at

- purge
    Payload:
      {
        "label": "User",               # optional
        "where": {...},                # optional
        "orig_ids": [...],             # optional
        "only_archived": true,         # default true
        "older_than_days": 30          # optional; keep newer archives
      }
    Effect: DETACH DELETE matched nodes. Returns count deleted.

- status
    Payload:
      {
        "label": "User"                # optional; restrict aggregation
      }
    Effect: Report counts for archived nodes (overall + by label).

- list
    Payload:
      {
        "label": "User",               # optional
        "limit": 50,                   # default 50
        "where": {...}                 # optional
      }
    Effect: Return sample archived nodes (lightweight fields).

Safety
------
- For "mark" and "restore", if no filters are supplied at all (no label, no where,
  no orig_ids) the call is rejected to prevent mass updates by accident.
- For "purge", `only_archived` defaults to true to avoid destructive mistakes.

Notes
-----
- Requires the Memgraph adapter: src.adapters.db_memgraph.MemgraphAdapter
- Uses integer epoch seconds for `archived_at` to avoid datetime dialect issues.
"""

from __future__ import annotations

import time
from contextlib import suppress
from typing import Any

# Mark as potentially long-running on large datasets
LONG_RUNNING = True

# ── Logging (structlog-aware if configured) ───────────────────────────────────
with suppress(Exception):
    from src.logging_setup import get_logger  # type: ignore

    logger = get_logger(__name__)  # type: ignore[assignment]
if "logger" not in globals():
    import logging

    logger = logging.getLogger(__name__)

# ── MCP Framework ─────────────────────────────────────────────────────────────
from src.mcp.runtime import ToolContext, mcp_tool

# ── Memgraph adapter ──────────────────────────────────────────────────────────
with suppress(Exception):
    from src.adapters.db_memgraph import MemgraphAdapter  # type: ignore
if "MemgraphAdapter" not in globals():
    raise RuntimeError("Memgraph adapter is required for data.archive tool")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _ensure_filters_present(
    action: str, label: str | None, where: dict[str, Any] | None, orig_ids: list[Any] | None
) -> None:
    if action in {"mark", "restore"} and not label and not where and not orig_ids:
        raise ValueError(f"{action} requires at least one filter (label, where, or orig_ids)")


def _build_match(
    label: str | None, where: dict[str, Any] | None, orig_ids: list[Any] | None
) -> tuple[str, dict[str, Any]]:
    """
    Build a MATCH ... WHERE ... clause and parameter dict.
    """
    lbl = f":`{label}`" if label else ""
    conds: list[str] = []
    params: dict[str, Any] = {}
    if orig_ids:
        conds.append("n.orig_id IN $orig_ids")
        params["orig_ids"] = list(orig_ids)
    if where:
        i = 0
        for k, v in where.items():
            pname = f"w_{i}"
            conds.append(f"n.`{k}` = ${pname}")
            params[pname] = v
            i += 1
    where_clause = f" WHERE {' AND '.join(conds)}" if conds else ""
    return f"MATCH (n{lbl}){where_clause}", params


# ─────────────────────────────────────────────────────────────────────────────
# Action implementations
# ─────────────────────────────────────────────────────────────────────────────
def _act_mark(db: MemgraphAdapter, payload: dict[str, Any]) -> dict[str, Any]:
    label = payload.get("label")
    where = payload.get("where") or {}
    orig_ids = payload.get("orig_ids") or []
    _ensure_filters_present("mark", label, where, orig_ids)

    match, params = _build_match(label, where, orig_ids)
    ts = int(time.time())
    cypher = f"""
        {match}
        WITH n
        SET n.archived = true, n.archived_at = $ts
        RETURN count(n) AS affected
    """
    params["ts"] = ts
    rows = db.query(cypher, params)
    affected = int(rows[0]["affected"]) if rows else 0
    return {"ok": True, "action": "mark", "affected": affected, "timestamp": ts}


def _act_restore(db: MemgraphAdapter, payload: dict[str, Any]) -> dict[str, Any]:
    label = payload.get("label")
    where = payload.get("where") or {}
    orig_ids = payload.get("orig_ids") or []
    _ensure_filters_present("restore", label, where, orig_ids)

    match, params = _build_match(label, where, orig_ids)
    cypher = f"""
        {match}
        WITH n
        SET n.archived = false
        REMOVE n.archived_at
        RETURN count(n) AS affected
    """
    rows = db.query(cypher, params)
    affected = int(rows[0]["affected"]) if rows else 0
    return {"ok": True, "action": "restore", "affected": affected}


def _act_purge(db: MemgraphAdapter, payload: dict[str, Any]) -> dict[str, Any]:
    label = payload.get("label")
    where = payload.get("where") or {}
    orig_ids = payload.get("orig_ids") or []
    only_archived = payload.get("only_archived", True)
    older_than_days = payload.get("older_than_days")

    match, params = _build_match(label, where, orig_ids)
    extra_conds: list[str] = []
    if only_archived:
        extra_conds.append("coalesce(n.archived, false) = true")
    if older_than_days is not None:
        try:
            days = int(older_than_days)
            cutoff = int(time.time()) - days * 86400
            extra_conds.append("coalesce(n.archived_at, 0) <= $cutoff")
            params["cutoff"] = cutoff
        except Exception:
            pass

    where_tail = ""
    if extra_conds:
        if " WHERE " in match:
            where_tail = " AND " + " AND ".join(extra_conds)
        else:
            where_tail = " WHERE " + " AND ".join(extra_conds)

    # Rebuild match with extra conditions appended
    full_match = match + where_tail

    # Count size(ns) first, then delete and return the count
    cypher = f"""
        {full_match}
        WITH collect(n) AS ns, size(collect(n)) AS c
        UNWIND ns AS x
        DETACH DELETE x
        RETURN c AS deleted
    """
    rows = db.query(cypher, params)
    deleted = int(rows[0]["deleted"]) if rows else 0
    return {"ok": True, "action": "purge", "deleted": deleted}


def _act_status(db: MemgraphAdapter, payload: dict[str, Any]) -> dict[str, Any]:
    label = payload.get("label")

    # Overall archived count
    params: dict[str, Any] = {}
    cond = "WHERE coalesce(n.archived, false) = true"
    if label:
        cond += " AND $label IN labels(n)"
        params["label"] = str(label)

    total_rows = db.query(f"MATCH (n) {cond} RETURN count(n) AS archived", params)
    total_archived = int(total_rows[0]["archived"]) if total_rows else 0

    # Archived by label
    by_label_rows = db.query(
        f"""
        MATCH (n) {cond}
        UNWIND labels(n) AS lbl
        RETURN lbl AS label, count(*) AS count
        ORDER BY count DESC
        """,
        params,
    )
    by_label = [{"label": r["label"], "count": int(r["count"])} for r in by_label_rows]

    return {
        "ok": True,
        "action": "status",
        "archived_total": total_archived,
        "by_label": by_label,
        "filter_label": label or None,
    }


def _act_list(db: MemgraphAdapter, payload: dict[str, Any]) -> dict[str, Any]:
    label = payload.get("label")
    where = payload.get("where") or {}
    limit = int(payload.get("limit") or 50)

    match, params = _build_match(label, where, None)
    cond = "coalesce(n.archived, false) = true"
    match = match + " AND " + cond if " WHERE " in match else match + " WHERE " + cond

    cypher = f"""
        {match}
        RETURN labels(n) AS labels, n.orig_id AS orig_id, n.archived AS archived, n.archived_at AS archived_at
        LIMIT $limit
    """
    params["limit"] = limit
    rows = db.query(cypher, params)
    items = [
        {
            "labels": r.get("labels") or [],
            "orig_id": r.get("orig_id"),
            "archived": bool(r.get("archived", False)),
            "archived_at": r.get("archived_at"),
        }
        for r in rows
    ]
    return {"ok": True, "action": "list", "count": len(items), "items": items, "limit": limit}


# ─────────────────────────────────────────────────────────────────────────────
# Public entrypoint
# ─────────────────────────────────────────────────────────────────────────────
@mcp_tool(tool_name="data.archive", required_scope="tools:write")
def invoke(ctx: ToolContext, payload: dict[str, Any] | None = None, **kwargs) -> dict[str, Any]:
    """
    Entry point for the data.archive tool. See module docstring for payload formats.
    """
    payload = payload or {}
    action = str(payload.get("action") or "").strip().lower()
    if action not in {"mark", "restore", "purge", "status", "list"}:
        raise ValueError("action must be one of: mark, restore, purge, status, list")

    db = MemgraphAdapter()

    # Dispatch
    if action == "mark":
        result = _act_mark(db, payload)
    elif action == "restore":
        result = _act_restore(db, payload)
    elif action == "purge":
        result = _act_purge(db, payload)
    elif action == "status":
        result = _act_status(db, payload)
    else:  # list
        result = _act_list(db, payload)

    return result
