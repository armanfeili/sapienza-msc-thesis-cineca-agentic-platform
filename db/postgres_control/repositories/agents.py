"""
Repository layer for agent sessions, steps, runs, and idempotency.

Provides CRUD operations with cursor-based pagination, ownership filtering,
and integration with Redis cache layer.
"""

from __future__ import annotations

import base64
import json
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, desc, or_
from sqlalchemy.orm import Session, load_only

from db.postgres_control.models import (
    AgentRun,
    AgentSession,
    AgentStep,
    IdempotencyKey,
)

# ============ Cursor Pagination Utilities ============


def encode_cursor(created_at: datetime, resource_id: UUID) -> str:
    """
    Encode pagination cursor as opaque base64 token.

    Args:
        created_at: Timestamp of the resource
        resource_id: UUID of the resource

    Returns:
        Base64-encoded cursor string
    """
    data = {"ts": created_at.isoformat(), "id": str(resource_id)}
    json_str = json.dumps(data, sort_keys=True)
    return base64.urlsafe_b64encode(json_str.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    """
    Decode pagination cursor.

    Args:
        cursor: Base64-encoded cursor string

    Returns:
        Tuple of (timestamp, resource_id)

    Raises:
        ValueError: If cursor is invalid
    """
    try:
        json_str = base64.urlsafe_b64decode(cursor.encode()).decode()
        data = json.loads(json_str)
        ts = datetime.fromisoformat(data["ts"])
        resource_id = UUID(data["id"])
        return ts, resource_id
    except Exception as exc:
        raise ValueError(f"Invalid cursor: {exc}")


# ============ Agent Session Repository ============


class AgentSessionRepository:
    """Repository for agent session operations."""

    @staticmethod
    def create(
        db: Session,
        *,
        session_id: UUID | None = None,
        user_id: str,
        tenant_id: str,
        status: str = "active",
        manager: str | None = None,
        preferred_workers: list[str] | None = None,
        llm_preferences: dict[str, str] | None = None,
        agent_role: str | None = None,
        tools: list[str] | None = None,
        temperature: float = 0.2,
        max_steps: int = 8,
        metadata: dict[str, Any] | None = None,
    ) -> AgentSession:
        """
        Create a new agent session.

        Args:
            db: Database session
            session_id: Optional client-provided session ID
            user_id: Owner user ID
            tenant_id: Tenant ID
            status: Initial status (default: active)
            manager: Manager/planner LLM name
            preferred_workers: List of preferred worker names
            llm_preferences: Tool -> LLM preferences
            agent_role: Agent role name
            tools: Allowed tool names
            temperature: Sampling temperature
            max_steps: Maximum steps allowed
            metadata: Additional metadata

        Returns:
            Created AgentSession instance
        """
        from datetime import datetime

        now = datetime.now(UTC)

        session = AgentSession(
            session_id=session_id,  # If None, DB will auto-generate
            user_id=user_id,
            tenant_id=tenant_id,
            status=status,
            manager=manager,
            preferred_workers=preferred_workers,
            llm_preferences=llm_preferences,
            agent_role=agent_role,
            tools=tools,
            temperature=temperature,
            max_steps=max_steps,
            session_metadata=metadata or {},
            created_at=now,
            updated_at=now,
        )
        session.update_etag()
        db.add(session)
        db.flush()  # Get the generated session_id
        return session

    @staticmethod
    def get_by_id(db: Session, session_id: UUID) -> AgentSession | None:
        """
        Get session by ID.

        Args:
            db: Database session
            session_id: Session UUID

        Returns:
            AgentSession or None if not found
        """
        return db.query(AgentSession).filter(AgentSession.session_id == session_id).first()

    @staticmethod
    def get_by_id_and_owner(
        db: Session,
        session_id: UUID,
        user_id: str,
    ) -> AgentSession | None:
        """
        Get session by ID with ownership check.

        Args:
            db: Database session
            session_id: Session UUID
            user_id: Expected owner user ID

        Returns:
            AgentSession or None if not found/not owned
        """
        return (
            db.query(AgentSession)
            .filter(
                and_(
                    AgentSession.session_id == session_id,
                    AgentSession.user_id == user_id,
                )
            )
            .first()
        )

    @staticmethod
    def list_by_user(
        db: Session,
        user_id: str,
        page_size: int = 20,
        page_token: str | None = None,
    ) -> tuple[list[AgentSession], str | None]:
        """
        List sessions for a user with cursor pagination.

        Args:
            db: Database session
            user_id: Owner user ID
            page_size: Number of items per page
            page_token: Opaque cursor for next page

        Returns:
            Tuple of (sessions list, next_page_token)
        """
        query = db.query(AgentSession).filter(AgentSession.user_id == user_id)

        # Apply cursor filter if provided
        if page_token:
            try:
                cursor_ts, cursor_id = decode_cursor(page_token)
                query = query.filter(
                    or_(
                        AgentSession.created_at < cursor_ts,
                        and_(
                            AgentSession.created_at == cursor_ts,
                            AgentSession.session_id < cursor_id,
                        ),
                    )
                )
            except ValueError:
                # Invalid cursor, ignore
                pass

        # Order by created_at DESC, session_id DESC for stable pagination
        query = query.order_by(
            desc(AgentSession.created_at),
            desc(AgentSession.session_id),
        )

        # Fetch one extra to determine if there's a next page
        items = query.limit(page_size + 1).all()

        has_more = len(items) > page_size
        sessions = items[:page_size]

        next_token = None
        if has_more and sessions:
            last = sessions[-1]
            next_token = encode_cursor(last.created_at, last.session_id)

        return sessions, next_token

    @staticmethod
    def list_all(
        db: Session,
        page_size: int = 20,
        page_token: str | None = None,
    ) -> tuple[list[AgentSession], str | None]:
        """
        List all sessions (admin view) with cursor pagination.

        Args:
            db: Database session
            page_size: Number of items per page
            page_token: Opaque cursor for next page

        Returns:
            Tuple of (sessions list, next_page_token)
        """
        query = db.query(AgentSession)

        if page_token:
            try:
                cursor_ts, cursor_id = decode_cursor(page_token)
                query = query.filter(
                    or_(
                        AgentSession.created_at < cursor_ts,
                        and_(
                            AgentSession.created_at == cursor_ts,
                            AgentSession.session_id < cursor_id,
                        ),
                    )
                )
            except ValueError:
                pass

        query = query.order_by(
            desc(AgentSession.created_at),
            desc(AgentSession.session_id),
        )

        items = query.limit(page_size + 1).all()
        has_more = len(items) > page_size
        sessions = items[:page_size]

        next_token = None
        if has_more and sessions:
            last = sessions[-1]
            next_token = encode_cursor(last.created_at, last.session_id)

        return sessions, next_token

    @staticmethod
    def update_status(
        db: Session,
        session_id: UUID,
        status: str,
    ) -> AgentSession | None:
        """
        Update session status.

        Args:
            db: Database session
            session_id: Session UUID
            status: New status

        Returns:
            Updated AgentSession or None if not found
        """
        session = AgentSessionRepository.get_by_id(db, session_id)
        if session:
            session.status = status
            session.update_etag()
            db.flush()
        return session

    @staticmethod
    def update_last_step(
        db: Session,
        session_id: UUID,
        step_id: UUID,
        step_seq: int | None = None,
    ) -> AgentSession | None:
        """
        Update session's last step reference.

        Args:
            db: Database session
            session_id: Session UUID
            step_id: Step UUID
            step_seq: Step sequence number

        Returns:
            Updated AgentSession or None if not found
        """
        session = AgentSessionRepository.get_by_id(db, session_id)
        if session:
            session.last_step_id = step_id
            if step_seq is not None:
                session.last_step_seq = step_seq
            session.update_etag()
            db.flush()
        return session

    @staticmethod
    def delete(db: Session, session_id: UUID) -> bool:
        """
        Delete a session (and cascade to steps/runs).

        Args:
            db: Database session
            session_id: Session UUID

        Returns:
            True if deleted, False if not found
        """
        session = AgentSessionRepository.get_by_id(db, session_id)
        if session:
            db.delete(session)
            db.flush()
            return True
        return False


# ============ Agent Step Repository ============


class AgentStepRepository:
    """Repository for agent step operations."""

    @staticmethod
    def create(
        db: Session,
        *,
        session_id: UUID,
        seq: int,
        type: str,
        message: str | None = None,
        tool: str | None = None,
        input: dict[str, Any] | None = None,
        output: dict[str, Any] | None = None,
        status: str = "queued",
        error: dict[str, Any] | None = None,
    ) -> AgentStep:
        """
        Create a new step.

        Args:
            db: Database session
            session_id: Parent session UUID
            seq: Sequence number (from Redis)
            type: Step type (user, assistant, tool, system, error)
            message: Human-readable message
            tool: Tool name if applicable
            input: Structured input
            output: Structured output
            status: Step status
            error: Error details if failed

        Returns:
            Created AgentStep instance
        """
        from datetime import datetime

        step = AgentStep(
            session_id=session_id,
            seq=seq,
            type=type,
            message=message,
            tool=tool,
            input=input,
            output=output,
            status=status,
            error=error,
            created_at=datetime.now(UTC),
        )
        db.add(step)
        db.flush()
        return step

    @staticmethod
    def get_by_id(db: Session, step_id: UUID) -> AgentStep | None:
        """Get step by ID."""
        return db.query(AgentStep).filter(AgentStep.step_id == step_id).first()

    @staticmethod
    def get_by_session_and_seq(
        db: Session,
        session_id: UUID,
        seq: int,
    ) -> AgentStep | None:
        """
        Get step by session and sequence number.

        Args:
            db: Database session
            session_id: Session UUID
            seq: Sequence number

        Returns:
            AgentStep or None
        """
        return (
            db.query(AgentStep)
            .filter(
                and_(
                    AgentStep.session_id == session_id,
                    AgentStep.seq == seq,
                )
            )
            .first()
        )

    @staticmethod
    def list_by_session(
        db: Session,
        session_id: UUID,
        page_size: int = 50,
        page_token: str | None = None,
    ) -> tuple[list[AgentStep], str | None]:
        """
        List steps for a session with cursor pagination (ASC order by seq).

        Args:
            db: Database session
            session_id: Session UUID
            page_size: Number of items per page
            page_token: Opaque cursor

        Returns:
            Tuple of (steps list, next_page_token)
        """
        query = db.query(AgentStep).filter(AgentStep.session_id == session_id)

        # For steps, we use seq as the cursor (simpler than timestamp)
        last_seq = 0
        if page_token:
            try:
                # Cursor is just the last seq number
                last_seq = int(page_token)
                query = query.filter(AgentStep.seq > last_seq)
            except ValueError:
                pass

        # Order by seq ASC for chronological order
        query = query.order_by(AgentStep.seq)

        items = query.limit(page_size + 1).all()
        has_more = len(items) > page_size
        steps = items[:page_size]

        next_token = None
        if has_more and steps:
            next_token = str(steps[-1].seq)

        return steps, next_token

    @staticmethod
    def update_status(
        db: Session,
        step_id: UUID,
        status: str,
        output: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
        completed_at: datetime | None = None,
    ) -> AgentStep | None:
        """
        Update step status and results.

        Args:
            db: Database session
            step_id: Step UUID
            status: New status
            output: Step output
            error: Error details
            completed_at: Completion timestamp

        Returns:
            Updated AgentStep or None
        """
        step = AgentStepRepository.get_by_id(db, step_id)
        if step:
            step.status = status
            if output is not None:
                step.output = output
            if error is not None:
                step.error = error
            if completed_at is not None:
                step.completed_at = completed_at
            db.flush()
        return step


# ============ Agent Run Repository ============


class AgentRunRepository:
    """Repository for agent run operations."""

    @staticmethod
    def create(
        db: Session,
        *,
        session_id: UUID | None = None,
        user_id: str,
        tenant_id: str,
        model: str | None = None,
        manager: str | None = None,
        latency_ms: int | None = None,
        trace_id: str | None = None,
        request_id: str | None = None,
        event_id: str | None = None,
        status: str = "running",
        # New model config fields (Task B.7)
        model_instance_name: str | None = None,
        model_id: str | None = None,
        provider_name: str | None = None,
        provider_id: str | None = None,
        config_source: str | None = None,
        # LLM error tracking fields (Task C.10)
        llm_error_type: str | None = None,
        llm_error_message: str | None = None,
        llm_error_occurred_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentRun:
        """
        Create a new run.

        Args:
            db: Database session
            session_id: Associated session UUID
            user_id: Owner user ID
            tenant_id: Tenant ID
            model: Model name used (legacy)
            manager: Manager name used
            latency_ms: Run latency
            trace_id: Provenance trace ID
            request_id: HTTP request ID for correlation
            event_id: Provenance event ID
            status: Run status
            model_instance_name: Human-readable instance name
            model_id: Provider-specific model ID
            provider_name: Provider name
            provider_id: Provider UUID
            config_source: Source of model config
            llm_error_type: Type of LLM error (timeout, context_length, etc.)
            llm_error_message: Detailed error message
            llm_error_occurred_at: Timestamp when error occurred
            metadata: Arbitrary metadata to persist with the run

        Returns:
            Created AgentRun instance
        """
        from datetime import datetime

        run = AgentRun(
            session_id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
            model=model,
            manager=manager,
            latency_ms=latency_ms,
            trace_id=trace_id,
            request_id=request_id,
            event_id=event_id,
            status=status,
            started_at=datetime.now(UTC),
            # New model config fields
            model_instance_name=model_instance_name,
            model_id=model_id,
            provider_name=provider_name,
            provider_id=provider_id,
            config_source=config_source,
            # LLM error tracking
            llm_error_type=llm_error_type,
            llm_error_message=llm_error_message,
            llm_error_occurred_at=llm_error_occurred_at,
            run_metadata=metadata or {},
        )
        db.add(run)
        db.flush()
        return run

    @staticmethod
    def get_by_id(db: Session, run_id: UUID) -> AgentRun | None:
        """Get run by ID."""
        return db.query(AgentRun).filter(AgentRun.run_id == run_id).first()

    @staticmethod
    def get_by_id_and_owner(
        db: Session,
        run_id: UUID,
        user_id: str,
    ) -> AgentRun | None:
        """Get run by ID with ownership check."""
        return (
            db.query(AgentRun)
            .filter(
                and_(
                    AgentRun.run_id == run_id,
                    AgentRun.user_id == user_id,
                )
            )
            .first()
        )

    @staticmethod
    def update_status(
        db: Session,
        run_id: UUID,
        status: str,
        latency_ms: int | None = None,
        finished_at: datetime | None = None,
        model: str | None = None,
        output: str | dict | list | None = None,  # Can be string, dict, or list (JSONB column)
        todos: list[dict[str, Any]] | None = None,
        steps: list[dict[str, Any]] | None = None,
        warnings: list[str] | None = None,
        trace_id: str | None = None,
        event_id: str | None = None,  # Provenance event ID (Issue #4)
        metrics: dict[str, Any] | None = None,  # Execution metrics (LLM, tools, etc.)
        # LLM error tracking fields (Task C.10)
        llm_error_type: str | None = None,
        llm_error_message: str | None = None,
        llm_error_occurred_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentRun | None:
        """
        Update run status and metrics.

        Args:
            db: Database session
            run_id: Run UUID
            status: New status
            latency_ms: Run latency
            finished_at: Finish timestamp
            model: Model name used
            output: Final output (object, list, or text - stored as JSONB)
            todos: List of TODO items from orchestration
            steps: List of execution steps from orchestration
            warnings: List of non-fatal warnings during execution
            trace_id: Trace/request ID for correlation
            event_id: Provenance event ID to persist (Issue #4)
            metrics: Execution metrics (overall_ms, llm, tools)
            llm_error_type: Type of LLM error (timeout, context_length, etc.)
            llm_error_message: Detailed error message
            llm_error_occurred_at: Timestamp when error occurred

        Returns:
            Updated AgentRun or None
        """
        run = AgentRunRepository.get_by_id(db, run_id)
        if run:
            # Debug: Log metrics parameter
            try:
                import structlog

                log = structlog.get_logger()
                log.info(
                    "repository.update_status.called",
                    run_id=str(run_id),
                    has_metrics=(metrics is not None),
                    metrics_type=type(metrics).__name__ if metrics else "None",
                )
            except Exception:
                # Logging is best-effort; never block persistence on logger issues
                pass
            
            run.status = status
            if latency_ms is not None:
                run.latency_ms = latency_ms
            if finished_at is not None:
                run.finished_at = finished_at
            if model is not None:
                run.model = model
            if output is not None:
                run.output = output
            if todos is not None:
                run.todos = todos
            if steps is not None:
                run.steps = steps
            if warnings is not None:
                run.warnings = warnings
            if trace_id is not None:
                run.trace_id = trace_id
            if event_id is not None:
                run.event_id = event_id  # Persist provenance event ID (Issue #4)
            if metrics is not None:
                run.metrics = metrics
            if metadata is not None:
                run.run_metadata = metadata
            # LLM error tracking (Task C.10)
            if llm_error_type is not None:
                run.llm_error_type = llm_error_type
            if llm_error_message is not None:
                run.llm_error_message = llm_error_message
            if llm_error_occurred_at is not None:
                run.llm_error_occurred_at = llm_error_occurred_at
            db.flush()
        return run

    @staticmethod
    def list_recent(
        db: Session,
        *,
        tenant_id: str | None = None,
        user_id: str | None = None,
        session_id: UUID | None = None,
        limit: int = 50,
    ) -> list[AgentRun]:
        """
        Fetch recent runs with ordering and limits to avoid long-running scans.

        Filters are optional; when provided they are combined to scope results.
        """
        query = db.query(AgentRun)
        if tenant_id:
            query = query.filter(AgentRun.tenant_id == tenant_id)
        if user_id:
            query = query.filter(AgentRun.user_id == user_id)
        if session_id:
            query = query.filter(AgentRun.session_id == session_id)
        query = query.options(
            load_only(
                AgentRun.run_id,
                AgentRun.session_id,
                AgentRun.user_id,
                AgentRun.tenant_id,
                AgentRun.status,
                AgentRun.started_at,
                AgentRun.finished_at,
                AgentRun.latency_ms,
            )
        )
        # Order newest first and bound result size
        query = query.order_by(desc(AgentRun.started_at)).limit(max(1, int(limit)))
        start_time = time.perf_counter()
        items = query.all()
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        if elapsed_ms > 200:  # basic health threshold for dev/CI
            try:
                import structlog

                log = structlog.get_logger()
                log.warning(
                    "repository.agent_runs.slow_list",
                    elapsed_ms=elapsed_ms,
                    limit=limit,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    session_id=str(session_id) if session_id else None,
                )
            except Exception:
                pass
        return items


# ============ Idempotency Repository ============


class IdempotencyRepository:
    """Repository for idempotency key operations."""

    @staticmethod
    def get_or_create(
        db: Session,
        key: str,
        owner_user_id: str,
        method: str,
        path: str,
        request_hash: str,
        response_hash: str,
        response_body: str | None = None,
        status_code: int = 200,
    ) -> tuple[IdempotencyKey, bool]:
        """
        Get existing idempotency key or create new one.

        Args:
            db: Database session
            key: Idempotency key
            owner_user_id: Owner user ID
            method: HTTP method
            path: Request path
            request_hash: Hash of request body
            response_hash: Hash of response body
            response_body: Full response body JSON
            status_code: HTTP status code to store (default 200)

        Returns:
            Tuple of (IdempotencyKey, created: bool)
        """
        existing = db.query(IdempotencyKey).filter(IdempotencyKey.key == key).first()

        if existing:
            return existing, False

        idem = IdempotencyKey(
            key=key,
            owner_user_id=owner_user_id,
            method=method,
            path=path,
            request_hash=request_hash,
            response_hash=response_hash,
            response_body=response_body,
            status_code=str(status_code),
        )
        db.add(idem)
        db.flush()
        return idem, True

    @staticmethod
    def mark_replayed(db: Session, key: str) -> IdempotencyKey | None:
        """
        Mark idempotency key as replayed.

        Args:
            db: Database session
            key: Idempotency key

        Returns:
            Updated IdempotencyKey or None
        """
        idem = db.query(IdempotencyKey).filter(IdempotencyKey.key == key).first()

        if idem:
            idem.replayed_at = datetime.now(UTC)
            db.flush()
        return idem


__all__ = [
    "AgentRunRepository",
    "AgentSessionRepository",
    "AgentStepRepository",
    "IdempotencyRepository",
    "decode_cursor",
    "encode_cursor",
]
