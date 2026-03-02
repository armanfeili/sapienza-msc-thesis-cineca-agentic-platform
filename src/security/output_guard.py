"""
Output guardrails (with a focus on Cypher safety).

Why this exists
---------------
LLM-generated Cypher (or hand-written queries coming from an API) can easily be
destructive or unbounded. This module provides:
- Lightweight analysis of Cypher strings (detect writes, destructive ops,
  unbounded traversals, missing LIMIT on RETURN queries, etc.).
- Guarding/sanitization utilities that can **append a LIMIT** automatically and/or
  **block** dangerous statements, depending on configured mode.

Configuration knobs (read from settings if present; safe defaults otherwise)
---------------------------------------------------------------------------
- OUTPUT_GUARD_MODE: "enforce" | "monitor" | "off"            (default: "monitor")
- OUTPUT_GUARD_ALLOW_WRITES: bool                              (default: False)
- OUTPUT_GUARD_ENFORCE_LIMIT: bool                             (default: True)
- OUTPUT_GUARD_DEFAULT_LIMIT: int                              (default: 100)
- OUTPUT_GUARD_BLOCK_DROP_GRAPH: bool                          (default: True)

Public API
----------
- analyze_cypher(query) -> CypherAnalysis
- guard_cypher(query, *, ...) -> OutputGuardResult
- ensure_cypher_limit(query, limit=100) -> str
- guard_text(text, *, ...) -> OutputGuardResult  (coarse intent check via intent_filter)
"""

from __future__ import annotations

import contextlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException, status

from src.config import settings

from .audit import audit_policy_decision

logger = logging.getLogger(__name__)

# Optional re-use of intent filter for text outputs
try:  # pragma: no cover
    from .intent_filter import analyze_intent
except Exception:  # pragma: no cover
    analyze_intent = None  # type: ignore


# ──────────────────────────────────────────────────────────────────────────────
# Config helpers with safe defaults
# ──────────────────────────────────────────────────────────────────────────────
def _cfg(name: str, default: Any) -> Any:
    return getattr(settings, name, default)


def _mode() -> str:
    return str(_cfg("OUTPUT_GUARD_MODE", "monitor")).lower()


def _allow_writes() -> bool:
    return bool(_cfg("OUTPUT_GUARD_ALLOW_WRITES", False))


def _enforce_limit() -> bool:
    return bool(_cfg("OUTPUT_GUARD_ENFORCE_LIMIT", True))


def _default_limit() -> int:
    return int(_cfg("OUTPUT_GUARD_DEFAULT_LIMIT", 100))


def _block_drop_graph() -> bool:
    return bool(_cfg("OUTPUT_GUARD_BLOCK_DROP_GRAPH", True))


# ──────────────────────────────────────────────────────────────────────────────
# Cypher heuristics
# ──────────────────────────────────────────────────────────────────────────────
# NOTE: These regexes are case-insensitive and intentionally simple.
RE_RETURN = re.compile(r"(?is)\bRETURN\b")
RE_LIMIT = re.compile(r"(?is)\bLIMIT\b")
RE_WRITE = re.compile(r"(?is)\b(CREATE|MERGE|SET|DELETE|DETACH\s+DELETE|REMOVE)\b")
RE_DROP_GRAPH = re.compile(r"(?is)\bDROP\s+GRAPH\b")
RE_LOAD = re.compile(r"(?is)\bLOAD\s+CSV\b")
RE_CALL_WRITEY = re.compile(r"(?is)\bCALL\b.*\b(write|create|delete|update)\b")
RE_UNBOUNDED = re.compile(r"-\s*\[\s*\*\s*(?:\d*\s*\.\.\s*\d*)?\s*\]\s*-")  # -[*]->  or -[*..]-> etc.


@dataclass(frozen=True)
class CypherAnalysis:
    text: str
    has_return: bool
    has_limit: bool
    writes: bool
    destructive: bool
    unbounded: bool
    risky_call: bool
    risk_score: int
    reasons: list[str] = field(default_factory=list)


