"""
Migration verification script for builtin process tables.

Ensures:
- processevent enum exists with all required values
- manifeststatus enum exists with all required values  
- Tables exist with correct schema
- Indexes are present
"""

import sys
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker

# Connection string - use environment variable or default
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://cineca_user:change_me_now@localhost:5432/cineca_platform")


def verify_enum(engine, enum_name: str, expected_values: list[str]) -> bool:
    """Verify PostgreSQL enum exists and has expected values."""
    with engine.connect() as conn:
        result = conn.execute(text(f"SELECT unnest(enum_range(NULL::{enum_name}))::text"))
        actual_values = {row[0] for row in result}
        expected = set(expected_values)

        if actual_values != expected:
            print(f"❌ Enum '{enum_name}' has incorrect values!")
            print(f"   Expected: {expected}")
            print(f"   Actual:   {actual_values}")
            print(f"   Missing:  {expected - actual_values}")
            print(f"   Extra:    {actual_values - expected}")
            return False

        print(f"✅ Enum '{enum_name}' OK: {sorted(actual_values)}")
        return True


def verify_table_exists(inspector, table_name: str) -> bool:
    """Verify table exists."""
    if table_name not in inspector.get_table_names():
        print(f"❌ Table '{table_name}' does not exist!")
        return False
    print(f"✅ Table '{table_name}' exists")
    return True


def verify_indexes(inspector, table_name: str, expected_index_patterns: list[str]) -> bool:
    """Verify required indexes exist on table (checks for pattern matches)."""
    indexes = inspector.get_indexes(table_name)
    index_names = {idx["name"] for idx in indexes}

    # Check if each pattern matches at least one index
    missing_patterns = []
    for pattern in expected_index_patterns:
        # Match if any index name contains the pattern
        if not any(pattern in idx_name for idx_name in index_names):
            missing_patterns.append(pattern)

    if missing_patterns:
        print(f"⚠️  Table '{table_name}' missing indexes matching: {missing_patterns}")
        print(f"   Present indexes: {sorted(index_names)}")
        return False

    print(f"✅ Table '{table_name}' has all required index patterns")
    return True


def main():
    print("=" * 70)
    print("Builtin Process Tables Migration Verification")
    print("=" * 70)
    print()

    try:
        engine = create_engine(DATABASE_URL)
        inspector = inspect(engine)

        all_ok = True

        # Verify enums
        print("📋 Checking PostgreSQL enums...")
        all_ok &= verify_enum(engine, "processevent", ["start", "heartbeat", "stop", "exit", "signal"])
        all_ok &= verify_enum(engine, "manifeststatus", ["staged", "active", "rolled_back", "failed"])
        print()

        # Verify tables
        print("📋 Checking tables...")
        all_ok &= verify_table_exists(inspector, "builtin_process_events")
        all_ok &= verify_table_exists(inspector, "builtin_manifest_activation_history")
        print()

        # Verify indexes on builtin_process_events
        print("📋 Checking indexes on builtin_process_events...")
        all_ok &= verify_indexes(
            inspector,
            "builtin_process_events",
            [
                "ts",  # Matches ix_builtin_process_events_ts or ix_builtin_process_ts
                "artifact",  # Matches indexes with artifact
                "pid",  # Matches indexes with pid
                "process_id",  # Matches indexes with process_id
                "tenant_id",  # Matches indexes with tenant_id
            ],
        )
        print()

        # Verify indexes on builtin_manifest_activation_history
        print("📋 Checking indexes on builtin_manifest_activation_history...")
        all_ok &= verify_indexes(
            inspector,
            "builtin_manifest_activation_history",
            [
                "manifest_name",  # Matches indexes with manifest_name
                "activated_at",  # Matches indexes with activated_at
                "status",  # Matches indexes with status
            ],
        )
        print()

        print("=" * 70)
        if all_ok:
            print("✅ All migration checks PASSED")
            print("=" * 70)
            return 0
        else:
            print("❌ Some migration checks FAILED")
            print("=" * 70)
            return 1

    except Exception as e:
        print(f"❌ Error during verification: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
