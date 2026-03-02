"""Singleton in-memory job store and SSE event ring buffers.

Provides a central place for job metadata and event buffering so multiple
FastAPI app instances in tests share the same objects (import-level singleton).

NOTE: This implementation is in-memory only and NOT suitable for multi-process
or multi-replica deployments. For production use, replace with a durable store
(e.g. Redis / database) and distributed pub/sub for events.
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any

__all__ = [
    "EVENT_BUFFER_MAX",
    "create_job_entry",
    "event_buffer",
    "get_events_since",
    "get_job",
    "job_expiry",
    "jobs",
    "record_event",
    "remove_job",
    "start_retention_cleaner",
]

# Core stores
jobs: dict[str, dict[str, Any]] = {}
job_expiry: dict[str, float] = {}
# In-memory ring buffer of recent SSE events per job_id
event_buffer: dict[str, list[dict[str, Any]]] = {}
EVENT_BUFFER_MAX = 100

_cleaner_started = False


def start_retention_cleaner(retention_days: int = 7):
    global _cleaner_started
    if _cleaner_started:
        return
    _cleaner_started = True
    max(1, retention_days * 86400)

    def _loop():
        while True:
            now = time.time()
            try:
                to_delete = [jid for jid, exp in list(job_expiry.items()) if exp <= now]
                for jid in to_delete:
                    jobs.pop(jid, None)
                    job_expiry.pop(jid, None)
                    event_buffer.pop(jid, None)
            except Exception:
                pass
            time.sleep(60)

    try:
        t = threading.Thread(target=_loop, name="job-retention-cleaner", daemon=True)
        t.start()
    except Exception:
        pass


def create_job_entry(subj: str, job_type: str, payload: dict[str, Any], tenant: str, retention_days: int) -> str:
    job_id = str(uuid.uuid4())
    created_at_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    ttl_seconds = max(1, retention_days * 86400)
    expires_at = time.time() + ttl_seconds
    jobs[job_id] = {
        "id": job_id,
        "status": "queued",
        "result": None,
        "owner_sub": subj,
        "type": job_type,
        "payload": payload,
        "created_at": created_at_iso,
        "metadata": {"tenant": tenant},
    }
    job_expiry[job_id] = expires_at
    return job_id


def get_job(job_id: str) -> dict[str, Any] | None:
    return jobs.get(job_id)


def remove_job(job_id: str):
    jobs.pop(job_id, None)
    job_expiry.pop(job_id, None)
    event_buffer.pop(job_id, None)


def record_event(job_id: str, ev_id: int, ev_type: str, payload: str):
    buf = event_buffer.setdefault(job_id, [])
    buf.append({"id": ev_id, "event": ev_type, "data": payload})
    if len(buf) > EVENT_BUFFER_MAX:
        del buf[: len(buf) - EVENT_BUFFER_MAX]


def get_events_since(job_id: str, last_seen: int) -> list[dict[str, Any]]:
    buf = event_buffer.get(job_id) or []
    return [e for e in buf if e.get("id", 0) > last_seen]
