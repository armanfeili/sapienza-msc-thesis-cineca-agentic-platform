"""
MCP Tool: viz.render

Render helpers for MCP viz tools with input validation and size caps.

This module provides small, dependency-free utilities to turn Python data
structures into textual visualizations you can embed in Markdown docs,
Grafana panels, or return from MCP tools:

- Graph → Mermaid `flowchart` or Graphviz DOT (with validation and escaping)
- Table → Markdown table
- Series → Unicode sparkline

Supported actions
-----------------
- graph_mermaid
    Render graph to Mermaid flowchart syntax.
    Payload:
      {
        "nodes": [...],          # list of str or dict with "id"
        "edges": [...],          # list of (from, label, to) tuples or dict
        "direction": "LR",       # "LR"|"TB"|"BT"|"RL"
        "show_labels": true,     # show edge labels
        "max_nodes": 100,        # max nodes (default 100)
        "max_edges": 200         # max edges (default 200)
      }
    Returns: { ok, action:"graph_mermaid", content, nodes, edges }

- graph_dot
    Render graph to Graphviz DOT syntax.
    Payload:
      {
        "nodes": [...],
        "edges": [...],
        "directed": true,
        "max_nodes": 100,
        "max_edges": 200
      }
    Returns: { ok, action:"graph_dot", content, nodes, edges }

- table_markdown
    Render rows to Markdown table.
    Payload:
      {
        "rows": [{...}, ...],
        "columns": ["col1", "col2"],  # optional
        "max_rows": 1000                # max rows (default 1000)
      }
    Returns: { ok, action:"table_markdown", content, rows }

- sparkline
    Render numeric series as Unicode sparkline.
    Payload:
      {
        "values": [1, 3, 2, 5, 4],
        "max_values": 100              # max values (default 100)
      }
    Returns: { ok, action:"sparkline", content, values }

Notes
-----
- All inputs are validated and escaped to prevent injection attacks.
- Size caps prevent resource exhaustion.
- Deterministic rendering ensures same input → same output.
"""

from __future__ import annotations

import html
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from contextlib import suppress
from typing import Any

# ── Logging (structlog-aware if configured) ───────────────────────────────────
with suppress(Exception):
    from src.logging_setup import get_logger  # type: ignore

    logger = get_logger(__name__)  # type: ignore[assignment]
if "logger" not in globals():
    import logging

    logger = logging.getLogger(__name__)

# ── MCP decorator (best-effort) ────────────────────────────────────────────────
with suppress(Exception):
    from src.mcp.core.decorators import mcp_tool  # type: ignore
if "mcp_tool" not in globals():

    def mcp_tool(**_deco_kwargs: Any):  # type: ignore[misc]
        def _identity(fn):  # type: ignore[no-untyped-def]
            return fn

        return _identity


# ── ToolContext (best-effort) ──────────────────────────────────────────────────
with suppress(Exception):
    from src.mcp.core.context import ToolContext  # type: ignore
if "ToolContext" not in globals():

    class ToolContext:  # type: ignore[no-redef]
        def __init__(self, **kw: Any) -> None:
            pass


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers (with validation and escaping)
# ──────────────────────────────────────────────────────────────────────────────
def _sanitize_id(s: Any) -> str:
    """Make an ID safe for Mermaid/DOT (letters, digits, underscore). Prevents injection."""
    if not isinstance(s, str):
        s = str(s)
    # Remove all non-alphanumeric/underscore characters
    x = re.sub(r"[^\w]", "_", s.strip())
    # Ensure doesn't start with digit
    if re.match(r"^\d", x):
        x = "_" + x
    # Limit length to prevent DoS
    return (x or "_")[:100]


def _escape_label(s: Any) -> str:
    """Escape labels for safe embedding in Mermaid/DOT. Prevents injection attacks."""
    t = "" if s is None else str(s)
    # HTML escape to prevent XSS-like attacks in renderers
    t = html.escape(t, quote=True)
    # Escape quotes and newlines for syntax safety
    t = t.replace('"', r"\"").replace("\n", r"\n")
    # Limit length
    return t[:200]


