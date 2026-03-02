"""
Session service: lightweight chat/session lifecycle with optional Redis backing.

Features
- Create/get/update/delete chat sessions
- Append messages (role/content) with timestamps & optional metadata
- Optional TTL and auto-expiration on read
- Pluggable persistence:
    • If RedisCache is available, store all sessions in one JSON blob key
    • Otherwise fall back to in-memory store (process local)
- Safe for async use (single-process) via an asyncio.Lock

Storage schema (Redis mode)
- Key: "{prefix}:sessions"  → JSON object { "<session_id>": <session_dict>, ... }

Notes
- This keeps the implementation simple and dependency-light; it is not optimized
  for very large numbers of sessions. Swap to hash/set-based indexing later if needed.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog

from src.services import ServiceBase, ServiceResult, utc_now

try:
    from db.redis_cache.client import RedisCache  # optional
except Exception:  # pragma: no cover - optional import
    RedisCache = None  # type: ignore[misc,assignment]

if TYPE_CHECKING:
    from db.redis_cache.client import RedisCache

try:
    from src.config import settings
except Exception:  # pragma: no cover - optional import
    settings = None  # type: ignore[misc,assignment]


log = structlog.get_logger(__name__)

DEFAULT_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days
MAX_MESSAGES_DEFAULT = 500
SESSION_STORE_KEY = "sessions"  # stored as "{prefix}:sessions" in Redis


# ──────────────────────────────────────────────────────────────────────────────
# Data models
# ──────────────────────────────────────────────────────────────────────────────
@dataclass(slots=True)
class ChatMessage:
    role: str  # "user" | "assistant" | "system" | "tool"
    content: str
    ts: str = field(default_factory=lambda: utc_now().isoformat())
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Session:
    id: str
    user_id: str | None = None
    tenant_id: str | None = None
    created_at: str = field(default_factory=lambda: utc_now().isoformat())
    updated_at: str = field(default_factory=lambda: utc_now().isoformat())
    expires_at: str | None = None
    title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    messages: list[ChatMessage] = field(default_factory=list)
    # Budget/counters (best-effort; not enforced here)
    tokens_in: int = 0
    tokens_out: int = 0
    turns: int = 0
    closed: bool = False
    max_messages: int = MAX_MESSAGES_DEFAULT

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # dataclasses.asdict already serializes nested dataclasses
        return d

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Session:
        msgs_in = data.get("messages") or []
        messages = [
            ChatMessage(
                role=m.get("role", "user"),
                content=m.get("content", ""),
                ts=m.get("ts") or utc_now().isoformat(),
                meta=dict(m.get("meta") or {}),
            )
            for m in msgs_in
        ]
        return cls(
            id=str(data.get("id")),
            user_id=data.get("user_id"),
            tenant_id=data.get("tenant_id"),
            created_at=data.get("created_at") or utc_now().isoformat(),
            updated_at=data.get("updated_at") or utc_now().isoformat(),
            expires_at=data.get("expires_at"),
            title=data.get("title"),
            metadata=dict(data.get("metadata") or {}),
            messages=messages,
            tokens_in=int(data.get("tokens_in") or 0),
            tokens_out=int(data.get("tokens_out") or 0),
            turns=int(data.get("turns") or 0),
            closed=bool(data.get("closed") or False),
            max_messages=int(data.get("max_messages") or MAX_MESSAGES_DEFAULT),
        )


# ──────────────────────────────────────────────────────────────────────────────
# Service implementation
# ──────────────────────────────────────────────────────────────────────────────
class SessionService(ServiceBase):
    """
    Manage chat sessions with optional Redis backing. All methods are async.

    This service stores all session objects in one key when using Redis for
    simplicity. For higher scale, replace with hash/set structures or a database.
    """

    def __init__(
        self,
        cache: Any | None = None,
        *,
        prefix: str | None = None,
        default_ttl_seconds: int | None = None,
        max_messages: int = MAX_MESSAGES_DEFAULT,
    ) -> None:
        super().__init__(name="session-service")
        self.cache = cache
        # Key prefix (if RedisCache provided, it also adds its own prefix)
        self.prefix = prefix or "cineca"
        self.default_ttl_seconds = int(
            default_ttl_seconds
            or (getattr(settings, "SESSION_TTL_SECONDS", None) if settings else None)
            or DEFAULT_TTL_SECONDS
        )
        self.max_messages_default = max_messages

        # In-memory fallback store (process-local)
        self._memstore: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

        log.info(
            "session.init",
            redis=bool(cache),
            ttl=self.default_ttl_seconds,
            max_messages=self.max_messages_default,
        )

    # Factory from env
    @classmethod
    def from_env(cls) -> SessionService:
        cache = None
        if RedisCache and settings:
            try:
                cache = RedisCache(
                    url=getattr(settings, "REDIS_URL", "redis://redis:6379/0"),
                    prefix=getattr(settings, "REDIS_PREFIX", "cineca"),
                    ttl_seconds=int(getattr(settings, "CACHE_TTL_SECONDS", 600)),
                )
            except Exception as exc:  # pragma: no cover
                log.warning("session.redis_unavailable", error=str(exc))
        return cls(cache=cache)

    # ──────────────────────────────────────────────────────────────────
    # Internal load/save helpers (store is a dict of session_id → session_dict)
    # ──────────────────────────────────────────────────────────────────
    async def _load_store(self) -> dict[str, dict[str, Any]]:
        if not self.cache:
            return dict(self._memstore)

        key = SESSION_STORE_KEY
        raw = await self.cache.get(key)  # type: ignore[union-attr]
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                return {}
            # ensure proper types
            return {str(k): dict(v) for k, v in data.items()}
        except Exception:  # pragma: no cover
            log.warning("session.store_parse_failed")
            return {}

    async def _save_store(self, store: dict[str, dict[str, Any]]) -> None:
        if not self.cache:
            self._memstore = dict(store)
            return
        # Redis mode: store per-session keys to avoid single large blob
        try:
            for sid, s in store.items():
                await self.cache.set(f"{SESSION_STORE_KEY}:{sid}", json.dumps(s, ensure_ascii=False), ex=self.default_ttl_seconds)  # type: ignore[union-attr]
        except Exception:
            # Fallback to whole-store if per-key fails
            key = SESSION_STORE_KEY
            await self.cache.set(key, json.dumps(store, ensure_ascii=False))  # type: ignore[union-attr]

    def _expired(self, sess: Mapping[str, Any]) -> bool:
        exp = sess.get("expires_at")
        if not exp:
            return False
        try:
            # Parse ISO8601 and compare to current UTC time
            return datetime.fromisoformat(exp) <= datetime.utcnow()
        except Exception:
            return True

    async def _purge_expired(self, store: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        to_delete = [sid for sid, s in store.items() if self._expired(s)]
        if to_delete:
            for sid in to_delete:
                store.pop(sid, None)
            await self._save_store(store)
        return store

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────
    async def create_session(
        self,
        *,
        user_id: str | None,
        tenant_id: str | None = None,
        title: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        ttl_seconds: int | None = None,
        max_messages: int | None = None,
        system_prompt: str | None = None,
    ) -> ServiceResult[dict[str, Any]]:
        async with self._lock:
            store = await self._load_store()
            await self._purge_expired(store)

            sid = str(uuid.uuid4())
            now = utc_now()
            ttl = int(ttl_seconds or self.default_ttl_seconds)
            expires_at = (now + timedelta(seconds=ttl)).isoformat()

            session = Session(
                id=sid,
                user_id=user_id,
                tenant_id=tenant_id,
                title=title,
                metadata=dict(metadata or {}),
                expires_at=expires_at,
                max_messages=int(max_messages or self.max_messages_default),
            )

            if system_prompt:
                session.messages.append(ChatMessage(role="system", content=system_prompt))

            store[sid] = session.to_dict()
            await self._save_store(store)

            log.info("session.created", session_id=sid, user_id=user_id, tenant_id=tenant_id)
            return ServiceResult.success(store[sid])

    async def get_session(self, session_id: str) -> ServiceResult[dict[str, Any]]:
        async with self._lock:
            store = await self._load_store()
            sess = store.get(session_id)
            if not sess:
                return ServiceResult.failure("Session not found", code="NOT_FOUND")
            # expire check
            if self._expired(sess):
                store.pop(session_id, None)
                await self._save_store(store)
                return ServiceResult.failure("Session expired", code="EXPIRED")
            return ServiceResult.success(sess)

    async def list_sessions(
        self,
        *,
        user_id: str | None = None,
        tenant_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ServiceResult[dict[str, Any]]:
        async with self._lock:
            store = await self._load_store()
            await self._purge_expired(store)

            sessions = list(store.values())
            if user_id:
                sessions = [s for s in sessions if s.get("user_id") == user_id]
            if tenant_id:
                sessions = [s for s in sessions if s.get("tenant_id") == tenant_id]

            # Sort by updated_at desc
            sessions.sort(key=lambda s: s.get("updated_at", ""), reverse=True)

            slice_ = sessions[offset : offset + limit]
            return ServiceResult.success({"items": slice_, "total": len(sessions), "limit": limit, "offset": offset})

    async def append_message(
        self,
        session_id: str,
        *,
        role: str,
        content: str,
        meta: Mapping[str, Any] | None = None,
        tokens_incr: int = 0,
        tokens_out_incr: int = 0,
    ) -> ServiceResult[dict[str, Any]]:
        if not content:
            return ServiceResult.failure("Message content is required", code="INVALID_INPUT")

        async with self._lock:
            store = await self._load_store()
            sess_d = store.get(session_id)
            if not sess_d:
                return ServiceResult.failure("Session not found", code="NOT_FOUND")
            if self._expired(sess_d):
                store.pop(session_id, None)
                await self._save_store(store)
                return ServiceResult.failure("Session expired", code="EXPIRED")
            if sess_d.get("closed"):
                return ServiceResult.failure("Session is closed", code="CLOSED")

            sess = Session.from_dict(sess_d)
            # Enforce max messages (drop oldest non-system if over limit)
            msg = ChatMessage(role=role, content=content, meta=dict(meta or {}))
            sess.messages.append(msg)
            if len(sess.messages) > int(sess.max_messages):
                # Prefer to keep system message if it exists
                # Drop from the left until within the limit
                kept: list[ChatMessage] = []
                system_msgs = [m for m in sess.messages if m.role == "system"]
                non_system = [m for m in sess.messages if m.role != "system"]
                # Keep one most recent system message if present
                keep_sys = system_msgs[-1:] if system_msgs else []
                remaining_slots = sess.max_messages - len(keep_sys)
                kept = keep_sys + non_system[-remaining_slots:]
                sess.messages = kept

            sess.tokens_in += int(tokens_incr or 0)
            sess.tokens_out += int(tokens_out_incr or 0)
            sess.turns += 1
            sess.updated_at = utc_now().isoformat()

            store[session_id] = sess.to_dict()
            await self._save_store(store)
            return ServiceResult.success(store[session_id])

    async def set_metadata(
        self,
        session_id: str,
        metadata: Mapping[str, Any],
        *,
        merge: bool = True,
    ) -> ServiceResult[dict[str, Any]]:
        async with self._lock:
            store = await self._load_store()
            sess_d = store.get(session_id)
            if not sess_d:
                return ServiceResult.failure("Session not found", code="NOT_FOUND")
            if self._expired(sess_d):
                store.pop(session_id, None)
                await self._save_store(store)
                return ServiceResult.failure("Session expired", code="EXPIRED")

            sess = Session.from_dict(sess_d)
            if merge:
                sess.metadata.update(dict(metadata or {}))
            else:
                sess.metadata = dict(metadata or {})
            sess.updated_at = utc_now().isoformat()

            store[session_id] = sess.to_dict()
            await self._save_store(store)
            return ServiceResult.success(store[session_id])

    async def close_session(self, session_id: str) -> ServiceResult[dict[str, Any]]:
        async with self._lock:
            store = await self._load_store()
            sess_d = store.get(session_id)
            if not sess_d:
                return ServiceResult.failure("Session not found", code="NOT_FOUND")
            sess = Session.from_dict(sess_d)
            sess.closed = True
            sess.updated_at = utc_now().isoformat()
            store[session_id] = sess.to_dict()
            await self._save_store(store)
            return ServiceResult.success(store[session_id])

    async def delete_session(self, session_id: str) -> ServiceResult[bool]:
        async with self._lock:
            store = await self._load_store()
            existed = store.pop(session_id, None) is not None
            await self._save_store(store)
            return ServiceResult.success(existed)

    async def renew_ttl(self, session_id: str, *, ttl_seconds: int | None = None) -> ServiceResult[dict[str, Any]]:
        async with self._lock:
            store = await self._load_store()
            sess_d = store.get(session_id)
            if not sess_d:
                return ServiceResult.failure("Session not found", code="NOT_FOUND")

            sess = Session.from_dict(sess_d)
            ttl = int(ttl_seconds or self.default_ttl_seconds)
            sess.expires_at = (utc_now() + timedelta(seconds=ttl)).isoformat()
            sess.updated_at = utc_now().isoformat()
            store[session_id] = sess.to_dict()
            await self._save_store(store)
            return ServiceResult.success(store[session_id])

    # Convenience helpers for extracting message windows
    async def get_messages(
        self, session_id: str, *, limit: int | None = None, include_system: bool = True
    ) -> ServiceResult[list[dict[str, Any]]]:
        res = await self.get_session(session_id)
        if not res.ok:
            return ServiceResult.failure(res.error or "Session not found", code=res.code)
        sess = res.data
        msgs = sess.get("messages", [])
        if not include_system:
            msgs = [m for m in msgs if (m.get("role") or "").lower() != "system"]
        if limit:
            msgs = msgs[-int(limit) :]
        return ServiceResult.success(msgs)
