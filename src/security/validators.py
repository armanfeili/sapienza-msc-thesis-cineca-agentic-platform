"""
Input validation helpers for the Cineca Agentic Platform.

This module centralizes small, dependency-light validators that you can reuse
across routers/services. They are deliberately pragmatic: simple types,
clear error messages, and no hidden side effects.

Highlights
----------
- Primitive validators: ensure_str/int/float/bool/list/dict
- Common patterns: validate_pagination, validate_sort, validate_identifier
- Cost/limit guards: validate_result_limits, validate_query_cost
- Error plumbing: ValidationProblem + helpers to raise HTTP 422/400 consistently
- Pydantic-friendly error formatting (without requiring a model)

Notes
-----
- Prefer raising `ValidationProblem` with one or more `Issue`s when you want to
  report multiple validation errors at once.
- For quick checks, the `ensure_*` helpers raise `ValueError` with context.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status

from src.config import settings


# ──────────────────────────────────────────────────────────────────────────────
# Error model
# ──────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Issue:
    field: str
    msg: str
    type: str = "value_error"


class ValidationProblem(Exception):
    """Collects one or more issues for 422-style responses."""

    def __init__(self, issues: Iterable[Issue] | None = None, message: str | None = None) -> None:
        self.issues: list[Issue] = list(issues or [])
        super().__init__(message or self._default_message())

    def add(self, field: str, msg: str, type: str = "value_error") -> None:
        self.issues.append(Issue(field=field, msg=msg, type=type))

    def _default_message(self) -> str:
        if not self.issues:
            return "validation error"
        if len(self.issues) == 1:
            i = self.issues[0]
            return f"{i.field}: {i.msg}"
        return f"{len(self.issues)} validation errors"

    def to_fastapi_detail(self) -> list[dict[str, Any]]:
        """Shape similar to pydantic's error format."""
        out: list[dict[str, Any]] = []
        for i in self.issues:
            loc = tuple(i.field.split(".")) if i.field else ("body",)
            out.append({"loc": loc, "msg": i.msg, "type": i.type})
        return out


def raise_http_422(problem: ValidationProblem) -> None:
    """Raise a FastAPI HTTPException(422) with structured detail."""
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=problem.to_fastapi_detail(),
    )


def http_400(msg: str, *, field: str | None = None) -> HTTPException:
    detail = [{"loc": tuple(field.split(".")) if field else ("body",), "msg": msg, "type": "value_error"}]
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


# ──────────────────────────────────────────────────────────────────────────────
# Primitive validators / normalizers
# ──────────────────────────────────────────────────────────────────────────────
_STRIP_RE = re.compile(r"\s+")


def normalize_whitespace(s: str) -> str:
    """Collapse consecutive whitespace to single spaces and strip ends."""
    return _STRIP_RE.sub(" ", s).strip()


def ensure_str(
    value: Any,
    *,
    field: str = "value",
    min_len: int | None = None,
    max_len: int | None = 4096,
    pattern: str | None = None,
    strip: bool = True,
    allow_empty: bool = False,
) -> str:
    """Coerce/validate a string with optional length + regex pattern."""
    if value is None:
        raise ValueError(f"{field} is required")
    if not isinstance(value, str):
        value = str(value)
    s = value.strip() if strip else value
    if not allow_empty and s == "":
        raise ValueError(f"{field} must not be empty")
    if min_len is not None and len(s) < min_len:
        raise ValueError(f"{field} must be at least {min_len} characters")
    if max_len is not None and len(s) > max_len:
        raise ValueError(f"{field} must be at most {max_len} characters")
    if pattern and not re.fullmatch(pattern, s):
        raise ValueError(f"{field} has invalid format")
    return s


def ensure_int(
    value: Any,
    *,
    field: str = "value",
    min_value: int | None = None,
    max_value: int | None = None,
) -> int:
    """Coerce/validate an integer with bounds."""
    if value is None:
        raise ValueError(f"{field} is required")
    try:
        n = int(value)
    except Exception:
        raise ValueError(f"{field} must be an integer")
    if min_value is not None and n < min_value:
        raise ValueError(f"{field} must be >= {min_value}")
    if max_value is not None and n > max_value:
        raise ValueError(f"{field} must be <= {max_value}")
    return n


