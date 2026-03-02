"""
MCP Tools: viz

Lightweight renderers to turn data structures into textual visualizations:
- Graph → Mermaid or DOT text
- Table → Markdown table
- Sparkline → Unicode inline chart

Actions:
- render_graph  (graph -> mermaid|dot)
- render_table  (rows -> markdown)
- sparkline     (numbers -> unicode sparkline)
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Sequence
from contextlib import suppress
from typing import Any, Dict, List, Optional, Tuple

# ── Logging (optional import) ─────────────────────────────────────────────────
with suppress(Exception):
    from src.logging_setup import get_logger  # type: ignore

    logger = get_logger(__name__)  # type: ignore[assignment]
if "logger" not in globals():
    import logging

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)


# ── Utilities ─────────────────────────────────────────────────────────────────
def _sanitize_id(s: str) -> str:
    """Make an ID safe for Mermaid/DOT (letters, digits, underscore)."""
    if not isinstance(s, str):
        s = str(s)
    x = re.sub(r"\W+", "_", s.strip())
    if re.match(r"^\d", x):
        x = "_" + x
    return x or "_"


def _escape_label(s: Any) -> str:
    t = str(s if s is not None else "")
    return t.replace('"', r"\"").replace("\n", r"\n")


# ── Graph renderers ───────────────────────────────────────────────────────────
def _to_mermaid(
    graph: dict[str, Any],
    direction: str = "LR",
    show_labels: bool = True,
) -> str:
    """
    Render a small graph to Mermaid flowchart syntax.

    Expected graph shape:
    {
      "nodes": [{"id":"n1","label":"Node 1"}, ...],
      "edges": [{"from":"n1","to":"n2","label":"REL"}, ...]
    }
    """
    nodes: list[dict[str, Any]] = list(graph.get("nodes") or [])
    edges: list[dict[str, Any]] = list(graph.get("edges") or [])

    # Mermaid header
    lines: list[str] = [f"flowchart {direction}"]

    # Nodes
    for n in nodes:
        nid = _sanitize_id(n.get("id", ""))
        text = _escape_label(n.get("label", n.get("id", nid)))
        # Simple rectangle shape
        lines.append(f'  {nid}["{text}"]')

    # Edges
    for e in edges:
        a = _sanitize_id(e.get("from", ""))
        b = _sanitize_id(e.get("to", ""))
        lbl = _escape_label(e.get("label", "")) if show_labels and e.get("label") else ""
        if lbl:
            lines.append(f'  {a} -->|"{lbl}"| {b}')
        else:
            lines.append(f"  {a} --> {b}")

    return "\n".join(lines)


def _to_dot(graph: dict[str, Any], directed: bool = True) -> str:
    """
    Render a small graph to Graphviz DOT.

    Expected graph shape identical to _to_mermaid.
    """
    nodes: list[dict[str, Any]] = list(graph.get("nodes") or [])
    edges: list[dict[str, Any]] = list(graph.get("edges") or [])

    gtype = "digraph" if directed else "graph"
    arrow = "->" if directed else "--"

    lines: list[str] = [f"{gtype} G {{", '  graph [rankdir="LR"];', "  node [shape=box];"]

    # Nodes
    for n in nodes:
        nid = _sanitize_id(n.get("id", ""))
        text = _escape_label(n.get("label", n.get("id", nid)))
        lines.append(f'  {nid} [label="{text}"];')

    # Edges
    for e in edges:
        a = _sanitize_id(e.get("from", ""))
        b = _sanitize_id(e.get("to", ""))
        lbl = _escape_label(e.get("label", "")) if e.get("label") else ""
        if lbl:
            lines.append(f'  {a} {arrow} {b} [label="{lbl}"];')
        else:
            lines.append(f"  {a} {arrow} {b};")

    lines.append("}")
    return "\n".join(lines)


# ── Table renderer ────────────────────────────────────────────────────────────
def _markdown_table(rows: Sequence[dict[str, Any]], columns: Sequence[str] | None = None) -> str:
    rows = list(rows or [])
    if not rows:
        return "| (no data) |\n| --- |"

    if columns is None:
        # Preserve first row's key order, then union remaining keys
        keys: list[str] = list(rows[0].keys())
        seen = set(keys)
        for r in rows[1:]:
            for k in r:
                if k not in seen:
                    seen.add(k)
                    keys.append(k)
        columns = keys

    def cell(v: Any) -> str:
        if v is None:
            return ""
        s = str(v)
        # escape pipes and newlines for Markdown
        s = s.replace("|", r"\|").replace("\n", "<br>")
        return s

    header = "| " + " | ".join(str(c) for c in columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    body = "\n".join("| " + " | ".join(cell(r.get(c)) for c in columns) + " |" for r in rows)
    return "\n".join([header, sep, body])


# ── Sparkline ─────────────────────────────────────────────────────────────────
_BARS = "▁▂▃▄▅▆▇█"


def _sparkline(values: Iterable[float]) -> str:
    vals = [v for v in values if v is not None]
    if not vals:
        return ""
    lo, hi = min(vals), max(vals)
    if math.isclose(hi, lo):
        return _BARS[-1] * len(vals)
    out = []
    for v in vals:
        idx = int((v - lo) / (hi - lo) * (len(_BARS) - 1))
        out.append(_BARS[idx])
    return "".join(out)


# ── Public MCP entrypoints ────────────────────────────────────────────────────
def invoke(payload: dict[str, Any] | None = None, **kwargs) -> dict[str, Any]:
    """
    Execute a viz action.

    Payload fields:
      - action: "render_graph" | "render_table" | "sparkline"
      - format: for render_graph: "mermaid" | "dot"
                for render_table: "markdown" (default)
      - graph:  {nodes:[{id,label?}], edges:[{from,to,label?}]}
      - rows:   list[dict] (for render_table)
      - columns:list[str]  (optional, for render_table)
      - values: list[number] (for sparkline)
      - direction: "LR"|"TB" etc (optional, mermaid)
    """
    payload = {**(payload or {}), **kwargs}
    action = str(payload.get("action", "render_graph")).lower()

    try:
        if action == "render_graph":
            graph = payload.get("graph") or {}
            fmt = str(payload.get("format", "mermaid")).lower()
            direction = str(payload.get("direction", "LR")).upper()
            if fmt == "mermaid":
                content = _to_mermaid(graph, direction=direction)
                return {"ok": True, "data": {"content_type": "text/mermaid", "content": content}}
            if fmt == "dot":
                content = _to_dot(graph, directed=True)
                return {"ok": True, "data": {"content_type": "text/vnd.graphviz", "content": content}}
            return {"ok": False, "error": f"unsupported graph format '{fmt}'"}

        if action == "render_table":
            rows = payload.get("rows") or []
            columns = payload.get("columns")
            content = _markdown_table(rows, columns)
            return {"ok": True, "data": {"content_type": "text/markdown", "content": content}}

        if action == "sparkline":
            values = payload.get("values") or []
            try:
                nums = [float(v) for v in values]
            except Exception:
                return {"ok": False, "error": "`values` must be a list of numbers"}
            content = _sparkline(nums)
            return {"ok": True, "data": {"content_type": "text/plain", "content": content}}

        return {"ok": False, "error": f"unsupported action '{action}'"}
    except Exception as e:  # pragma: no cover
        logger.exception("viz error: %s", e)
        return {"ok": False, "error": str(e)}


def describe() -> dict[str, Any]:
    """
    Static metadata + JSON Schemas for MCP discovery.
    """
    return {
        "name": "viz",
        "summary": "Render lightweight visualizations (Mermaid/DOT graphs, Markdown tables, sparklines).",
        "tools": [
            {
                "name": "viz.render_graph",
                "summary": "Render a graph to Mermaid or DOT.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "action": {"const": "render_graph"},
                        "format": {"type": "string", "enum": ["mermaid", "dot"], "default": "mermaid"},
                        "direction": {"type": "string", "default": "LR"},
                        "graph": {
                            "type": "object",
                            "properties": {
                                "nodes": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {"id": {"type": "string"}, "label": {"type": "string"}},
                                        "required": ["id"],
                                        "additionalProperties": True,
                                    },
                                    "default": [],
                                },
                                "edges": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "from": {"type": "string"},
                                            "to": {"type": "string"},
                                            "label": {"type": "string"},
                                        },
                                        "required": ["from", "to"],
                                        "additionalProperties": True,
                                    },
                                    "default": [],
                                },
                            },
                            "required": ["nodes", "edges"],
                            "additionalProperties": True,
                        },
                    },
                    "required": ["graph"],
                    "additionalProperties": True,
                },
            },
            {
                "name": "viz.render_table",
                "summary": "Render a list of objects to a Markdown table.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "action": {"const": "render_table"},
                        "rows": {"type": "array", "items": {"type": "object"}, "default": []},
                        "columns": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["rows"],
                    "additionalProperties": True,
                },
            },
            {
                "name": "viz.sparkline",
                "summary": "Render a compact unicode sparkline for numeric series.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "action": {"const": "sparkline"},
                        "values": {"type": "array", "items": {"type": "number"}, "default": []},
                    },
                    "required": ["values"],
                    "additionalProperties": False,
                },
            },
        ],
        "examples": [
            {
                "tool": "viz.render_graph",
                "input": {
                    "action": "render_graph",
                    "format": "mermaid",
                    "graph": {
                        "nodes": [{"id": "User", "label": "User"}, {"id": "Institution"}],
                        "edges": [{"from": "User", "to": "Institution", "label": "WORKS_AT"}],
                    },
                },
            },
            {
                "tool": "viz.render_table",
                "input": {
                    "action": "render_table",
                    "rows": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}],
                },
            },
            {"tool": "viz.sparkline", "input": {"action": "sparkline", "values": [1, 3, 2, 5, 4]}},
        ],
    }


__all__ = ["describe", "invoke"]