def _normalize_nodes(nodes: Iterable[str | Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    """
    Accepts:
      - ["A", "B"]  → [{"id":"A"}, {"id":"B"}]
      - [{"id":"A","label":"Alpha"}, ...] → as-is (shallow-copied)
      - None → []

    Validates node structure and limits.
    """
    out: list[dict[str, Any]] = []
    if not nodes:
        return out
    for n in nodes:
        if isinstance(n, Mapping):
            nid = n.get("id")
            if nid is None:
                # try fallbacks
                nid = n.get("name") or n.get("label")
            if nid is None:
                raise ValueError("Each node must have an 'id', 'name', or 'label' field")
            out.append({"id": nid, "label": n.get("label", nid), **dict(n)})
        else:
            if not n:
                raise ValueError("Node ID cannot be empty")
            out.append({"id": n, "label": n})
    return out


def _normalize_edges(edges: Iterable[tuple[Any, Any, Any] | Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    """
    Accepts:
      - [("A","REL","B"), ...] → [{"from":"A","label":"REL","to":"B"}]
      - [{"from":"A","to":"B","label":"REL"}, ...] → as-is (shallow-copied)
      - None → []

    Validates edge structure.
    """
    out: list[dict[str, Any]] = []
    if not edges:
        return out
    for e in edges:
        if isinstance(e, Mapping):
            if "from" not in e or "to" not in e:
                raise ValueError("Each edge dict must have 'from' and 'to' fields")
            out.append({"from": e.get("from"), "to": e.get("to"), "label": e.get("label"), **dict(e)})
        else:
            if not isinstance(e, (list, tuple)) or len(e) != 3:
                raise ValueError("Each edge tuple must be (from, label, to)")
            a, rel, b = e  # type: ignore[misc]
            out.append({"from": a, "to": b, "label": rel})
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Graph renderers (now as actions)
# ──────────────────────────────────────────────────────────────────────────────
def _act_graph_mermaid(payload: dict[str, Any], ctx: ToolContext | None = None) -> dict[str, Any]:
    """
    Render a graph to Mermaid flowchart syntax with validation and size caps.
    """
    nodes = payload.get("nodes")
    edges = payload.get("edges")
    direction = str(payload.get("direction") or "LR")
    show_labels = bool(payload.get("show_labels", True))
    max_nodes = int(payload.get("max_nodes", 100))
    max_edges = int(payload.get("max_edges", 200))

    # Validate direction
    if direction not in {"LR", "TB", "BT", "RL"}:
        raise ValueError("direction must be one of: LR, TB, BT, RL")

    ns = _normalize_nodes(nodes)
    es = _normalize_edges(edges)

    # Apply size caps
    if len(ns) > max_nodes:
        raise ValueError(f"Too many nodes ({len(ns)}), max is {max_nodes}")
    if len(es) > max_edges:
        raise ValueError(f"Too many edges ({len(es)}), max is {max_edges}")

    lines: list[str] = [f"flowchart {direction}"]
    for n in ns:
        nid = _sanitize_id(n.get("id"))
        text = _escape_label(n.get("label", n.get("id", nid)))
        lines.append(f'  {nid}["{text}"]')

    for e in es:
        a = _sanitize_id(e.get("from", ""))
        b = _sanitize_id(e.get("to", ""))
        lbl = _escape_label(e.get("label", "")) if show_labels and e.get("label") else ""
        if lbl:
            lines.append(f'  {a} -->|"{lbl}"| {b}')
        else:
            lines.append(f"  {a} --> {b}")

    content = "\n".join(lines)
    return {
        "ok": True,
        "action": "graph_mermaid",
        "content": content,
        "nodes": len(ns),
        "edges": len(es),
    }


def _act_graph_dot(payload: dict[str, Any], ctx: ToolContext | None = None) -> dict[str, Any]:
    """
    Render a graph to Graphviz DOT syntax with validation and size caps.
    """
    nodes = payload.get("nodes")
    edges = payload.get("edges")
    directed = bool(payload.get("directed", True))
    max_nodes = int(payload.get("max_nodes", 100))
    max_edges = int(payload.get("max_edges", 200))

    ns = _normalize_nodes(nodes)
    es = _normalize_edges(edges)

    # Apply size caps
    if len(ns) > max_nodes:
        raise ValueError(f"Too many nodes ({len(ns)}), max is {max_nodes}")
    if len(es) > max_edges:
        raise ValueError(f"Too many edges ({len(es)}), max is {max_edges}")

    gtype = "digraph" if directed else "graph"
    arrow = "->" if directed else "--"

    lines: list[str] = [f"{gtype} G {{", '  graph [rankdir="LR"];', "  node [shape=box];"]
    for n in ns:
        nid = _sanitize_id(n.get("id"))
        text = _escape_label(n.get("label", n.get("id", nid)))
        lines.append(f'  {nid} [label="{text}"];')
    for e in es:
        a = _sanitize_id(e.get("from", ""))
        b = _sanitize_id(e.get("to", ""))
        lbl = _escape_label(e.get("label", "")) if e.get("label") else ""
        if lbl:
            lines.append(f'  {a} {arrow} {b} [label="{lbl}"];')
        else:
            lines.append(f"  {a} {arrow} {b};")
    lines.append("}")

    content = "\n".join(lines)
    return {
        "ok": True,
        "action": "graph_dot",
        "content": content,
        "nodes": len(ns),
        "edges": len(es),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Table renderer
# ──────────────────────────────────────────────────────────────────────────────
def _act_table_markdown(payload: dict[str, Any], ctx: ToolContext | None = None) -> dict[str, Any]:
    """
    Render dictionaries to a Markdown table with row limit.
    """
    rows = payload.get("rows", [])
    columns = payload.get("columns")
    max_rows = int(payload.get("max_rows", 1000))

    if not isinstance(rows, (list, tuple)):
        raise ValueError("rows must be a list")

    rows = list(rows or [])
    if len(rows) > max_rows:
        raise ValueError(f"Too many rows ({len(rows)}), max is {max_rows}")

    if not rows:
        content = "| (no data) |\n| --- |"
        return {
            "ok": True,
            "action": "table_markdown",
            "content": content,
            "rows": 0,
        }

    if columns is None:
        # Infer columns from union of keys, deterministic order (alphabetic)
        keys_set = set()
        for r in rows:
            if isinstance(r, Mapping):
                keys_set.update(r.keys())
        columns = sorted(str(k) for k in keys_set)

    def cell(v: Any) -> str:
        if v is None:
            return ""
        s = str(v)
        # Escape pipes and newlines, limit length
        s = s.replace("|", r"\|").replace("\n", "<br>")
        return s[:200]  # Cap cell length

    header = "| " + " | ".join(str(c) for c in columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    body = "\n".join(
        "| " + " | ".join(cell(r.get(c) if isinstance(r, Mapping) else "") for c in columns) + " |" for r in rows
    )
    content = "\n".join([header, sep, body])

    return {
        "ok": True,
        "action": "table_markdown",
        "content": content,
        "rows": len(rows),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Sparkline
# ──────────────────────────────────────────────────────────────────────────────
_BARS = "▁▂▃▄▅▆▇█"


def _act_sparkline(payload: dict[str, Any], ctx: ToolContext | None = None) -> dict[str, Any]:
    """
    Render a compact Unicode sparkline for a list of numbers.
    """
    values = payload.get("values", [])
    max_values = int(payload.get("max_values", 100))

    if not isinstance(values, (list, tuple)):
        raise ValueError("values must be a list")

    vals = [float(v) for v in values if v is not None]
    if len(vals) > max_values:
        raise ValueError(f"Too many values ({len(vals)}), max is {max_values}")

    if not vals:
        content = ""
    else:
        lo, hi = min(vals), max(vals)
        if math.isclose(hi, lo):
            content = _BARS[-1] * len(vals)
        else:
            out = []
            for v in vals:
                idx = int((v - lo) / (hi - lo) * (len(_BARS) - 1))
                out.append(_BARS[idx])
            content = "".join(out)

    return {
        "ok": True,
        "action": "sparkline",
        "content": content,
        "values": len(vals),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Convenience: build graph from triples or path-like data
# ──────────────────────────────────────────────────────────────────────────────
def graph_from_triples(
    triples: Iterable[tuple[Any, Any, Any]],
    *,
    node_labels: Mapping[Any, str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Build (nodes, edges) from (a, rel, b) triples.
    `node_labels` can map node-id → display label.
    """
    node_labels = node_labels or {}
    nodes_map: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    for a, rel, b in triples:
        aid, bid = str(a), str(b)
        if aid not in nodes_map:
            nodes_map[aid] = {"id": aid, "label": node_labels.get(a, aid)}
        if bid not in nodes_map:
            nodes_map[bid] = {"id": bid, "label": node_labels.get(b, bid)}
        edges.append({"from": aid, "to": bid, "label": rel})

    return list(nodes_map.values()), edges


# ──────────────────────────────────────────────────────────────────────────────
# Public entrypoint
# ──────────────────────────────────────────────────────────────────────────────
@mcp_tool(tool_name="viz.render", required_scope="viz:render")
def invoke(payload: dict[str, Any] | None = None, **kwargs) -> dict[str, Any]:
    """
    Entry for viz.render tool. See module docstring for supported actions.
    """
    payload = payload or {}
    ctx = kwargs.get("ctx") or ToolContext()
    action = str(payload.get("action") or "graph_mermaid").strip().lower()

    if action not in {"graph_mermaid", "graph_dot", "table_markdown", "sparkline"}:
        raise ValueError("action must be one of: graph_mermaid, graph_dot, table_markdown, sparkline")

    if action == "graph_mermaid":
        return _act_graph_mermaid(payload, ctx)
    elif action == "graph_dot":
        return _act_graph_dot(payload, ctx)
    elif action == "table_markdown":
        return _act_table_markdown(payload, ctx)
    else:
        return _act_sparkline(payload, ctx)


# Back-compat aliases
run = invoke
handle = invoke


# Legacy function aliases for backward compatibility
def render_graph_mermaid(
    nodes: Iterable[str | Mapping[str, Any]] | None = None,
    edges: Iterable[tuple[Any, Any, Any] | Mapping[str, Any]] | None = None,
    *,
    direction: str = "LR",
    show_labels: bool = True,
) -> str:
    """Legacy wrapper for graph_mermaid action."""
    result = _act_graph_mermaid(
        {
            "nodes": nodes,
            "edges": edges,
            "direction": direction,
            "show_labels": show_labels,
        }
    )
    return result["content"]


def render_graph_dot(
    nodes: Iterable[str | Mapping[str, Any]] | None = None,
    edges: Iterable[tuple[Any, Any, Any] | Mapping[str, Any]] | None = None,
    *,
    directed: bool = True,
) -> str:
    """Legacy wrapper for graph_dot action."""
    result = _act_graph_dot(
        {
            "nodes": nodes,
            "edges": edges,
            "directed": directed,
        }
    )
    return result["content"]


def render_table_markdown(
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[str] | None = None,
) -> str:
    """Legacy wrapper for table_markdown action."""
    result = _act_table_markdown(
        {
            "rows": rows,
            "columns": columns,
        }
    )
    return result["content"]


def sparkline(values: Iterable[int | float]) -> str:
    """Legacy wrapper for sparkline action."""
    result = _act_sparkline({"values": values})
    return result["content"]


# ──────────────────────────────────────────────────────────────────────────────
# __all__
# ──────────────────────────────────────────────────────────────────────────────
__all__ = [
    "_act_graph_dot",
    # Internal actions (useful for tests)
    "_act_graph_mermaid",
    "_act_sparkline",
    "_act_table_markdown",
    "graph_from_triples",
    "handle",
    "invoke",
    "render_graph_dot",
    # Legacy function names for backward compatibility
    "render_graph_mermaid",
    "render_table_markdown",
    "run",
    "sparkline",
]


# ──────────────────────────────────────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":  # pragma: no cover
    demo_nodes = ["User", "Institution"]
    demo_edges = [("User", "WORKS_AT", "Institution")]

    print("# Mermaid")
    print(render_graph_mermaid(demo_nodes, demo_edges, direction="LR"))
    print()
    print("# DOT")
    print(render_graph_dot(demo_nodes, demo_edges))
    print()
    print("# Table")
    print(render_table_markdown([{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]))
    print()
    print("# Sparkline")
    print(sparkline([1, 3, 2, 5, 4]))
