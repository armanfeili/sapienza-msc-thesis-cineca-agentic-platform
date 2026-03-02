"""
Service layer for built-in process management.

Provides business logic for:
- Merging runtime (Redis) and persistent (PostgreSQL) process state
- Process lifecycle operations (stop with idempotency)
- Audit trail querying with pagination
- Manifest activation history

Redis key structure:
- runtime:builtins:processes:live (Set) - active PIDs/process_ids
- runtime:builtins:process:{pid} (Hash) - per-process runtime metadata
- runtime:builtins:processes:recent (ZSet) - recently recorded processes by timestamp
- runtime:builtins:process:{pid}:stop-lock (String) - idempotency lock for stop operations
"""

from __future__ import annotations

import contextlib
import logging
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from db.postgres_control.models.builtin_process import (
    BuiltinManifestActivationHistory,
    BuiltinProcessEvent,
    ManifestStatus,
    ProcessEvent,
)
from db.redis_cache.client import get_redis
from src.adapters.llm import LLMAdapter

logger = logging.getLogger(__name__)

# Redis keyspace prefix
REDIS_PREFIX = "runtime:builtins:processes"
REDIS_LIVE_SET = f"{REDIS_PREFIX}:live"
REDIS_RECENT_ZSET = f"{REDIS_PREFIX}:recent"
REDIS_PROCESS_HASH_PREFIX = f"{REDIS_PREFIX}:process"
REDIS_STOP_LOCK_PREFIX = f"{REDIS_PREFIX}:process"

# Configuration
PROCESS_TTL_SECONDS = 120  # Sliding TTL for process hashes
STOP_LOCK_TTL_SECONDS = 30  # Lock duration for stop operations
RECENT_MAX_SIZE = 1000  # Max entries in recent ZSet
DEFAULT_LIMIT = 100
MAX_LIMIT = 1000


def _utc_now() -> datetime:
    """Return timezone-aware UTC timestamp."""
    return datetime.now(UTC)


def _now_unix() -> float:
    """Return current Unix timestamp."""
    return time.time()


# ---------------- Redis helpers ----------------
def _get_process_hash_key(pid: int | str) -> str:
    """Get Redis key for process hash."""
    return f"{REDIS_PROCESS_HASH_PREFIX}:{pid}"


def _get_stop_lock_key(pid: int | str) -> str:
    """Get Redis key for stop lock."""
    return f"{REDIS_STOP_LOCK_PREFIX}:{pid}:stop-lock"


def _get_runtime_processes() -> list[dict[str, Any]]:
    """
    Fetch all live processes from Redis.

    Returns:
        List of process dicts with runtime metadata
    """
    try:
        r = get_redis()
        live_pids = r.smembers(REDIS_LIVE_SET)
        processes = []

        for pid in live_pids:
            hash_key = _get_process_hash_key(pid)
            proc_data = r.hgetall(hash_key)
            if proc_data:
                # Convert types
                proc = dict(proc_data.items())
                # Parse numeric fields
                if "pid" in proc:
                    with contextlib.suppress(ValueError, TypeError):
                        proc["pid"] = int(proc["pid"])
                if "port" in proc:
                    with contextlib.suppress(ValueError, TypeError):
                        proc["port"] = int(proc["port"])
                # Check staleness
                last_heartbeat_str = proc.get("last_heartbeat")
                if last_heartbeat_str:
                    try:
                        last_heartbeat = float(last_heartbeat_str)
                        if _now_unix() - last_heartbeat > PROCESS_TTL_SECONDS:
                            proc["status"] = "stale"
                    except (ValueError, TypeError):
                        pass

                processes.append(proc)

        return processes
    except Exception as e:
        logger.warning(f"Failed to fetch runtime processes: {e}")
        return []


