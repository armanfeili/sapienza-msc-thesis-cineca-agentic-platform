"""
Intent filter: lightweight guardrails for unsafe or costly requests.

Goals
-----
- Quick heuristics to detect high-risk intents (data exfiltration, destructive DB
  ops, prompt injection, shell abuse, unbounded graph queries, secrets scraping).
- Return a structured result (risk score, categories, reasons).
- Configurable action via settings:
    INTENT_FILTER_MODE: "enforce" | "monitor"  (default: "monitor")
      - enforce: block flagged requests (HTTP 400) unless explicitly told not to raise
      - monitor: never block, only annotate result; callers can decide
- Zero heavy dependencies; pure regex and keyword matching.

Usage
-----
    from src.security.intent_filter import analyze_intent, enforce_intent

    res = analyze_intent("MATCH (n)-[*]->(m) RETURN n")
    if not res.allowed:
        # log / transform / return
        ...

    # Or in a router/service:
    enforce_intent(user_prompt, resource="/agent/run", user=current_user)

Notes
-----
- This module is intentionally conservative and coarse. Adjust patterns and
  thresholds for your environment. Prefer denying on *intent* rather than on
  specific strings only.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException, status

from src.config import settings

from .audit import audit_policy_decision

logger = logging.getLogger(__name__)


# ---------------- Configuration helpers ----------------
def _mode() -> str:
    # Safe getattr in case config didn't define the field
    return getattr(settings, "INTENT_FILTER_MODE", "monitor").lower()


def _enabled() -> bool:
    return bool(getattr(settings, "INTENT_FILTER_ENABLED", True))


# ---------------- Data model ----------------
@dataclass
class IntentResult:
    allowed: bool
    action: str  # "allow" | "monitor" | "block"
    risk_score: int  # 0..100
    categories: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    sanitized: str | None = None


# ---------------- Patterns ----------------
# Prompt injection / jailbreak cues
RE_PROMPT_INJECTION = re.compile(r"(?i)\b(ignore|bypass|override|forget)\b.*\b(instruction|policy|guard|safety)\b")

# Obvious secret scraping / exfil intent
RE_SECRETS = re.compile(r"(?i)\b(api[_ -]?key|secret|password|token|ssh[_ -]?key)\b")

# PII hunting
RE_PII = re.compile(r"(?i)\b(ssn|social security|credit\s*card|cvv|iban|passport|national id|tax id)\b")

# Dangerous shell / OS ops
RE_SHELL = re.compile(
    r"(?i)\b(rm\s+-rf\b|mkfs\w*\b|dd\s+if=\b|format\s+c:\b|shutdown\b|poweroff\b|reboot\b|del\s+/s\s+/q\b)"
)

# SQL-ish destructive ops
RE_SQL_DROP = re.compile(r"(?i)\b(drop\s+(database|table)\b|truncate\s+table\b)")

# Cypher / Memgraph destructive ops
RE_CYPHER_DANGER = re.compile(r"(?i)\b(detach\s+delete\b|drop\s+graph\b)")

# Pathological graph patterns: unbounded variable-length traversals
RE_CYPHER_UNBOUNDED = re.compile(r"-\s*\[\s*\*\s*\]\s*-|(\*){3,}")

# Broad exfil cues
RE_EXFIL = re.compile(r"(?i)\b(dump|export|download)\b.*\b(all|everything|entire|database|db)\b")

# Malware / exploit cues (very coarse)
RE_EXPLOIT = re.compile(r"(?i)\b(buffer overflow|exploit|rce|reverse shell)\b")


# ---------------- Core logic ----------------
def _score(hit: bool, weight: int) -> int:
    return weight if hit else 0


def analyze_intent(text: str, *, context: dict[str, Any] | None = None) -> IntentResult:
    """
    Analyze a user-provided text and return a structured risk assessment.
    """
    t = (text or "").strip()
    if not t:
        return IntentResult(allowed=True, action="allow", risk_score=0)

    categories: list[str] = []
    reasons: list[str] = []
    risk = 0

    def add(cat: str, reason: str, w: int) -> None:
        nonlocal risk
        if cat not in categories:
            categories.append(cat)
        reasons.append(reason)
        risk = min(100, risk + w)

    # Prompt injection attempts
    if RE_PROMPT_INJECTION.search(t):
        add("prompt_injection", "attempt to override/ignore safety or instructions", 20)

    # Secrets scraping
    if RE_SECRETS.search(t):
        add("secrets", "request mentions secrets/tokens/passwords", 25)

    # PII hunting
    if RE_PII.search(t):
        add("pii", "request mentions sensitive PII", 20)

    # OS / shell abuse
    if RE_SHELL.search(t):
        add("system_abuse", "dangerous shell/OS operation requested", 40)

    # SQL destructive
    # -    if RE_SQL_DROP.search(t):
    # -        add("db_destructive", "destructive SQL keyword present", 30)
    # +    # SQL destructive — treat explicit DROP/TRUNCATE as an immediate block
    if RE_SQL_DROP.search(t):
        # Mark explicit destructive SQL statements as disallowed immediately.
        return IntentResult(
            allowed=False,
            action="block",
            risk_score=100,
            categories=["db_destructive"],
            reasons=["destructive SQL statement detected"],
        )

    # Cypher destructive
    if RE_CYPHER_DANGER.search(t):
        add("graph_destructive", "destructive Cypher keyword present", 35)

    # Cypher DoS-like patterns
    if RE_CYPHER_UNBOUNDED.search(t):
        add("graph_dos", "unbounded variable-length traversal in query", 20)

    # Bulk exfiltration
    if RE_EXFIL.search(t):
        add("exfiltration", "bulk export/dump of all data requested", 25)

    # Exploit-y language
    if RE_EXPLOIT.search(t):
        add("exploit", "exploit development or reverse shell cues", 30)

    # Heuristic: global "delete everything" cues
    if re.search(r"(?i)\b(delete|erase|remove|wipe)\b.*\b(all|everything)\b", t):
        add("destructive", "mass deletion intent", 35)
        # Mark explicit mass-deletion intents as disallowed
        return IntentResult(
            allowed=False,
            action="block",
            risk_score=min(100, 35),
            categories=categories or ["destructive"],
            reasons=["mass deletion intent"],
        )

    # Decide action by threshold
    # Tunables:
    hard_block = risk >= 60 or "graph_destructive" in categories or "system_abuse" in categories
    soft_flag = (risk >= 25) or bool(categories)

    mode = _mode()
    if not _enabled():
        return IntentResult(allowed=True, action="allow", risk_score=0)

    if hard_block and mode == "enforce":
        return IntentResult(allowed=False, action="block", risk_score=risk, categories=categories, reasons=reasons)

    if soft_flag:
        # In monitor mode we still mark as allowed but with "monitor" action.
        action = "monitor" if mode != "enforce" else "allow"
        return IntentResult(allowed=True, action=action, risk_score=risk, categories=categories, reasons=reasons)

    return IntentResult(allowed=True, action="allow", risk_score=risk, categories=categories, reasons=reasons)


def enforce_intent(
    text: str,
    *,
    resource: str | None = None,
    user: Any | None = None,
    context: dict[str, Any] | None = None,
    raise_on_block: bool = True,
) -> IntentResult:
    """
    Analyze and (optionally) enforce blocking based on configured mode.

    - If mode == "enforce" and result.action == "block", raise HTTP 400 unless
      raise_on_block=False.
    - Always emits a policy audit record with attributes: categories, reasons, score.
    """
    res = analyze_intent(text, context=context)

    # Audit decision (best effort)
    principal = None
    try:
        if user is not None:
            # Extract username/email/sub if present
            for key in ("username", "email", "sub"):
                if hasattr(user, key):
                    principal = getattr(user, key)
                    break
                if isinstance(user, dict) and key in user:
                    principal = user[key]
                    break
        audit_policy_decision(
            policy="intent_filter",
            subject=str(principal) if principal else None,
            action="submit",
            resource=resource or "unknown",
            allowed=res.allowed and res.action != "block",
            reason="; ".join(res.reasons) if res.reasons else None,
            attributes={
                "risk_score": res.risk_score,
                "categories": res.categories,
                "mode": _mode(),
                "enabled": _enabled(),
            },
        )
    except Exception:
        logger.debug("intent_filter: audit_policy_decision failed", exc_info=True)

    if res.action == "block" and raise_on_block:
        detail = {
            "message": "Request blocked by intent filter",
            "risk_score": res.risk_score,
            "categories": res.categories,
            "reasons": res.reasons,
        }
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

    return res


__all__ = ["IntentResult", "analyze_intent", "enforce_intent"]
