"""
MCP Tool: data.quality

Lightweight data quality checks for the Memgraph graph.

Supported actions
-----------------
- stats
    → Global counts; counts by label and relationship type.
    Payload: {}
    Returns: { nodes, relationships, by_label[], by_relationship[] }

- missing_props
    → For a given label and list of required properties, report how many nodes
      are missing each property (and optionally sample a few orig_ids).
    Payload: { "label":"User", "properties":["user_id","email"], "sample":5 }
    Returns: { label, results: [ {property, missing, sample_orig_ids[]} ] }

- degree
    → Degree distribution and summary statistics (optionally for a label).
    Payload: { "label":"User" }   # label optional
    Returns: { label, summary:{min,max,avg}, distribution:[{degree,count}] }

- dangling
    → Nodes with zero degree (isolates), optionally filtered by label.
    Payload: { "label":"File" }   # label optional
    Returns: { label, total, by_label[] }

- duplicates
    → Detect duplicate values for a property under a label.
    Payload: { "label":"User", "property":"user_id", "limit":100 }
    Returns: { label, property, duplicates:[{value,count}] }

- sample
    → Return a small sample of nodes (properties maps) by label.
    Payload: { "label":"User", "limit":10 }
    Returns: { label, count, items:[ {labels, properties} ] }

Notes
-----
- Requires the Memgraph adapter: src.adapters.db_memgraph.MemgraphAdapter
- Keeps queries simple & portable (no APOC).
"""

from __future__ import annotations

from contextlib import suppress
from typing import Any

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
    raise RuntimeError("Memgraph adapter is required for data.quality tool")


