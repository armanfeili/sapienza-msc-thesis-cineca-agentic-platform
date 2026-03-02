"""In-memory fallback store for agent sessions when PostgreSQL is unavailable."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import RLock
from typing import Any
from uuid import UUID

try:  # pragma: no cover - logging setup optional during tests
    from src.logging_setup import get_logger  # type: ignore

    logger = get_logger(__name__)  # type: ignore[assignment]
except Exception:  # pragma: no cover - fallback to stdlib logging
    logger = logging.getLogger(__name__)

_DB_ERROR_TYPES: tuple[type[BaseException], ...] = ()
try:  # pragma: no cover - import depends on optional extras
    from sqlalchemy.exc import OperationalError as _SAOperationalError

    _DB_ERROR_TYPES += (_SAOperationalError,)
except Exception:  # pragma: no cover - SQLAlchemy missing during linting
    pass

try:  # pragma: no cover - psycopg optional in certain profiles
    from psycopg2 import OperationalError as _PsycopgOperationalError  # type: ignore

    _DB_ERROR_TYPES += (_PsycopgOperationalError,)
except Exception:  # pragma: no cover - psycopg not installed in some envs
    pass

_CONNECTION_ERROR_SUBSTRINGS = (
    "could not translate host name",
    "connection refused",
    "server closed the connection",
    "timeout",
    "name or service not known",
    "could not connect to server",
)


@dataclass
class LocalAgentSession:
    """Minimal representation of an agent session for fallback responses."""

    session_id: UUID
    user_id: str
    tenant_id: str
    status: str = "active"
    manager: str | None = None
    preferred_workers: list[str] | None = None
    llm_preferences: dict[str, str] | None = None
    agent_role: str | None = None
    tools: list[str] | None = None
    temperature: float = 0.2
    max_steps: int = 8
    session_metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_step_id: UUID | None = None
    last_step_seq: int | None = None
    etag: str | None = None

    def update_etag(self) -> None:
        updated_str = self.updated_at.isoformat()
        payload = f"{self.session_id}:{self.status}:{updated_str}"
        self.etag = hashlib.md5(payload.encode(), usedforsecurity=False).hexdigest()


class SessionFallbackStore:
    """Process-local fallback cache for agent sessions."""

    _sessions: dict[str, LocalAgentSession] = {}
    _lock: RLock = RLock()
    _db_available: bool = True
    _warning_emitted: bool = False

    @classmethod
    def is_db_available(cls) -> bool:
        return cls._db_available

    @classmethod
    def mark_db_unavailable(cls, exc: Exception | None = None) -> None:
        if cls._db_available:
            cls._db_available = False
            if not cls._warning_emitted:
                logger.warning(
                    "PostgreSQL unavailable for session persistence; using in-memory fallback",
                    extra={"error": str(exc) if exc else None},
                )
                cls._warning_emitted = True

    @classmethod
    def should_use_fallback(cls, exc: Exception | None = None) -> bool:
        if exc and _DB_ERROR_TYPES and isinstance(exc, _DB_ERROR_TYPES):
            return True
        message = str(exc).lower() if exc else ""
        return any(token in message for token in _CONNECTION_ERROR_SUBSTRINGS)

    @classmethod
    @staticmethod
    def _normalize_session_id(session_id: UUID | str) -> UUID:
        if isinstance(session_id, UUID):
            return session_id
        return UUID(str(session_id))

    @classmethod
    def create(
        cls,
        *,
        session_id: UUID | str,
        user_id: str,
        tenant_id: str,
        manager: str | None,
        tools: list[str] | None,
        temperature: float,
        max_steps: int,
        metadata: dict[str, Any],
    ) -> LocalAgentSession:
        session_uuid = cls._normalize_session_id(session_id)

        record = LocalAgentSession(
            session_id=session_uuid,
            user_id=user_id,
            tenant_id=tenant_id,
            manager=manager,
            tools=tools,
            temperature=temperature,
            max_steps=max_steps,
            session_metadata=metadata or {},
        )
        record.update_etag()
        with cls._lock:
            cls._sessions[str(session_uuid)] = record
        return record

    @classmethod
    def get(cls, session_id: UUID | str) -> LocalAgentSession | None:
        normalized = cls._normalize_session_id(session_id)
        with cls._lock:
            return cls._sessions.get(str(normalized))

    @classmethod
    def get_for_owner(cls, session_id: UUID | str, user_id: str) -> LocalAgentSession | None:
        record = cls.get(session_id)
        if record and record.user_id == user_id:
            return record
        return None