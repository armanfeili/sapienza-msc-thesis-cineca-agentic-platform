"""
MCP Tool: output.format

Portable formatters for common result shapes:
- json      → JSON / NDJSON (deterministic column order)
- csv       → RFC4180-ish CSV (configurable delimiter/quote)
- markdown  → GitHub-style table with width caps
- text      → plain/text rows
- normalize → utility that returns {columns, rows} from arbitrary input

Input `data` may be:
- list[dict]                  → treated as tabular rows
- dict with "rows" (and optional "columns")
- dict (non-tabular)          → formatted as a single JSON object unless normalize=true
- string                      → returned as-is for text; JSON-encoded for json

All actions return a dict:
  { ok, action, format, content, columns?, rowcount?, bytes }

Options (payload fields)
------------------------
- action: "json" | "csv" | "markdown" | "text" | "normalize"
- data: any
- columns: list[str]           # column order; if omitted we infer union of keys (deterministic)
- limit: int                   # cap number of rows (default: no cap)
- flatten: bool                # flatten nested dicts into dot.notation (default: true)
- json:
    ndjson: bool               # one JSON object per line (data must be list-like)
    indent: int | null         # pretty print when not ndjson (default: null/compact)
    sort_keys: bool            # default: true (for deterministic output)
    ensure_ascii: bool         # default: false (unicode safe)
- csv:
    delimiter: string          # default: ","
    quotechar: string          # default: '"'
    header: bool               # default: true
    include_bom: bool          # default: false
- markdown:
    max_col_width: int         # truncate cells (…); 0/None = no truncate (default: 50)
    code_fence: bool           # wrap in ```md fence (default: false)
- text:
    separator: str             # join rows with sep (default: newline)
    key_value_sep: str         # for dict rows (default: ": ")
    code_fence: bool           # wrap in ```text (default: false)
- wrap: bool                   # alias for code_fence on markdown/text; ignored elsewhere
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Mapping, Sequence
from contextlib import suppress
from typing import Any

# ── Optional orjson for speed (fallback to stdlib) ────────────────────────────
_ORJSON_AVAILABLE = False
with suppress(Exception):
    import orjson as _orjson  # type: ignore

    _ORJSON_AVAILABLE = True

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


# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────
def _is_mapping(x: Any) -> bool:
    return isinstance(x, Mapping)


def _is_sequence(x: Any) -> bool:
    return isinstance(x, (list, tuple))


def flatten_dict(d: Mapping[str, Any], parent_key: str = "", sep: str = ".") -> dict[str, Any]:
    """
    Flatten nested mappings into 'a.b.c' keys. Lists are preserved as-is (JSON-serializable).
    """
    items: list[tuple[str, Any]] = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else str(k)
        if isinstance(v, Mapping):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def _infer_columns(rows: list[Mapping[str, Any]], explicit: Sequence[str] | None = None) -> list[str]:
    """
    Infer column order from rows. Deterministic: sorts alphabetically if not explicit.
    """
    if explicit:
        return [str(c) for c in explicit]
    if not rows:
        return []
    # Collect all unique keys
    seen = set()
    for r in rows:
        seen.update(r.keys())
    # Sort alphabetically for deterministic output
    return sorted(str(k) for k in seen)


def _apply_limit(rows: list[Mapping[str, Any]], limit: int | None) -> list[Mapping[str, Any]]:
    if limit is None or limit <= 0:
        return rows
    return rows[: int(limit)]


def _normalize(
    data: Any,
    *,
    columns: Sequence[str] | None = None,
    limit: int | None = None,
    flatten: bool = True,
) -> dict[str, Any]:
    """
    Return a normalized tabular view: {columns, rows}.
    Rules:
    - If `data` is {"rows":[...], "columns":[...]} use that (respect limit/flatten).
    - If `data` is list[dict], use as rows.
    - If `data` is dict and contains no "rows" → treat as single row [data].
    - Else → rows = [{"value": str(data)}], columns=["value"].
    """
    orig_rows: list[Mapping[str, Any]] = []
    cols: Sequence[str] | None = None

    if _is_mapping(data) and "rows" in data:
        maybe_rows = data.get("rows")
        if _is_sequence(maybe_rows):
            orig_rows = list(maybe_rows)  # type: ignore[arg-type]
            cols = data.get("columns") if isinstance(data.get("columns"), (list, tuple)) else None
        else:
            orig_rows = [data]  # type: ignore[list-item]
    elif _is_sequence(data):
        if data and all(_is_mapping(r) for r in data):
            orig_rows = list(data)  # type: ignore[assignment]
        else:
            # sequence of scalars -> wrap as {"value": ...}
            orig_rows = [{"value": v} for v in data]  # type: ignore[list-item]
    elif _is_mapping(data):
        orig_rows = [data]  # type: ignore[list-item]
    else:
        orig_rows = [{"value": data}]  # type: ignore[list-item]

    # Flatten if required
    if flatten:
        rows: list[dict[str, Any]] = [flatten_dict(r) if isinstance(r, Mapping) else {"value": r} for r in orig_rows]
    else:
        rows = [dict(r) if isinstance(r, Mapping) else {"value": r} for r in orig_rows]

    rows = _apply_limit(rows, limit)
    final_columns = _infer_columns(rows, explicit=columns or cols)
    return {"columns": final_columns, "rows": rows}


def _json_dumps(obj: Any, *, indent: int | None, sort_keys: bool, ensure_ascii: bool) -> str:
    """JSON serialization with unicode safety (ensure_ascii=False by default)."""
    if _ORJSON_AVAILABLE and indent is None and not ensure_ascii and sort_keys:
        # orjson doesn't support sort_keys, so only use when sort_keys=True is acceptable
        with suppress(Exception):
            # orjson always produces sorted output
            return _orjson.dumps(obj, option=_orjson.OPT_SORT_KEYS).decode("utf-8")  # type: ignore[attr-defined]
    return json.dumps(obj, indent=indent, sort_keys=bool(sort_keys), ensure_ascii=bool(ensure_ascii))


def _with_fence(content: str, lang: str) -> str:
    return f"```{lang}\n{content}\n```"


def _truncate(s: Any, width: int | None) -> str:
    txt = "" if s is None else str(s)
    if not width or width <= 0:
        return txt
    return txt if len(txt) <= width else (txt[: max(0, width - 1)] + "…")


def _md_escape(s: str) -> str:
    return s.replace("|", r"\|").replace("\n", r"<br>")


# ─────────────────────────────────────────────────────────────────────────────
# JSON
# ─────────────────────────────────────────────────────────────────────────────
def _act_json(payload: dict[str, Any], ctx: ToolContext | None = None) -> dict[str, Any]:
    """Format data as JSON or NDJSON (newline-delimited JSON)."""
    data = payload.get("data")
    ndjson = bool(payload.get("ndjson", False))
    indent = payload.get("indent")
    sort_keys = bool(payload.get("sort_keys", True))  # True for deterministic output
    ensure_ascii = bool(payload.get("ensure_ascii", False))  # False for unicode safety
    limit = payload.get("limit")
    flatten = bool(payload.get("flatten", True))

    if ndjson:
        norm = _normalize(data, limit=limit, flatten=flatten)
        lines = []
        for row in norm["rows"]:
            lines.append(_json_dumps(row, indent=None, sort_keys=sort_keys, ensure_ascii=ensure_ascii))
        content = "\n".join(lines)
    else:
        content = _json_dumps(
            data,
            indent=indent if indent is None or indent >= 0 else None,
            sort_keys=sort_keys,
            ensure_ascii=ensure_ascii,
        )

    return {
        "ok": True,
        "action": "json",
        "format": "application/json" if not ndjson else "application/x-ndjson",
        "content": content,
        "bytes": len(content.encode("utf-8")),
    }


# ─────────────────────────────────────────────────────────────────────────────
# CSV
# ─────────────────────────────────────────────────────────────────────────────
def _act_csv(payload: dict[str, Any], ctx: ToolContext | None = None) -> dict[str, Any]:
    """Format data as CSV with deterministic column order."""
    data = payload.get("data")
    delimiter = (payload.get("delimiter") or ",")[0]
    quotechar = (payload.get("quotechar") or '"')[0]
    include_header = payload.get("header", True)
    include_bom = bool(payload.get("include_bom", False))
    columns = payload.get("columns")
    limit = payload.get("limit")
    flatten = bool(payload.get("flatten", True))

    norm = _normalize(data, columns=columns, limit=limit, flatten=flatten)
    cols: list[str] = list(norm["columns"])

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=delimiter, quotechar=quotechar, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    if include_header and cols:
        writer.writerow(cols)
    for r in norm["rows"]:
        writer.writerow([r.get(c, "") for c in cols])

    content = buf.getvalue()
    if include_bom:
        content = "\ufeff" + content  # UTF-8 BOM

    return {
        "ok": True,
        "action": "csv",
        "format": "text/csv",
        "columns": cols,
        "rowcount": len(norm["rows"]),
        "content": content,
        "bytes": len(content.encode("utf-8")),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Markdown
# ─────────────────────────────────────────────────────────────────────────────
def _act_markdown(payload: dict[str, Any], ctx: ToolContext | None = None) -> dict[str, Any]:
    """Format data as Markdown table with width caps."""
    data = payload.get("data")
    columns = payload.get("columns")
    limit = payload.get("limit")
    flatten = bool(payload.get("flatten", True))
    max_col_width = payload.get("max_col_width", 50)  # Default 50 chars for width cap
    code_fence = bool(payload.get("code_fence") or payload.get("wrap", False))

    norm = _normalize(data, columns=columns, limit=limit, flatten=flatten)
    cols: list[str] = list(norm["columns"])
    if not cols:
        # Non-tabular → render as fenced JSON block
        content = _with_fence(_json_dumps(data, indent=2, sort_keys=True, ensure_ascii=False), "json")
        return {
            "ok": True,
            "action": "markdown",
            "format": "text/markdown",
            "content": content,
            "bytes": len(content.encode("utf-8")),
        }

    # Header
    header = "| " + " | ".join(_md_escape(str(c)) for c in cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"

    # Rows
    body_lines: list[str] = []
    for r in norm["rows"]:
        cells = []
        for c in cols:
            val = r.get(c, "")
            cell = _truncate(val, max_col_width)
            cells.append(_md_escape(cell))
        body_lines.append("| " + " | ".join(cells) + " |")

    table = "\n".join([header, sep, *body_lines])
    content = _with_fence(table, "md") if code_fence else table

    return {
        "ok": True,
        "action": "markdown",
        "format": "text/markdown",
        "columns": cols,
        "rowcount": len(norm["rows"]),
        "content": content,
        "bytes": len(content.encode("utf-8")),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Plain text
# ─────────────────────────────────────────────────────────────────────────────
def _act_text(payload: dict[str, Any], ctx: ToolContext | None = None) -> dict[str, Any]:
    """Format data as plain text."""
    data = payload.get("data")
    columns = payload.get("columns")
    limit = payload.get("limit")
    flatten = bool(payload.get("flatten", True))
    sep = payload.get("separator") or "\n"
    kv_sep = payload.get("key_value_sep") or ": "
    code_fence = bool(payload.get("code_fence") or payload.get("wrap", False))

    # String is returned as-is (optionally fenced)
    if isinstance(data, str):
        content = data
        if code_fence:
            content = _with_fence(content, "text")
        return {
            "ok": True,
            "action": "text",
            "format": "text/plain",
            "content": content,
            "bytes": len(content.encode("utf-8")),
        }

    norm = _normalize(data, columns=columns, limit=limit, flatten=flatten)
    cols: list[str] = list(norm["columns"])
    lines: list[str] = []

    if not cols:
        # Non-tabular → stringify JSON compactly
        content = _json_dumps(data, indent=None, sort_keys=True, ensure_ascii=False)
        if code_fence:
            content = _with_fence(content, "json")
        return {
            "ok": True,
            "action": "text",
            "format": "text/plain",
            "content": content,
            "bytes": len(content.encode("utf-8")),
        }

    for r in norm["rows"]:
        parts = [f"{c}{kv_sep}{r.get(c, '')}" for c in cols]
        lines.append(", ".join(parts))

    content = sep.join(lines)
    if code_fence:
        content = _with_fence(content, "text")

    return {
        "ok": True,
        "action": "text",
        "format": "text/plain",
        "columns": cols,
        "rowcount": len(norm["rows"]),
        "content": content,
        "bytes": len(content.encode("utf-8")),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Normalize
# ─────────────────────────────────────────────────────────────────────────────
def _act_normalize(payload: dict[str, Any], ctx: ToolContext | None = None) -> dict[str, Any]:
    """Normalize data to {columns, rows} format."""
    limit = payload.get("limit")
    flatten = bool(payload.get("flatten", True))
    columns = payload.get("columns")
    norm = _normalize(payload.get("data"), columns=columns, limit=limit, flatten=flatten)
    return {"ok": True, "action": "normalize", **norm, "rowcount": len(norm["rows"])}


# ─────────────────────────────────────────────────────────────────────────────
# Public entrypoint
# ─────────────────────────────────────────────────────────────────────────────
@mcp_tool(tool_name="output.format", required_scope="output:format")
def invoke(payload: dict[str, Any] | None = None, **kwargs) -> dict[str, Any]:
    """
    Format dispatcher. See module docstring for available actions and options.
    """
    payload = payload or {}
    ctx = kwargs.get("ctx") or ToolContext()
    action = str(payload.get("action") or "json").strip().lower()

    if action == "normalize":
        return _act_normalize(payload, ctx)
    if action in {"json"}:
        return _act_json(payload, ctx)
    if action in {"csv"}:
        return _act_csv(payload, ctx)
    if action in {"markdown", "md"}:
        return _act_markdown(payload, ctx)
    if action in {"text", "plain"}:
        return _act_text(payload, ctx)

    raise ValueError("action must be one of: json, csv, markdown, text, normalize")


# Back-compat aliases
run = invoke
handle = invoke

__all__ = [
    # helpers (useful for tests)
    "_normalize",
    "flatten_dict",
    "handle",
    "invoke",
    "run",
]