def _get_recent_processes(limit: int = 100) -> list[dict[str, Any]]:
    """
    Fetch recently recorded processes from Redis ZSet.

    Args:
        limit: Max number of recent processes to fetch

    Returns:
        List of process identifiers with scores (timestamps)
    """
    try:
        r = get_redis()
        # Get top N by score (timestamp) descending
        recent = r.zrevrange(REDIS_RECENT_ZSET, 0, limit - 1, withscores=True)
        return [{"process_id": pid, "ts": score} for pid, score in recent]
    except Exception as e:
        logger.warning(f"Failed to fetch recent processes: {e}")
        return []


def _acquire_stop_lock(pid: int | str, ttl: int = STOP_LOCK_TTL_SECONDS) -> bool:
    """
    Try to acquire a stop lock for idempotent process stopping.

    Args:
        pid: Process ID
        ttl: Lock TTL in seconds

    Returns:
        True if lock acquired, False if already locked
    """
    try:
        r = get_redis()
        lock_key = _get_stop_lock_key(pid)
        # SET NX (only if not exists) with TTL
        return bool(r.set(lock_key, "1", nx=True, ex=ttl))
    except Exception as e:
        logger.warning(f"Failed to acquire stop lock for {pid}: {e}")
        return False


def _release_stop_lock(pid: int | str) -> None:
    """Release stop lock."""
    try:
        r = get_redis()
        lock_key = _get_stop_lock_key(pid)
        r.delete(lock_key)
    except Exception:
        pass


def _remove_process_from_runtime(pid: int | str) -> None:
    """
    Remove process from runtime state (live set and hash).

    Args:
        pid: Process ID to remove
    """
    try:
        r = get_redis()
        r.srem(REDIS_LIVE_SET, str(pid))
        hash_key = _get_process_hash_key(pid)
        r.delete(hash_key)
    except Exception as e:
        logger.warning(f"Failed to remove process {pid} from runtime: {e}")


def _record_process_event(
    db: Session,
    process_id: str,
    artifact: str,
    event: ProcessEvent,
    pid: int | None = None,
    port: int | None = None,
    reason: str | None = None,
    exit_code: int | None = None,
    tenant_id: str | None = None,
    manifest_version: str | None = None,
    host: str | None = None,
) -> BuiltinProcessEvent:
    """
    Record a process lifecycle event to PostgreSQL.

    Args:
        db: Database session
        process_id: Stable process identifier
        artifact: Artifact name
        event: Event type
        pid: OS process ID
        port: Listening port
        reason: Event reason/context
        exit_code: Exit code for EXIT events
        tenant_id: Tenant identifier
        manifest_version: Manifest version
        host: Hostname/pod

    Returns:
        Created event record
    """
    event_record = BuiltinProcessEvent(
        process_id=process_id,
        artifact=artifact,
        pid=pid,
        port=port,
        event=event,
        reason=reason,
        exit_code=exit_code,
        tenant_id=tenant_id,
        manifest_version=manifest_version,
        host=host,
        ts=_utc_now(),
    )
    db.add(event_record)
    db.commit()
    db.refresh(event_record)
    return event_record