# ─────────────────────────────────────────────────────────────────────────────
# Action: stats
# ─────────────────────────────────────────────────────────────────────────────
def _act_stats(db: MemgraphAdapter) -> dict[str, Any]:
    # Global counts
    nodes = db.query("MATCH (n) RETURN count(n) AS c")
    rels = db.query("MATCH ()-[r]->() RETURN count(r) AS c")
    node_count = int(nodes[0]["c"] if nodes else 0)
    rel_count = int(rels[0]["c"] if rels else 0)

    # By label
    by_label_rows = db.query(
        """
        MATCH (n)
        UNWIND labels(n) AS lbl
        RETURN lbl AS label, count(*) AS count
        ORDER BY count DESC
        """
    )
    by_label = [{"label": r["label"], "count": int(r["count"])} for r in by_label_rows]

    # By relationship type
    by_rel_rows = db.query(
        """
        MATCH ()-[r]->()
        RETURN type(r) AS type, count(*) AS count
        ORDER BY count DESC
        """
    )
    by_rel = [{"type": r["type"], "count": int(r["count"])} for r in by_rel_rows]

    return {
        "ok": True,
        "action": "stats",
        "nodes": node_count,
        "relationships": rel_count,
        "by_label": by_label,
        "by_relationship": by_rel,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Action: missing_props
# ─────────────────────────────────────────────────────────────────────────────
def _act_missing_props(db: MemgraphAdapter, payload: dict[str, Any]) -> dict[str, Any]:
    label = payload.get("label")
    props = payload.get("properties") or []
    sample = int(payload.get("sample") or 0)

    if not label or not isinstance(props, list) or not props:
        raise ValueError("missing_props requires 'label' and a non-empty 'properties' list")

    out: list[dict[str, Any]] = []
    for p in props:
        # Count nodes missing the property p
        q = f"MATCH (n:`{label}`) WHERE NOT exists(n.`{p}`) RETURN count(n) AS c"
        rows = db.query(q)
        missing = int(rows[0]["c"] if rows else 0)

        entry: dict[str, Any] = {"property": p, "missing": missing}

        if sample > 0 and missing > 0:
            qs = f"MATCH (n:`{label}`) WHERE NOT exists(n.`{p}`) " "RETURN n.orig_id AS orig_id LIMIT $limit"
            srows = db.query(qs, {"limit": sample})
            entry["sample_orig_ids"] = [r.get("orig_id") for r in srows if r.get("orig_id") is not None]

        out.append(entry)

    return {"ok": True, "action": "missing_props", "label": label, "results": out}


# ─────────────────────────────────────────────────────────────────────────────
# Action: degree
# ─────────────────────────────────────────────────────────────────────────────
def _act_degree(db: MemgraphAdapter, payload: dict[str, Any]) -> dict[str, Any]:
    label = payload.get("label")

    lbl = f":`{label}`" if label else ""
    # Distribution
    dist_rows = db.query(
        f"""
        MATCH (n{lbl})
        WITH size((n)--()) AS deg
        RETURN deg AS degree, count(*) AS count
        ORDER BY degree ASC
        """
    )
    distribution = [{"degree": int(r["degree"]), "count": int(r["count"])} for r in dist_rows]

    # Summary stats
    sum_rows = db.query(
        f"""
        MATCH (n{lbl})
        WITH size((n)--()) AS d
        RETURN min(d) AS min, max(d) AS max, avg(d) AS avg
        """
    )
    if sum_rows:
        summary = {
            "min": int(sum_rows[0]["min"] or 0),
            "max": int(sum_rows[0]["max"] or 0),
            "avg": float(sum_rows[0]["avg"] or 0.0),
        }
    else:
        summary = {"min": 0, "max": 0, "avg": 0.0}

    return {"ok": True, "action": "degree", "label": label, "summary": summary, "distribution": distribution}


# ─────────────────────────────────────────────────────────────────────────────
# Action: dangling
# ─────────────────────────────────────────────────────────────────────────────
def _act_dangling(db: MemgraphAdapter, payload: dict[str, Any]) -> dict[str, Any]:
    label = payload.get("label")

    lbl_cond = ""
    params: dict[str, Any] = {}
    if label:
        lbl_cond = "AND $lbl IN labels(n)"
        params["lbl"] = str(label)

    total_rows = db.query(
        f"""
        MATCH (n)
        WHERE size((n)--()) = 0 {lbl_cond}
        RETURN count(n) AS c
        """,
        params,
    )
    total = int(total_rows[0]["c"] if total_rows else 0)

    by_label_rows = db.query(
        f"""
        MATCH (n)
        WHERE size((n)--()) = 0 {lbl_cond}
        UNWIND labels(n) AS lbl
        RETURN lbl AS label, count(*) AS count
        ORDER BY count DESC
        """,
        params,
    )
    by_label = [{"label": r["label"], "count": int(r["count"])} for r in by_label_rows]

    return {"ok": True, "action": "dangling", "label": label, "total": total, "by_label": by_label}


# ─────────────────────────────────────────────────────────────────────────────
# Action: duplicates
# ─────────────────────────────────────────────────────────────────────────────
def _act_duplicates(db: MemgraphAdapter, payload: dict[str, Any]) -> dict[str, Any]:
    label = payload.get("label")
    prop = payload.get("property")
    limit = int(payload.get("limit") or 100)

    if not label or not prop:
        raise ValueError("duplicates requires 'label' and 'property'")

    q = f"""
        MATCH (n:`{label}`)
        WITH n.`{prop}` AS k
        WHERE k IS NOT NULL
        WITH k, count(*) AS c
        WHERE c > 1
        RETURN k AS value, c AS count
        ORDER BY c DESC
        LIMIT $limit
    """
    rows = db.query(q, {"limit": limit})
    dups = [{"value": r.get("value"), "count": int(r.get("count") or 0)} for r in rows]

    return {"ok": True, "action": "duplicates", "label": label, "property": prop, "duplicates": dups}


# ─────────────────────────────────────────────────────────────────────────────
# Action: sample
# ─────────────────────────────────────────────────────────────────────────────
def _act_sample(db: MemgraphAdapter, payload: dict[str, Any]) -> dict[str, Any]:
    label = payload.get("label")
    limit = int(payload.get("limit") or 10)
    if not label:
        raise ValueError("sample requires 'label'")

    rows = db.query(
        f"""
        MATCH (n:`{label}`)
        RETURN labels(n) AS labels, properties(n) AS props
        LIMIT $limit
        """,
        {"limit": limit},
    )
    items = [{"labels": r.get("labels") or [], "properties": r.get("props") or {}} for r in rows]
    return {"ok": True, "action": "sample", "label": label, "count": len(items), "items": items, "limit": limit}


# ─────────────────────────────────────────────────────────────────────────────
# Public entrypoint
# ─────────────────────────────────────────────────────────────────────────────
@mcp_tool(tool_name="data.quality", required_scope="tools:read")
def invoke(ctx: ToolContext, payload: dict[str, Any] | None = None, **kwargs) -> dict[str, Any]:
    """
    Entry point for the data.quality tool. See module docstring for payload formats.
    """
    payload = payload or {}
    action = str(payload.get("action") or "").strip().lower()
    if action not in {"stats", "missing_props", "degree", "dangling", "duplicates", "sample"}:
        raise ValueError("action must be one of: stats, missing_props, degree, dangling, duplicates, sample")

    db = MemgraphAdapter()

    if action == "stats":
        result = _act_stats(db)
    elif action == "missing_props":
        result = _act_missing_props(db, payload)
    elif action == "degree":
        result = _act_degree(db, payload)
    elif action == "dangling":
        result = _act_dangling(db, payload)
    elif action == "duplicates":
        result = _act_duplicates(db, payload)
    else:  # sample
        result = _act_sample(db, payload)

    return result
