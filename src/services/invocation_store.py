"""
Invocation Store
----------------
Persist and retrieve tool invocation results for POST/GET parity.

Design:
- Primary key: (tool name, event_id)
- Owner scoping: store owner subject (`owner_sub`) to enforce anti-enumeration
- Storage backends: Redis JSON with TTL; in-memory dict fallback with per-key TTL
- Values: the exact response body (dict) returned by POST `/v1/tools/{name}/invocations`

API:
- save_invocation(name, eid, owner_sub, body, ttl_s) -> bool
- load_invocation(name, eid) -> Optional[{"owner": str, "body": dict}]

Notes:
- We intentionally do not expose listing to avoid enumeration.
"""

from __future__ import annotations

import json
import time
from contextlib import suppress
from typing import Any

from db.redis_cache.client import cache_get_json, cache_set_json
from src.config import settings

_LOCAL: dict[str, tuple[str, float | None]] = {}


def _key(name: str, eid: str) -> str:
    return f"inv:{name}:{eid}"


def save_invocation(name: str, eid: str, owner_sub: str, body: dict[str, Any], ttl_s: int | None = None) -> bool:
    record = {"owner": owner_sub, "body": body}
    ttl = int(ttl_s or int(settings.RETENTION_DAYS) * 86400)
    key = _key(name, eid)
    # Try Redis first
    try:
        ok = cache_set_json(key, record, ex=ttl)
        if ok:
            return True
    except Exception:
        pass
    # Fallback to local in-memory store
    try:
        data = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        _LOCAL[key] = (data, time.time() + ttl if ttl else None)
        return True
    except Exception:
        return False


def load_invocation(name: str, eid: str) -> dict[str, Any] | None:
    key = _key(name, eid)
    # Try Redis first
    try:
        rec = cache_get_json(key)
        if isinstance(rec, dict) and "body" in rec and "owner" in rec:
            return rec  # type: ignore[return-value]
    except Exception:
        pass
    # Fallback to local
    entry = _LOCAL.get(key)
    if not entry:
        return None
    data, exp = entry
    if exp is not None and time.time() > exp:
        with suppress(Exception):
            _LOCAL.pop(key, None)
        return None
    try:
        rec = json.loads(data)
        if isinstance(rec, dict) and "body" in rec and "owner" in rec:
            return rec  # type: ignore[return-value]
    except Exception:
        return None
    return None


__all__ = ["load_invocation", "save_invocation"]