# ---------------- Public service functions ----------------
def list_processes(
    db: Session,
    limit: int = DEFAULT_LIMIT,
    artifact: str | None = None,
    status: str | None = None,
    since: datetime | None = None,
    tenant_id: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """
    List active and recently recorded built-in processes.

    Merges runtime state from Redis with persistent records from PostgreSQL.

    Args:
        db: Database session
        limit: Max results to return
        artifact: Filter by artifact name
        status: Filter by status
        since: Filter events after this timestamp
        tenant_id: Filter by tenant

    Returns:
        Tuple of (process list, next_cursor)
    """
    limit = min(limit, MAX_LIMIT)

    # 1. Get runtime processes
    runtime_procs = _get_runtime_processes()

    # 2. Get recent from Redis (non-active)
    _get_recent_processes(limit=RECENT_MAX_SIZE)

    # 3. Enrich/merge with PostgreSQL
    # Query for latest events per process to enrich
    query = db.query(BuiltinProcessEvent).order_by(desc(BuiltinProcessEvent.ts))

    if artifact:
        query = query.filter(BuiltinProcessEvent.artifact == artifact)
    if since:
        query = query.filter(BuiltinProcessEvent.ts >= since)
    if tenant_id:
        query = query.filter(BuiltinProcessEvent.tenant_id == tenant_id)

    db_events = query.limit(limit * 2).all()  # Fetch extra for merging

    # Build unified process list
    processes_map: dict[str, dict[str, Any]] = {}

    # Add runtime processes (highest priority)
    for proc in runtime_procs:
        proc_id = proc.get("process_id") or proc.get("id") or str(proc.get("pid"))
        processes_map[proc_id] = {
            "id": proc.get("id", proc_id),
            "process_id": proc_id,
            "artifact": proc.get("artifact", ""),
            "pid": proc.get("pid"),
            "port": proc.get("port"),
            "status": proc.get("status", "running"),
            "ts": datetime.fromtimestamp(float(proc.get("last_heartbeat", _now_unix())), tz=UTC),
            "tenant_id": proc.get("tenant_id"),
            "manifest_version": proc.get("manifest_version"),
            "host": proc.get("host"),
            "last_heartbeat": datetime.fromtimestamp(float(proc.get("last_heartbeat", _now_unix())), tz=UTC)
            if proc.get("last_heartbeat")
            else None,
        }

    # Add/enrich from PostgreSQL events
    for event in db_events:
        proc_id = event.process_id
        if proc_id not in processes_map:
            # New process from DB
            processes_map[proc_id] = {
                "id": proc_id,
                "process_id": proc_id,
                "artifact": event.artifact,
                "pid": event.pid,
                "port": event.port,
                "status": "exited" if event.event == ProcessEvent.EXIT else "stopped",
                "ts": event.ts,
                "tenant_id": event.tenant_id,
                "manifest_version": event.manifest_version,
                "host": event.host,
                "last_heartbeat": None,
            }
        else:
            # Enrich existing runtime process with DB data if missing
            proc = processes_map[proc_id]
            if not proc.get("manifest_version"):
                proc["manifest_version"] = event.manifest_version
            if not proc.get("tenant_id"):
                proc["tenant_id"] = event.tenant_id

    # Convert to list and apply filters
    processes = list(processes_map.values())

    if status:
        processes = [p for p in processes if p.get("status") == status]

    # Sort: running first, then by timestamp desc
    def sort_key(p):
        status_priority = 0 if p.get("status") == "running" else 1
        ts = p.get("ts") or datetime.min.replace(tzinfo=UTC)
        return (status_priority, -ts.timestamp())

    processes.sort(key=sort_key)

    # Apply limit and generate cursor
    next_cursor = None
    if len(processes) > limit:
        processes = processes[:limit]
        # Simple cursor: last timestamp
        last_ts = processes[-1].get("ts")
        if last_ts:
            next_cursor = last_ts.isoformat()

    return processes, next_cursor


def stop_process(
    db: Session,
    pid: int,
    actor: str,
) -> bool:
    """
    Stop a builtin process by PID (idempotent).

    Args:
        db: Database session
        pid: Operating system process ID
        actor: User or system identifier initiating stop

    Returns:
        True if stopped (or already gone), False if lock conflict

    Raises:
        HTTPException: On validation errors
    """
    # Acquire stop lock for idempotency
    if not _acquire_stop_lock(pid):
        # Already being stopped or recently stopped
        logger.info(f"Stop lock already held for PID {pid}, treating as idempotent success")
        return True

    try:
        # Check if process exists in runtime
        hash_key = _get_process_hash_key(pid)
        r = get_redis()
        proc_data = r.hgetall(hash_key)

        process_id = proc_data.get("process_id", f"pid:{pid}")
        artifact = proc_data.get("artifact", "unknown")

        # If not in runtime, check PostgreSQL
        if not proc_data:
            # Query for last event with this PID
            last_event = (
                db.query(BuiltinProcessEvent)
                .filter(BuiltinProcessEvent.pid == pid)
                .order_by(desc(BuiltinProcessEvent.ts))
                .first()
            )

            if last_event:
                process_id = last_event.process_id
                artifact = last_event.artifact
                # Already exited/stopped
                if last_event.event in (ProcessEvent.EXIT, ProcessEvent.STOP):
                    logger.info(f"Process {pid} already stopped/exited in DB, treating as idempotent")
                    return True

        # Attempt stop via adapter
        adapter = LLMAdapter()
        try:
            adapter.unload_model(str(pid))
            logger.info(f"Successfully unloaded process {pid}")
        except Exception as e:
            logger.warning(f"Failed to unload process {pid} via adapter: {e}")
            # Continue to record stop event even if adapter fails

        # Remove from runtime state
        _remove_process_from_runtime(pid)

        # Record stop event
        _record_process_event(
            db=db,
            process_id=process_id,
            artifact=artifact,
            event=ProcessEvent.STOP,
            pid=pid,
            reason=f"admin_stop_by_{actor}",
        )

        logger.info(f"Recorded stop event for process {pid}")
        return True

    finally:
        _release_stop_lock(pid)


def get_manifest_history(
    db: Session,
    limit: int = DEFAULT_LIMIT,
    manifest_name: str | None = None,
    status: ManifestStatus | None = None,
    since: datetime | None = None,
) -> tuple[list[BuiltinManifestActivationHistory], str | None]:
    """
    Get manifest activation history with pagination.

    Args:
        db: Database session
        limit: Max results
        manifest_name: Filter by manifest name
        status: Filter by status
        since: Filter after this timestamp

    Returns:
        Tuple of (records, next_cursor)
    """
    limit = min(limit, MAX_LIMIT)

    query = db.query(BuiltinManifestActivationHistory).order_by(desc(BuiltinManifestActivationHistory.activated_at))

    if manifest_name:
        query = query.filter(BuiltinManifestActivationHistory.manifest_name == manifest_name)
    if status:
        query = query.filter(BuiltinManifestActivationHistory.status == status)
    if since:
        query = query.filter(BuiltinManifestActivationHistory.activated_at >= since)

    # Fetch limit + 1 to check for next page
    records = query.limit(limit + 1).all()

    next_cursor = None
    if len(records) > limit:
        records = records[:limit]
        last_ts = records[-1].activated_at
        next_cursor = last_ts.isoformat()

    return records, next_cursor


def get_process_history(
    db: Session,
    limit: int = DEFAULT_LIMIT,
    artifact: str | None = None,
    pid: int | None = None,
    process_id: str | None = None,
    tenant_id: str | None = None,
    event: ProcessEvent | None = None,
    since: datetime | None = None,
) -> tuple[list[BuiltinProcessEvent], str | None]:
    """
    Get process lifecycle event history with pagination.

    Args:
        db: Database session
        limit: Max results
        artifact: Filter by artifact
        pid: Filter by PID
        process_id: Filter by process ID
        tenant_id: Filter by tenant
        event: Filter by event type
        since: Filter after this timestamp

    Returns:
        Tuple of (events, next_cursor)
    """
    limit = min(limit, MAX_LIMIT)

    query = db.query(BuiltinProcessEvent).order_by(desc(BuiltinProcessEvent.ts))

    if artifact:
        query = query.filter(BuiltinProcessEvent.artifact == artifact)
    if pid is not None:
        query = query.filter(BuiltinProcessEvent.pid == pid)
    if process_id:
        query = query.filter(BuiltinProcessEvent.process_id == process_id)
    if tenant_id:
        query = query.filter(BuiltinProcessEvent.tenant_id == tenant_id)
    if event:
        query = query.filter(BuiltinProcessEvent.event == event)
    if since:
        query = query.filter(BuiltinProcessEvent.ts >= since)

    # Fetch limit + 1 to check for next page
    events = query.limit(limit + 1).all()

    next_cursor = None
    if len(events) > limit:
        events = events[:limit]
        last_ts = events[-1].ts
        next_cursor = last_ts.isoformat()

    return events, next_cursor


__all__ = [
    "get_manifest_history",
    "get_process_history",
    "list_processes",
    "stop_process",
]
