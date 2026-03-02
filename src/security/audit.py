"""
Security audit utilities.

This module provides a thin, consistent interface to record security-relevant
events (auth, authorization, access decisions, policy checks, rate limiting,
model usage, data access). It is intentionally light-weight and safe:

- Emits a structured log line (via structlog if configured, else stdlib).
- Mirrors the event into the provenance chain (tamper-evident) **without**
  storing sensitive payloads verbatim — only redacted metadata plus content
  hashes are sent to provenance.
- Exposes convenience helpers like `audit_auth_success(...)`, `audit_access(...)`,
  and a generic `audit_event(...)`.

The functions return an `AuditEvent` instance which includes the generated
event_id and timestamp; callers may ignore the return value if not needed.

This module does not raise if logging/provenance export fails; failures are
swallowed to avoid breaking the request path.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable
from contextlib import suppress
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

# Logging (structlog preferred)
with suppress(Exception):
    from src.logging_setup import get_logger  # type: ignore

    logger = get_logger(__name__)  # type: ignore[assignment]
if "logger" not in globals():
    import logging

    logger = logging.getLogger(__name__)

# Provenance (best-effort)
try:  # pragma: no cover
    from src.provenance import record_provenance
except Exception:  # pragma: no cover
    record_provenance = None  # type: ignore

# Prometheus (optional)
try:  # pragma: no cover
    from prometheus_client import Counter
except Exception:  # pragma: no cover
    Counter = None  # type: ignore

if Counter is not None:  # pragma: no cover
    AUDIT_EVENTS = Counter(
        "security_audit_events_total",
        "Number of security audit events",
        labelnames=("category", "action", "outcome", "severity"),
    )
else:  # pragma: no cover
    AUDIT_EVENTS = None  # type: ignore


# ---------------- helpers ----------------
def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_hex(data: Any) -> str:
    import hashlib

    if isinstance(data, (bytes, bytearray)):
        b = bytes(data)
    elif isinstance(data, str):
        b = data.encode("utf-8")
    else:
        b = _canonical(data).encode("utf-8")
    return hashlib.sha256(b).hexdigest()


_SENSITIVE_KEYS = {
    "password",
    "authorization",
    "authorization_header",
    "auth",
    "token",
    "id_token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "secret",
    "client_secret",
    "ssn",
}


def _scrub_meta(meta: dict[str, Any] | None) -> dict[str, Any]:
    """
    Redact obviously sensitive keys and trim large values.
    """
    if not meta:
        return {}
    out: dict[str, Any] = {}
    for k, v in meta.items():
        lk = str(k).lower()
        if lk in _SENSITIVE_KEYS:
            out[k] = "***"
            continue
        if isinstance(v, str) and len(v) > 512:
            out[k] = v[:512] + "…"
        else:
            out[k] = v
    return out


# ---------------- data model ----------------
@dataclass(slots=True)
class AuditEvent:
    event_id: str
    ts: datetime
    category: str  # e.g., "auth", "access", "policy", "ratelimit", "model", "data"
    action: str  # e.g., "login", "check", "allow", "deny"
    outcome: str  # "success" | "failure" | "allow" | "deny" | "info"
    severity: str = "info"  # "info" | "warning" | "critical"
    principal: str | None = None
    tenant_id: str | None = None
    resource: str | None = None
    trace_id: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    input_hash: str | None = None
    output_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["ts"] = self.ts.isoformat()
        return d


# ---------------- core API ----------------
def audit_event(
    *,
    category: str,
    action: str,
    outcome: str,
    severity: str = "info",
    principal: str | None = None,
    resource: str | None = None,
    tenant_id: str | None = None,
    trace_id: str | None = None,
    meta: dict[str, Any] | None = None,
    content_in: Any | None = None,
    content_out: Any | None = None,
) -> AuditEvent:
    """
    Generic audit event emitter. Redacts meta and mirrors into provenance with hashes.
    """
    ev = AuditEvent(
        event_id=str(uuid.uuid4()),
        ts=_utcnow(),
        category=str(category),
        action=str(action),
        outcome=str(outcome),
        severity=str(severity).lower(),
        principal=str(principal) if principal else None,
        tenant_id=str(tenant_id) if tenant_id else None,
        resource=str(resource) if resource else None,
        trace_id=str(trace_id) if trace_id else None,
        meta=_scrub_meta(meta),
        input_hash=_sha256_hex(content_in) if content_in is not None else None,
        output_hash=_sha256_hex(content_out) if content_out is not None else None,
    )

    # Structured log
    try:
        logger.info(
            "security_audit",
            **ev.to_dict(),
        )
    except Exception:  # pragma: no cover
        # avoid breaking the request path due to logging issues
        pass

    # Prometheus
    if AUDIT_EVENTS is not None:  # pragma: no cover
        with suppress(Exception):
            AUDIT_EVENTS.labels(category=ev.category, action=ev.action, outcome=ev.outcome, severity=ev.severity).inc()

    # Provenance (best-effort, hashed)
    if record_provenance is not None:  # pragma: no cover
        with suppress(Exception):
            record_provenance(
                actor="security",
                action=f"audit.{ev.category}.{ev.action}",
                resource=ev.resource or "security",
                input={"principal": ev.principal, "tenant_id": ev.tenant_id, "meta": ev.meta},
                output={"outcome": ev.outcome, "severity": ev.severity},
                meta={"trace_id": ev.trace_id} if ev.trace_id else {},
            )

    return ev


# ---------------- convenience wrappers ----------------
def audit_auth_success(
    *,
    username: str,
    scopes: Iterable[str] | None = None,
    tenant_id: str | None = None,
    trace_id: str | None = None,
) -> AuditEvent:
    return audit_event(
        category="auth",
        action="login",
        outcome="success",
        severity="info",
        principal=username,
        tenant_id=tenant_id,
        trace_id=trace_id,
        meta={"scopes": list(scopes or [])},
    )


def audit_auth_failure(
    *, username: str | None, reason: str, tenant_id: str | None = None, trace_id: str | None = None
) -> AuditEvent:
    return audit_event(
        category="auth",
        action="login",
        outcome="failure",
        severity="warning",
        principal=username,
        tenant_id=tenant_id,
        trace_id=trace_id,
        meta={"reason": reason},
    )


def audit_access(
    *,
    principal: str | None,
    resource: str,
    method: str = "GET",
    allowed: bool,
    reason: str | None = None,
    tenant_id: str | None = None,
    trace_id: str | None = None,
) -> AuditEvent:
    return audit_event(
        category="access",
        action="allow" if allowed else "deny",
        outcome="allow" if allowed else "deny",
        severity="info" if allowed else "warning",
        principal=principal,
        resource=resource,
        tenant_id=tenant_id,
        trace_id=trace_id,
        meta={"method": method, "reason": reason} if reason else {"method": method},
    )


def audit_policy_decision(
    *,
    policy: str,
    subject: str | None,
    action: str,
    resource: str,
    allowed: bool,
    reason: str | None = None,
    tenant_id: str | None = None,
    trace_id: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> AuditEvent:
    return audit_event(
        category="policy",
        action=action,
        outcome="allow" if allowed else "deny",
        severity="info" if allowed else "warning",
        principal=subject,
        resource=resource,
        tenant_id=tenant_id,
        trace_id=trace_id,
        meta={"policy": policy, "reason": reason, "attributes": _scrub_meta(attributes or {})},
    )


def audit_rate_limit(
    *,
    principal: str | None,
    key: str,
    allowed: bool,
    limit: int,
    window_seconds: int,
    count: int,
    tenant_id: str | None = None,
    trace_id: str | None = None,
) -> AuditEvent:
    return audit_event(
        category="ratelimit",
        action="check",
        outcome="allow" if allowed else "deny",
        severity="info" if allowed else "warning",
        principal=principal,
        resource=key,
        tenant_id=tenant_id,
        trace_id=trace_id,
        meta={"limit": limit, "window_seconds": window_seconds, "count": count},
    )


def audit_model_usage(
    *,
    principal: str | None,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    success: bool = True,
    tenant_id: str | None = None,
    trace_id: str | None = None,
) -> AuditEvent:
    return audit_event(
        category="model",
        action="complete",
        outcome="success" if success else "failure",
        severity="info" if success else "warning",
        principal=principal,
        resource=model,
        tenant_id=tenant_id,
        trace_id=trace_id,
        meta={
            "usage": {
                "prompt_tokens": int(prompt_tokens),
                "completion_tokens": int(completion_tokens),
                "total_tokens": int(total_tokens),
            }
        },
    )


def audit_data_access(
    *,
    principal: str | None,
    operation: str,  # "read" | "write" | "delete" | "export"
    data_classification: str = "internal",
    resource: str | None = None,
    record_count: int | None = None,
    tenant_id: str | None = None,
    trace_id: str | None = None,
) -> AuditEvent:
    return audit_event(
        category="data",
        action=operation,
        outcome="success",
        severity="info",
        principal=principal,
        resource=resource,
        tenant_id=tenant_id,
        trace_id=trace_id,
        meta={"classification": data_classification, "record_count": record_count},
    )


__all__ = [
    "AuditEvent",
    "audit_access",
    "audit_auth_failure",
    "audit_auth_success",
    "audit_data_access",
    "audit_event",
    "audit_model_usage",
    "audit_policy_decision",
    "audit_rate_limit",
]
