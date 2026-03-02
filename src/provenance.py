"""
Provenance & audit trail utilities.

Goals:
- Provide a lightweight, tamper-evident event log for requests, tool calls, and DB ops.
- Keep zero-DB dependency by default (in-memory), with optional Redis-backed append-only log.
- Be easy to use: one-shot `record_provenance(...)` or a context manager span.

Usage (one-shot):
    from src.provenance import provenance, record_provenance
    record_provenance(actor="api", action="tools.query", resource="/tools/query",
                      input={"cypher": "MATCH (n) RETURN count(n)"}, output={"count": 42})

Usage (context manager):
    from src.provenance import provenance_span
    with provenance_span(actor="api", action="agent.run", resource="/agent") as span:
        span.set_input({"prompt": "find X"})
        # ... do work ...
        span.set_output({"result": "..."})

Implementation notes:
- Each event includes SHA-256 hashes of input/output (canonical JSON) to avoid storing sensitive content directly.
- A chain hash is computed as sha256(prev_chain + event_core_hash) to make tampering evident.
- If Redis is available (REDIS_URL), events are also appended to a Redis list key (`prov:events`).
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from contextlib import suppress
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from .config import settings
from .utils.jsonable import to_jsonable

# Logging (structlog if configured, stdlib otherwise)
with suppress(Exception):
    from .logging_setup import get_logger  # type: ignore

    logger = get_logger(__name__)  # type: ignore[assignment]
if "logger" not in globals():
    import logging

    logger = logging.getLogger(__name__)

# Prometheus metrics (optional)
try:
    from prometheus_client import Counter, Histogram
except Exception:  # pragma: no cover
    Counter = None  # type: ignore
    Histogram = None  # type: ignore

if Counter is not None:
    PROV_EVENTS = Counter(
        "provenance_events_total",
        "Number of provenance events recorded",
        labelnames=("action", "actor", "success"),
    )
else:  # pragma: no cover
    PROV_EVENTS = None  # type: ignore

if Histogram is not None:
    PROV_DURATION = Histogram(
        "provenance_event_duration_seconds",
        "Duration of provenance spans",
        labelnames=("action",),
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, float("inf")),
    )
else:  # pragma: no cover
    PROV_DURATION = None  # type: ignore

# Redis (optional)
_redis = None
if settings.REDIS_URL:
    with suppress(Exception):
        import redis  # type: ignore

        _redis = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


# ---------------- Helpers ----------------
def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _canonical(obj: Any) -> str:
    """Serialize to canonical JSON string (sorted keys, no spaces)."""
    return json.dumps(
        to_jsonable(obj),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _sha256_hex(data: Any) -> str:
    import hashlib

    if isinstance(data, (bytes, bytearray)):
        b = bytes(data)
    elif isinstance(data, str):
        b = data.encode("utf-8")
    else:
        b = _canonical(data).encode("utf-8")
    return hashlib.sha256(b).hexdigest()


def _scrub_meta(meta: dict[str, Any] | None) -> dict[str, Any]:
    """Drop obviously sensitive keys and shrink large values."""
    if not meta:
        return {}
    SENSITIVE = {"password", "authorization", "auth", "token", "secret", "api_key", "apikey"}
    cleaned: dict[str, Any] = {}
    for k, v in meta.items():
        lk = str(k).lower()
        if lk in SENSITIVE:
            cleaned[k] = "***"
            continue
        # Truncate long strings
        if isinstance(v, str) and len(v) > 512:
            cleaned[k] = v[:512] + "…"
        else:
            cleaned[k] = v
    return cleaned


# ---------------- Data model ----------------
@dataclass(slots=True)
class ProvenanceEvent:
    event_id: str
    ts: datetime
    actor: str
    action: str
    resource: str | None
    trace_id: str
    parent_id: str | None
    success: bool
    error: str | None
    duration_ms: int | None
    input_hash: str | None
    output_hash: str | None
    meta: dict[str, Any] = field(default_factory=dict)
    prev_chain: str | None = None
    chain: str | None = None  # filled by store

    def to_core_dict(self) -> dict[str, Any]:
        """Subset used for chain hashing (exclude prev_chain/chain)."""
        d = asdict(self)
        d.pop("prev_chain", None)
        d.pop("chain", None)
        # Serialize datetime as ISO for stability
        d["ts"] = self.ts.isoformat()
        return d

    def to_json(self) -> str:
        d = asdict(self)
        d["ts"] = self.ts.isoformat()
        return _canonical(d)


# ---------------- Stores ----------------
class _BaseStore:
    def append(self, ev: ProvenanceEvent) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def last_chain(self) -> str | None:  # pragma: no cover - interface
        raise NotImplementedError


class MemoryStore(_BaseStore):
    """In-memory append-only store with chain hashing."""

    def __init__(self) -> None:
        self._events: list[ProvenanceEvent] = []
        self._lock = threading.Lock()
        self._last_chain: str | None = None

    def append(self, ev: ProvenanceEvent) -> None:
        with self._lock:
            ev.prev_chain = self._last_chain
            core_hash = _sha256_hex(ev.to_core_dict())
            chain_input = (self._last_chain or "") + core_hash
            ev.chain = _sha256_hex(chain_input)
            self._events.append(ev)
            self._last_chain = ev.chain

    def last_chain(self) -> str | None:
        with self._lock:
            return self._last_chain

    # Convenience for tests / debugging
    def dump(self) -> list[ProvenanceEvent]:
        with self._lock:
            return list(self._events)


class RedisStore(_BaseStore):
    """Redis-backed append-only log using LPUSH on a list key.

    Keys:
      - prov:events   -> JSON lines (LPUSH newest first)
      - prov:last     -> last chain hash
    """

    def __init__(self, client, key_events: str = "prov:events", key_last: str = "prov:last") -> None:
        self._r = client
        self._key_events = key_events
        self._key_last = key_last

    def append(self, ev: ProvenanceEvent) -> None:
        pipe = self._r.pipeline()
        last = self._r.get(self._key_last)
        ev.prev_chain = last
        core_hash = _sha256_hex(ev.to_core_dict())
        chain_input = (last or "") + core_hash
        ev.chain = _sha256_hex(chain_input)
        pipe.lpush(self._key_events, ev.to_json())
        pipe.set(self._key_last, ev.chain)
        pipe.execute()

    def last_chain(self) -> str | None:
        return self._r.get(self._key_last)


# ---------------- Provenance manager ----------------
class Provenance:
    def __init__(self) -> None:
        # Choose Redis if available; fall back to memory
        if _redis is not None:
            try:
                # simple ping to validate
                _redis.ping()
                self.store: _BaseStore = RedisStore(_redis)
                logger.info("provenance store: redis", url=settings.REDIS_URL)
            except Exception:
                logger.warning("redis not available, using in-memory provenance store")
                self.store = MemoryStore()
        else:
            self.store = MemoryStore()

    def record(
        self,
        *,
        actor: str,
        action: str,
        resource: str | None = None,
        input: Any | None = None,  # noqa: A002 - shadow builtin is fine here
        output: Any | None = None,
        meta: dict[str, Any] | None = None,
        trace_id: str | None = None,
        parent_id: str | None = None,
        success: bool = True,
        error: str | None = None,
        duration_ms: int | None = None,
    ) -> ProvenanceEvent:
        ev = ProvenanceEvent(
            event_id=str(uuid.uuid4()),
            ts=_utcnow(),
            actor=str(actor),
            action=str(action),
            resource=str(resource) if resource else None,
            trace_id=trace_id or str(uuid.uuid4()),
            parent_id=parent_id,
            success=bool(success),
            error=str(error) if error else None,
            duration_ms=duration_ms,
            input_hash=_sha256_hex(input) if input is not None else None,
            output_hash=_sha256_hex(output) if output is not None else None,
            meta=_scrub_meta(meta),
        )
        self.store.append(ev)

        # Metrics (best-effort)
        if PROV_EVENTS is not None:
            try:
                PROV_EVENTS.labels(action=ev.action, actor=ev.actor, success=str(ev.success)).inc()
            except Exception:  # pragma: no cover
                pass

        logger.debug(
            "provenance event",
            event_id=ev.event_id,
            action=ev.action,
            actor=ev.actor,
            trace_id=ev.trace_id,
            success=ev.success,
        )
        return ev

    # Context manager API
    def span(
        self,
        *,
        actor: str,
        action: str,
        resource: str | None = None,
        meta: dict[str, Any] | None = None,
        trace_id: str | None = None,
        parent_id: str | None = None,
    ) -> ProvenanceSpan:
        return ProvenanceSpan(
            mgr=self,
            actor=actor,
            action=action,
            resource=resource,
            meta=meta or {},
            trace_id=trace_id,
            parent_id=parent_id,
        )


class ProvenanceSpan:
    """Context manager that records a single event on exit with duration and hashes."""

    def __init__(
        self,
        *,
        mgr: Provenance,
        actor: str,
        action: str,
        resource: str | None,
        meta: dict[str, Any],
        trace_id: str | None,
        parent_id: str | None,
    ) -> None:
        self._mgr = mgr
        self.actor = actor
        self.action = action
        self.resource = resource
        self._meta = meta
        self._trace_id = trace_id
        self._parent_id = parent_id

        self._input: Any | None = None
        self._output: Any | None = None
        self._start_ns: int | None = None
        self._success = True
        self._error: str | None = None

    def __enter__(self) -> ProvenanceSpan:
        self._start_ns = time.monotonic_ns()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc is not None:
            self._success = False
            self._error = f"{exc_type.__name__}: {exc}"
        dur_ms = None
        if self._start_ns is not None:
            dur_ms = int((time.monotonic_ns() - self._start_ns) / 1_000_000)

        self._mgr.record(
            actor=self.actor,
            action=self.action,
            resource=self.resource,
            input=self._input,
            output=self._output,
            meta=self._meta,
            trace_id=self._trace_id,
            parent_id=self._parent_id,
            success=self._success,
            error=self._error,
            duration_ms=dur_ms,
        )

        # Metrics: duration
        if PROV_DURATION is not None and dur_ms is not None:
            with suppress(Exception):  # pragma: no cover
                PROV_DURATION.labels(action=self.action).observe(dur_ms / 1000.0)

        # Do not suppress exceptions
        return False

    # Mutators during the span
    def set_input(self, value: Any) -> None:
        self._input = value

    def set_output(self, value: Any) -> None:
        self._output = value

    def add_meta(self, **kwargs: Any) -> None:
        self._meta.update(kwargs)


# ------------- Convenience top-level API -------------
provenance = Provenance()


def record_provenance(
    *,
    actor: str,
    action: str,
    resource: str | None = None,
    input: Any | None = None,  # noqa: A002
    output: Any | None = None,
    meta: dict[str, Any] | None = None,
    trace_id: str | None = None,
    parent_id: str | None = None,
    success: bool = True,
    error: str | None = None,
    duration_ms: int | None = None,
) -> ProvenanceEvent:
    """One-shot helper.

    Constructs a ProvenanceEvent using canonical hashes for input/output
    instead of embedding full payloads (the dataclass stores hashes).
    """
    ev = ProvenanceEvent(
        event_id=str(uuid.uuid4()),
        ts=_utcnow(),
        actor=str(actor),
        action=str(action),
        resource=str(resource) if resource else None,
        trace_id=trace_id or str(uuid.uuid4()),
        parent_id=parent_id,
        success=bool(success),
        error=str(error) if error else None,
        duration_ms=duration_ms,
        input_hash=_sha256_hex(input) if input is not None else None,
        output_hash=_sha256_hex(output) if output is not None else None,
        meta=_scrub_meta(meta or {}),
    )

    # Augment meta with manager/assignee fields if present
    try:
        mgr = (meta or {}).get("manager")
        assignee = (meta or {}).get("assignee")
        if mgr:
            ev.meta["manager"] = mgr
        if assignee:
            ev.meta["assignee"] = assignee
    except Exception:
        pass

    provenance.store.append(ev)

    # Metrics (best-effort)
    if PROV_EVENTS is not None:
        try:
            PROV_EVENTS.labels(action=ev.action, actor=ev.actor, success=str(ev.success)).inc()
        except Exception:  # pragma: no cover
            pass

    logger.debug(
        "provenance event",
        event_id=ev.event_id,
        action=ev.action,
        actor=ev.actor,
        trace_id=ev.trace_id,
        success=ev.success,
    )
    return ev


def provenance_span(
    *,
    actor: str,
    action: str,
    resource: str | None = None,
    meta: dict[str, Any] | None = None,
    trace_id: str | None = None,
    parent_id: str | None = None,
) -> ProvenanceSpan:
    """Context manager factory."""
    return provenance.span(
        actor=actor,
        action=action,
        resource=resource,
        meta=meta or {},
        trace_id=trace_id,
        parent_id=parent_id,
    )


__all__ = [
    "MemoryStore",
    "Provenance",
    "ProvenanceEvent",
    "RedisStore",
    "provenance",
    "provenance_span",
    "record_provenance",
]