def ensure_float(
    value: Any,
    *,
    field: str = "value",
    min_value: float | None = None,
    max_value: float | None = None,
) -> float:
    """Coerce/validate a float with bounds."""
    if value is None:
        raise ValueError(f"{field} is required")
    try:
        x = float(value)
        if math.isnan(x) or math.isinf(x):
            raise ValueError
    except Exception:
        raise ValueError(f"{field} must be a finite number")
    if min_value is not None and x < float(min_value):
        raise ValueError(f"{field} must be >= {min_value}")
    if max_value is not None and x > float(max_value):
        raise ValueError(f"{field} must be <= {max_value}")
    return x


def ensure_bool(value: Any, *, field: str = "value") -> bool:
    """Coerce/validate a boolean."""
    truthy = {"true", "1", "yes", "y", "on"}
    falsy = {"false", "0", "no", "n", "off"}
    if isinstance(value, bool):
        return value
    if value is None:
        raise ValueError(f"{field} is required")
    s = str(value).strip().lower()
    if s in truthy:
        return True
    if s in falsy:
        return False
    raise ValueError(f"{field} must be a boolean")


def ensure_list(
    value: Any,
    *,
    field: str = "value",
    item_validator: Callable[[Any], Any] | None = None,
    min_len: int | None = None,
    max_len: int | None = None,
) -> list[Any]:
    """Validate a list with optional item validator and length bounds."""
    if value is None:
        raise ValueError(f"{field} is required")
    if isinstance(value, (tuple, set)):
        value = list(value)
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    lst = value
    if min_len is not None and len(lst) < min_len:
        raise ValueError(f"{field} must contain at least {min_len} items")
    if max_len is not None and len(lst) > max_len:
        raise ValueError(f"{field} must contain at most {max_len} items")
    if item_validator:
        out: list[Any] = []
        for i, item in enumerate(lst):
            try:
                out.append(item_validator(item))
            except Exception as e:
                raise ValueError(f"{field}[{i}]: {e}") from e
        return out
    return lst