def analyze_cypher(query: str) -> CypherAnalysis:
    q = (query or "").strip()
    reasons: list[str] = []
    risk = 0

    has_return = bool(RE_RETURN.search(q))
    has_limit = bool(RE_LIMIT.search(q))
    writes = bool(RE_WRITE.search(q) or RE_LOAD.search(q))
    destructive = bool(RE_DROP_GRAPH.search(q) or re.search(r"(?is)\bTRUNCATE\b", q))
    risky_call = bool(RE_CALL_WRITEY.search(q))
    unbounded = bool(RE_UNBOUNDED.search(q))

    if writes:
        reasons.append("write-verb present (CREATE/MERGE/SET/DELETE/REMOVE/LOAD CSV)")
        risk += 35
    if destructive:
        reasons.append("destructive verb present (DROP GRAPH / TRUNCATE)")
        risk += 50
    if risky_call:
        reasons.append("CALL likely to mutate (contains write/create/delete/update)")
        risk += 25
    if has_return and not has_limit:
        reasons.append("RETURN without LIMIT")
        risk += 15
    if unbounded:
        reasons.append("unbounded variable-length traversal")
        risk += 20

    risk = min(100, risk)
    return CypherAnalysis(
        text=q,
        has_return=has_return,
        has_limit=has_limit,
        writes=writes,
        destructive=destructive,
        unbounded=unbounded,
        risky_call=risky_call,
        risk_score=risk,
        reasons=reasons,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Guard & sanitize
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class OutputGuardResult:
    allowed: bool
    action: str  # "allow" | "monitor" | "block" | "limited"
    reasons: list[str] = field(default_factory=list)
    risk_score: int = 0
    sanitized_query: str | None = None
    analysis: CypherAnalysis | None = None


def ensure_cypher_limit(query: str, limit: int | None = None) -> str:
    """
    Append `LIMIT N` if the query returns rows but has no LIMIT.
    Keeps trailing semicolon style consistent.
    """
    limit = int(limit or _default_limit())
    q = (query or "").strip()
    # Only add limit if last RETURN clause exists and there's no LIMIT after it
    if not re.search(r"RETURN\b(?!.*\bLIMIT\b)", q, re.I | re.S):
        return q

    # Remove trailing semicolons and whitespace
    q_no_semi = re.sub(r"\s*;+$", "", q)
    return f"{q_no_semi} LIMIT {limit}"


def guard_cypher(
    query: str,
    *,
    mode: str | None = None,
    allow_writes: bool | None = None,
    enforce_limit: bool | None = None,
    default_limit: int | None = None,
    resource: str | None = None,
    user: Any | None = None,
    raise_on_block: bool = True,
) -> OutputGuardResult:
    """
    Analyze and (optionally) enforce Cypher guardrails.

    Behavior:
      - If destructive and mode=="enforce" (or _block_drop_graph()), block.
      - If writes and not allow_writes and mode=="enforce", block.
      - If RETURN lacks LIMIT and enforce_limit, append LIMIT.
      - In monitor mode, never block; just annotate.
    """
    m = (mode or _mode()).lower()
    allow_w = _allow_writes() if allow_writes is None else bool(allow_writes)
    must_limit = _enforce_limit() if enforce_limit is None else bool(enforce_limit)
    limit_n = _default_limit() if default_limit is None else int(default_limit)

    analysis = analyze_cypher(query)
    reasons = list(analysis.reasons)
    action = "allow"
    allowed = True
    sanitized = analysis.text

    # Decide on blocking
    if m == "off":
        pass
    elif analysis.destructive and (_block_drop_graph() or m == "enforce"):
        allowed = False
        action = "block"
        reasons.append("destructive statements are not permitted")
    elif analysis.writes and not allow_w and m == "enforce":
        allowed = False
        action = "block"
        reasons.append("write operations are not allowed")
    elif analysis.risky_call and not allow_w and m == "enforce":
        allowed = False
        action = "block"
        reasons.append("risky CALL detected and writes disabled")

    # Auto-limit
    if allowed and must_limit and analysis.has_return and not analysis.has_limit:
        sanitized = ensure_cypher_limit(sanitized, limit=limit_n)
        action = "limited" if m == "enforce" else "monitor"
        reasons.append(f"auto-appended LIMIT {limit_n}")

    # Audit policy decision (best-effort)
    try:
        principal = None
        if user is not None:
            for key in ("username", "email", "sub"):
                if hasattr(user, key):
                    principal = getattr(user, key)
                    break
                if isinstance(user, dict) and key in user:
                    principal = user[key]
                    break
        audit_policy_decision(
            policy="output_guard.cypher",
            subject=str(principal) if principal else None,
            action="compile",
            resource=resource or "cypher",
            allowed=allowed,
            reason="; ".join(reasons) if reasons else None,
            attributes={
                "mode": m,
                "allow_writes": allow_w,
                "enforce_limit": must_limit,
                "risk_score": analysis.risk_score,
                "flags": {
                    "writes": analysis.writes,
                    "destructive": analysis.destructive,
                    "unbounded": analysis.unbounded,
                    "has_return": analysis.has_return,
                    "has_limit": analysis.has_limit,
                    "risky_call": analysis.risky_call,
                },
            },
        )
    except Exception:
        logger.debug("output_guard: audit_policy_decision failed", exc_info=True)

    if not allowed and m == "enforce" and raise_on_block:
        detail = {
            "message": "Query blocked by output guard",
            "reasons": reasons,
            "risk_score": analysis.risk_score,
        }
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

    result_action = "monitor" if (not allowed and m != "enforce") else action
    return OutputGuardResult(
        allowed=allowed or m != "enforce",
        action=result_action,
        reasons=reasons,
        risk_score=analysis.risk_score,
        sanitized_query=sanitized,
        analysis=analysis,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Text guard (coarse; delegates to intent filter when available)
# ──────────────────────────────────────────────────────────────────────────────
def guard_text(
    text: str,
    *,
    mode: str | None = None,
    resource: str | None = None,
    user: Any | None = None,
    raise_on_block: bool = False,
) -> OutputGuardResult:
    """
    Coarse guard for free-form text. If the intent filter is available, we reuse it.
    """
    m = (mode or _mode()).lower()
    if analyze_intent is None:
        return OutputGuardResult(allowed=True, action="allow", reasons=[], risk_score=0, sanitized_query=None)

    res = analyze_intent(text)
    allowed = res.allowed or (m != "enforce")
    action = res.action if res.action in {"allow", "monitor"} else ("block" if m == "enforce" else "monitor")

    with contextlib.suppress(Exception):
        audit_policy_decision(
            policy="output_guard.text",
            subject=(getattr(user, "username", None) if user else None),
            action="emit",
            resource=resource or "text",
            allowed=allowed,
            reason="; ".join(res.reasons) if res.reasons else None,
            attributes={"risk_score": res.risk_score, "mode": m, "categories": res.categories},
        )

    if action == "block" and raise_on_block:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail={"message": "Text blocked", "reasons": res.reasons}
        )

    return OutputGuardResult(
        allowed=allowed,
        action=action,
        reasons=res.reasons,
        risk_score=res.risk_score,
        sanitized_query=None,
        analysis=None,
    )


__all__ = [
    "CypherAnalysis",
    "OutputGuardResult",
    "analyze_cypher",
    "ensure_cypher_limit",
    "guard_cypher",
    "guard_text",
]
