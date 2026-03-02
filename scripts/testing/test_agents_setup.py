#!/usr/bin/env python3
"""
Test script for Agents API database migration and Redis helpers.

Run this after applying migration 008 to verify everything works.

Usage:
    python scripts/test_agents_setup.py
"""

import sys
import uuid
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_database_migration():
    """Test that agent tables were created successfully."""
    print("=" * 60)
    print("Testing Database Migration...")
    print("=" * 60)

    try:
        from db.postgres_control.database import get_db_context
        from db.postgres_control.models import AgentSession, AgentStep, AgentRun, IdempotencyKey
        from sqlalchemy import inspect

        with get_db_context() as db:
            inspector = inspect(db.bind)
            tables = inspector.get_table_names()

            required_tables = ["agent_sessions", "agent_steps", "agent_runs", "idempotency_keys"]

            print("\n✓ Checking for agent tables...")
            for table in required_tables:
                if table in tables:
                    print(f"  ✓ {table} exists")
                else:
                    print(f"  ✗ {table} MISSING!")
                    return False

            # Test creating a session
            print("\n✓ Testing session creation...")
            test_session = AgentSession(
                user_id="test-user",
                tenant_id="tenant-admin-root",
                status="active",
                temperature=0.2,
                max_steps=8,
                metadata={"test": True},
            )
            db.add(test_session)
            db.commit()
            print(f"  ✓ Created session: {test_session.session_id}")

            # Test creating a step
            print("\n✓ Testing step creation...")
            test_step = AgentStep(
                session_id=test_session.session_id, seq=1, type="user", message="Test message", status="queued"
            )
            db.add(test_step)
            db.commit()
            print(f"  ✓ Created step: {test_step.step_id} (seq={test_step.seq})")

            # Cleanup
            db.delete(test_step)
            db.delete(test_session)
            db.commit()
            print("  ✓ Cleaned up test data")

        print("\n" + "=" * 60)
        print("✅ Database migration test PASSED")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n❌ Database test FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_redis_helpers():
    """Test Redis agent helpers."""
    print("\n" + "=" * 60)
    print("Testing Redis Helpers...")
    print("=" * 60)

    try:
        from db.redis_cache.agents import (
            allocate_next_seq,
            session_lock,
            set_session_state,
            get_session_state,
            set_session_cancelled,
            is_session_cancelled,
            compute_list_etag,
        )

        test_session_id = uuid.uuid4()

        # Test sequence allocation
        print("\n✓ Testing sequence allocation...")
        seq1 = allocate_next_seq(test_session_id)
        seq2 = allocate_next_seq(test_session_id)
        seq3 = allocate_next_seq(test_session_id)
        assert seq1 == 1 and seq2 == 2 and seq3 == 3, "Sequences not sequential!"
        print(f"  ✓ Allocated sequences: {seq1}, {seq2}, {seq3}")

        # Test session lock
        print("\n✓ Testing distributed lock...")
        with session_lock(test_session_id, timeout=5):
            print("  ✓ Lock acquired successfully")
        print("  ✓ Lock released successfully")

        # Test session state cache
        print("\n✓ Testing session state cache...")
        state = {"status": "active", "last_seq": seq3, "heartbeat_ts": 1234567890.123}
        set_session_state(test_session_id, state, ttl=60)
        cached_state = get_session_state(test_session_id)
        assert cached_state == state, "Cached state doesn't match!"
        print(f"  ✓ Cached state: {cached_state}")

        # Test cancellation flag
        print("\n✓ Testing cancellation flag...")
        assert not is_session_cancelled(test_session_id), "Should not be cancelled"
        set_session_cancelled(test_session_id, ttl=60)
        assert is_session_cancelled(test_session_id), "Should be cancelled"
        print("  ✓ Cancellation flag works")

        # Test ETag computation
        print("\n✓ Testing ETag computation...")
        items = [{"id": 1}, {"id": 2}]
        etag = compute_list_etag("test-user", items)
        assert len(etag) == 32, "ETag should be MD5 hex (32 chars)"
        print(f"  ✓ Computed ETag: {etag}")

        print("\n" + "=" * 60)
        print("✅ Redis helpers test PASSED")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n❌ Redis test FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_schemas():
    """Test Pydantic schemas."""
    print("\n" + "=" * 60)
    print("Testing Pydantic Schemas...")
    print("=" * 60)

    try:
        from src.schemas.agents import (
            CreateSessionRequest,
            SessionResponse,
            CreateStepRequest,
            StepResponse,
            CreateRunRequest,
            RunResponse,
            ProblemDetail,
        )

        # Test session request
        print("\n✓ Testing CreateSessionRequest...")
        req = CreateSessionRequest(prompt="Test prompt", temperature=0.5, max_steps=10, tools=["tool1", "tool2"])
        assert req.temperature == 0.5
        print(f"  ✓ Valid request: temperature={req.temperature}, max_steps={req.max_steps}")

        # Test step request
        print("\n✓ Testing CreateStepRequest...")
        step_req = CreateStepRequest(type="user", message="Hello", input={"key": "value"})
        assert step_req.type == "user"
        print(f"  ✓ Valid step request: type={step_req.type}")

        # Test invalid step type
        print("\n✓ Testing validation...")
        try:
            invalid_step = CreateStepRequest(type="invalid", message="Test")
            print("  ✗ Should have raised validation error!")
            return False
        except Exception as e:
            print(f"  ✓ Validation works: {type(e).__name__}")

        # Test problem detail
        print("\n✓ Testing ProblemDetail...")
        problem = ProblemDetail(
            type="https://api.example.com/problems/not-found",
            title="Not Found",
            status=404,
            detail="The resource was not found",
            extensions={"correlation_id": "abc123"},
        )
        assert problem.status == 404
        print(f"  ✓ Problem detail: {problem.title}")

        print("\n" + "=" * 60)
        print("✅ Schema test PASSED")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n❌ Schema test FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 12 + "Agents API Setup Verification" + " " * 17 + "║")
    print("╚" + "=" * 58 + "╝")

    results = []

    # Run tests
    results.append(("Database Migration", test_database_migration()))
    results.append(("Redis Helpers", test_redis_helpers()))
    results.append(("Pydantic Schemas", test_schemas()))

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{name:.<40} {status}")
        if not passed:
            all_passed = False

    print("=" * 60)

    if all_passed:
        print("\n🎉 All tests PASSED! Agents API foundation is ready.")
        print("\nNext steps:")
        print("  1. Review docs/AGENTS_TODO_IMPLEMENTATION_PLAN.md")
        print("  2. Start implementing Phase 2 (Repository Layer)")
        return 0
    else:
        print("\n⚠️  Some tests FAILED. Please review the errors above.")
        print("\nTroubleshooting:")
        print("  - Ensure Docker containers are running: docker compose ps")
        print("  - Apply migration: cd db/postgres_control && alembic upgrade head")
        print("  - Check Redis: docker exec -it redis redis-cli PING")
        return 1


if __name__ == "__main__":
    sys.exit(main())