def ensure_dict(
    value: Any,
    *,
    field: str = "value",
    required_keys: Iterable[str] | None = None,
    allowed_keys: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Validate a dict with optional required/allowed key constraints."""
    if value is None:
        raise ValueError(f"{field} is required")
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    d = dict(value)
    if required_keys:
        missing = [k for k in required_keys if k not in d]
        if missing:
            raise ValueError(f"{field} missing required keys: {', '.join(missing)}")
    if allowed_keys:
        extras = [k for k in d if k not in set(allowed_keys)]
        if extras:
            raise ValueError(f"{field} has unexpected keys: {', '.join(extras)}")
    return d


# ──────────────────────────────────────────────────────────────────────────────
# Common patterns
# ──────────────────────────────────────────────────────────────────────────────
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


def validate_identifier(token: str, *, field: str = "identifier") -> str:
    """Validate an identifier (letters, digits, underscore; no leading digit)."""
    s = ensure_str(token, field=field, min_len=1, max_len=64)
    if not _IDENTIFIER_RE.fullmatch(s):
        raise ValueError(f"{field} must match {_IDENTIFIER_RE.pattern}")
    return s


def validate_pagination(
    *,
    limit: Any,
    offset: Any = 0,
    max_limit: int = 100,
    field_limit: str = "limit",
    field_offset: str = "offset",
) -> tuple[int, int]:
    """Validate (limit, offset) pair with sane bounds."""
    lim = ensure_int(limit, field=field_limit, min_value=1, max_value=max_limit)
    off = ensure_int(offset, field=field_offset, min_value=0)
    return lim, off


def validate_sort(
    sort_by: Any,
    *,
    allowed_fields: Iterable[str],
    allow_minus: bool = True,
    field: str = "sort_by",
) -> str:
    """
    Validate a sort field. Accepts optional '-' prefix for descending if allow_minus.
    """
    s = ensure_str(sort_by, field=field, min_len=1, max_len=64)
    desc = s.startswith("-") and allow_minus
    name = s[1:] if desc else s
    if name not in set(allowed_fields):
        raise ValueError(f"{field} must be one of {sorted(set(allowed_fields))}")
    return "-" + name if desc else name


def safe_json_loads(text: Any, *, field: str = "json", max_chars: int = 200_000) -> Any:
    """Parse JSON string with a size cap to avoid pathological payloads."""
    s = ensure_str(text, field=field, max_len=max_chars)
    try:
        return json.loads(s)
    except Exception as e:
        raise ValueError(f"{field} is not valid JSON: {e}") from e


# ──────────────────────────────────────────────────────────────────────────────
# Safety rails / limits
# ──────────────────────────────────────────────────────────────────────────────
def validate_result_limits(
    *,
    nodes: int | None = None,
    edges: int | None = None,
    field_nodes: str = "max_nodes",
    field_edges: str = "max_edges",
) -> tuple[int | None, int | None]:
    """
    Enforce upper limits (from settings) for graph results. Returns sanitized values.
    """
    max_nodes = settings.MAX_GRAPH_RESULT_NODES
    max_edges = settings.MAX_GRAPH_RESULT_EDGES

    n = None if nodes is None else ensure_int(nodes, field=field_nodes, min_value=1, max_value=max_nodes)
    e = None if edges is None else ensure_int(edges, field=field_edges, min_value=1, max_value=max_edges)
    return n, e


def validate_query_cost(
    *,
    estimated_nodes: int,
    estimated_edges: int,
    limit: int | None = None,
    field: str = "query",
) -> None:
    """
    Very rough guardrail to avoid runaway queries.
    Raises ValueError if (nodes + edges) * (limit or 1) exceeds MAX_QUERY_COST.
    """
    n = ensure_int(estimated_nodes, field=f"{field}.estimated_nodes", min_value=0)
    e = ensure_int(estimated_edges, field=f"{field}.estimated_edges", min_value=0)
    l = 1 if limit is None else ensure_int(limit, field=f"{field}.limit", min_value=1)
    cost = (n + e) * l
    if cost > settings.MAX_QUERY_COST:
        raise ValueError(
            f"{field} estimated cost {cost} exceeds max {settings.MAX_QUERY_COST} " f"(nodes={n}, edges={e}, limit={l})"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Multi-error validation helper
# ──────────────────────────────────────────────────────────────────────────────
def validate_fields(specs: Sequence[tuple[str, Callable[[], Any]]]) -> dict[str, Any]:
    """
    Validate multiple fields and collect all errors before raising.

    Example:
        data = validate_fields([
            ("username", lambda: ensure_str(body.get("username"), field="username", min_len=3, max_len=50)),
            ("limit",    lambda: ensure_int(query.get("limit", 50), field="limit", min_value=1, max_value=100)),
        ])
    """
    out: dict[str, Any] = {}
    problem = ValidationProblem()
    for name, fn in specs:
        try:
            out[name] = fn()
        except ValidationProblem as vp:
            for iss in vp.issues:
                problem.add(iss.field or name, iss.msg, iss.type)
        except ValueError as ve:
            problem.add(name, str(ve))
        except Exception as e:
            problem.add(name, f"invalid value: {e}")
    if problem.issues:
        raise problem
    return out


__all__ = [
    "Issue",
    "ValidationProblem",
    "ensure_bool",
    "ensure_dict",
    "ensure_float",
    "ensure_int",
    "ensure_list",
    "ensure_str",
    "http_400",
    "normalize_whitespace",
    "raise_http_422",
    "safe_json_loads",
    "validate_fields",
    "validate_identifier",
    "validate_pagination",
    "validate_query_cost",
    "validate_result_limits",
    "validate_sort",
]
