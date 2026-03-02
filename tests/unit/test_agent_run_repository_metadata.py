"""
Unit tests for AgentRunRepository metadata round-trip.

Uses in-memory SQLite with JSON fallback to validate that request metadata
persists to the database and is exposed in RunResponse payloads.
"""

from __future__ import annotations

import sys
import sqlalchemy as sa
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.dialects import postgresql
from sqlalchemy import JSON

# Mock psycopg2 before any DB imports
sys.modules["psycopg2"] = Mock()

# Ensure database engine creation uses SQLite for tests
with patch("db.postgres_control.database.create_db_engine") as mock_engine:
    mock_engine.return_value = create_engine("sqlite:///:memory:")

    from db.postgres_control.database import Base
    from db.postgres_control.models.agent_run import AgentRun
    from db.postgres_control.models.tenant import Tenant
    from db.postgres_control.repositories.agents import AgentRunRepository
    from src.schemas.agents import RunResponse


@pytest.fixture(scope="function")
def db_session():
    """Create an in-memory SQLite database for AgentRun tests."""
    original_jsonb = postgresql.JSONB
    postgresql.JSONB = JSON  # SQLite fallback

    try:
        engine = create_engine("sqlite:///:memory:", echo=False)
        # Replace JSONB columns with SQLite-compatible JSON for this metadata instance
        from sqlalchemy import JSON as SQLITE_JSON
        for table in Base.metadata.tables.values():
            # Drop Postgres-specific defaults and constraints that SQLite can't parse
            to_remove = [
                c
                for c in list(table.constraints)
                if isinstance(c, sa.CheckConstraint) and "char_length" in str(c.sqltext).lower()
            ]
            for c in to_remove:
                table.constraints.discard(c)

            for column in table.columns:
                if isinstance(column.type, postgresql.JSONB):
                    column.type = SQLITE_JSON()
                if isinstance(column.type, postgresql.UUID):
                    column.type = sa.String(36)

                if column.server_default is not None:
                    default_text = str(getattr(column.server_default, "arg", column.server_default)).lower()
                    if "::" in default_text or "gen_random_uuid" in default_text:
                        column.server_default = None

                if hasattr(column, "server_onupdate") and column.server_onupdate is not None:
                    onupdate_text = str(getattr(column.server_onupdate, "arg", column.server_onupdate)).lower()
                    if "::" in onupdate_text or "gen_random_uuid" in onupdate_text:
                        column.server_onupdate = None

                # SQLite needs a Python-side default for UUID PKs once server defaults are stripped
                if table.name == "agent_runs" and column.name == "run_id" and column.default is None:
                    column.default = sa.schema.ColumnDefault(lambda: str(uuid4()))

        # Only create the tables required for AgentRun tests
        Base.metadata.create_all(engine, tables=[Tenant.__table__, AgentRun.__table__])

        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()

        # Seed required tenant (FK on agent_runs.tenant_id)
        tenant = Tenant(
            id="tenant-test",
            name="Tenant Test",
            admin_email="admin@test.com",
            metadata_={},
        )
        session.add(tenant)
        session.commit()

        yield session

        session.close()
        Base.metadata.drop_all(engine)
    finally:
        postgresql.JSONB = original_jsonb


@pytest.fixture
def repo(db_session: Session):
    return AgentRunRepository


def _fresh_run_kwargs(extra_metadata: dict | None = None) -> dict:
    return dict(
        session_id=None,
        user_id="user-123",
        tenant_id="tenant-test",
        model="phi3:mini",
        manager="phi3-mini",
        latency_ms=None,
        trace_id=str(uuid4()),
        request_id="req-123",
        event_id=None,
        status="running",
        model_instance_name="phi3-mini",
        model_id="phi3:mini",
        provider_name="ollama-local",
        provider_id=None,
        config_source="db_default",
        metadata=extra_metadata,
    )


def test_run_metadata_round_trip(repo, db_session: Session):
    """Metadata should persist to DB and show up in RunResponse payloads."""
    run = repo.create(db_session, **_fresh_run_kwargs({"memgraph_force_llm": True}))
    db_session.commit()

    stored = db_session.get(AgentRun, run.run_id)
    assert stored is not None
    assert stored.run_metadata == {"memgraph_force_llm": True}

    payload = stored.to_dict()
    assert payload["metadata"]["memgraph_force_llm"] is True

    response = RunResponse(**payload)
    assert response.metadata["memgraph_force_llm"] is True


def test_run_metadata_defaults_to_empty_dict(repo, db_session: Session):
    """When no metadata is provided, persisted metadata should be an empty dict."""
    run = repo.create(db_session, **_fresh_run_kwargs(None))
    db_session.commit()

    stored = db_session.get(AgentRun, run.run_id)
    assert stored is not None
    assert stored.run_metadata == {}

    payload = stored.to_dict()
    assert payload["metadata"] == {}
    response = RunResponse(**payload)
    assert response.metadata == {}


def test_update_status_preserves_metadata_when_unspecified(repo, db_session: Session):
    """Updating a run without metadata must not clear existing run_metadata."""
    run = repo.create(db_session, **_fresh_run_kwargs({"memgraph_force_llm": True}))
    db_session.commit()

    repo.update_status(
        db_session,
        run_id=run.run_id,
        status="succeeded",
        finished_at=datetime.now(timezone.utc),
        metadata=None,  # Explicitly omit metadata to ensure preservation
    )
    db_session.commit()

    stored = db_session.get(AgentRun, run.run_id)
    assert stored.run_metadata == {"memgraph_force_llm": True}

    # Overwrite with new metadata to confirm updates still work when provided
    repo.update_status(
        db_session,
        run_id=run.run_id,
        status="succeeded",
        finished_at=datetime.now(timezone.utc),
        metadata={"memgraph_force_llm": False},
    )
    db_session.commit()

    stored_after = db_session.get(AgentRun, run.run_id)
    assert stored_after.run_metadata == {"memgraph_force_llm": False}
