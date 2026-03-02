"""
Regression tests for SQLAlchemy enum handling in builtin process tables.

Ensures that ProcessEvent and ManifestStatus enums correctly use lowercase
values (not names) when writing to PostgreSQL.
"""

import pytest
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from db.postgres_control.models.builtin_process import (
    BuiltinProcessEvent,
    BuiltinManifestActivationHistory,
    ProcessEvent,
    ManifestStatus,
)
from db.postgres_control.database import get_db


def test_process_event_enum_stores_lowercase_value():
    """Regression: Ensure ProcessEvent.STOP writes 'stop' (not 'STOP') to DB."""
    db: Session = next(get_db())

    try:
        # Create event using enum constant
        event = BuiltinProcessEvent(
            process_id="test_process_123",
            artifact="test-artifact",
            pid=99999,
            port=8080,
            event=ProcessEvent.STOP,  # Use enum, not string
            reason="test_regression",
            ts=datetime.now(timezone.utc),
        )

        db.add(event)
        db.commit()
        db.refresh(event)

        # Query back and verify stored value
        retrieved = db.query(BuiltinProcessEvent).filter_by(pid=99999).first()
        assert retrieved is not None
        assert retrieved.event == ProcessEvent.STOP
        assert retrieved.event.value == "stop"  # Lowercase in DB

        # Verify we can query by enum
        by_enum = (
            db.query(BuiltinProcessEvent)
            .filter(BuiltinProcessEvent.event == ProcessEvent.STOP)
            .filter_by(pid=99999)
            .first()
        )
        assert by_enum is not None

        # Cleanup
        db.delete(event)
        db.commit()

    finally:
        db.close()


def test_manifest_status_enum_stores_lowercase_value():
    """Regression: Ensure ManifestStatus.ACTIVE writes 'active' (not 'ACTIVE') to DB."""
    db: Session = next(get_db())

    try:
        # Create manifest history using enum constant
        manifest = BuiltinManifestActivationHistory(
            manifest_name="test-manifest",
            version="1.0.0",
            activated_at=datetime.now(timezone.utc),
            activated_by="test_user",
            status=ManifestStatus.ACTIVE,  # Use enum, not string
            notes="test_regression",
        )

        db.add(manifest)
        db.commit()
        db.refresh(manifest)

        # Query back and verify stored value
        retrieved = db.query(BuiltinManifestActivationHistory).filter_by(manifest_name="test-manifest").first()
        assert retrieved is not None
        assert retrieved.status == ManifestStatus.ACTIVE
        assert retrieved.status.value == "active"  # Lowercase in DB

        # Verify we can query by enum
        by_enum = (
            db.query(BuiltinManifestActivationHistory)
            .filter(BuiltinManifestActivationHistory.status == ManifestStatus.ACTIVE)
            .filter_by(manifest_name="test-manifest")
            .first()
        )
        assert by_enum is not None

        # Cleanup
        db.delete(manifest)
        db.commit()

    finally:
        db.close()


def test_all_process_events_are_writable():
    """Ensure all ProcessEvent enum values can be written to DB."""
    db: Session = next(get_db())

    events_to_test = [
        ProcessEvent.START,
        ProcessEvent.HEARTBEAT,
        ProcessEvent.STOP,
        ProcessEvent.EXIT,
        ProcessEvent.SIGNAL,
    ]

    created_ids = []

    try:
        for idx, event_type in enumerate(events_to_test):
            event = BuiltinProcessEvent(
                process_id=f"test_all_events_{idx}",
                artifact="test-artifact",
                pid=90000 + idx,
                event=event_type,
                ts=datetime.now(timezone.utc),
            )
            db.add(event)
            db.commit()
            db.refresh(event)
            created_ids.append(event.id)

            # Verify stored correctly
            assert event.event == event_type
            assert event.event.value in ["start", "heartbeat", "stop", "exit", "signal"]

        # Cleanup
        for event_id in created_ids:
            event = db.query(BuiltinProcessEvent).filter_by(id=event_id).first()
            if event:
                db.delete(event)
        db.commit()

    finally:
        db.close()


def test_all_manifest_statuses_are_writable():
    """Ensure all ManifestStatus enum values can be written to DB."""
    db: Session = next(get_db())

    statuses_to_test = [
        ManifestStatus.STAGED,
        ManifestStatus.ACTIVE,
        ManifestStatus.ROLLED_BACK,
        ManifestStatus.FAILED,
    ]

    created_ids = []

    try:
        for idx, status in enumerate(statuses_to_test):
            manifest = BuiltinManifestActivationHistory(
                manifest_name=f"test-manifest-{idx}",
                version="1.0.0",
                activated_at=datetime.now(timezone.utc),
                status=status,
            )
            db.add(manifest)
            db.commit()
            db.refresh(manifest)
            created_ids.append(manifest.id)

            # Verify stored correctly
            assert manifest.status == status
            assert manifest.status.value in ["staged", "active", "rolled_back", "failed"]

        # Cleanup
        for manifest_id in created_ids:
            manifest = db.query(BuiltinManifestActivationHistory).filter_by(id=manifest_id).first()
            if manifest:
                db.delete(manifest)
        db.commit()

    finally:
        db.close()
