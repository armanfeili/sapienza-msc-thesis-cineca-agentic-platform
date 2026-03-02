#!/usr/bin/env python3
"""
Seed demo tenant data into PostgreSQL.

Creates a few example tenants for local development and testing.
Safe to run multiple times (idempotent).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from db.postgres_control.database import get_db_context
from db.postgres_control.repositories.tenants import TenantsRepository


def seed_demo_tenants():
    """Create demo tenants in the database."""

    demo_tenants = [
        {
            "name": "Admin Root Tenant",
            "admin_email": "admin@cineca.platform",
            "metadata": {"role": "system", "tier": "admin", "description": "Default administrative tenant"},
        },
        {
            "name": "ACME Corporation",
            "admin_email": "admin@acme.com",
            "metadata": {"region": "us-east-1", "tier": "premium", "industry": "technology"},
        },
        {
            "name": "Beta Test Tenant",
            "admin_email": "beta@example.com",
            "metadata": {"region": "eu-west-1", "tier": "standard", "pilot_program": True},
        },
        {
            "name": "Research Lab",
            "admin_email": "lab@university.edu",
            "metadata": {"region": "us-west-2", "tier": "academic", "department": "AI Research"},
        },
    ]

    print("🌱 Seeding demo tenants into PostgreSQL...")

    with get_db_context() as db:
        repo = TenantsRepository(db)

        created_count = 0
        existing_count = 0

        for tenant_data in demo_tenants:
            try:
                tenant, was_created = repo.create(
                    name=tenant_data["name"], admin_email=tenant_data["admin_email"], metadata=tenant_data["metadata"]
                )

                if was_created:
                    print(f"  ✅ Created: {tenant.name} (ID: {tenant.id})")
                    created_count += 1
                else:
                    print(f"  ♻️  Exists:  {tenant.name} (ID: {tenant.id})")
                    existing_count += 1

            except ValueError as e:
                print(f"  ❌ Error creating '{tenant_data['name']}': {e}")
                continue

    print("\n📊 Summary:")
    print(f"  • Created: {created_count}")
    print(f"  • Already existed: {existing_count}")
    print(f"  • Total: {created_count + existing_count}")
    print("\n✨ Seeding complete!")


if __name__ == "__main__":
    try:
        seed_demo_tenants()
    except Exception as e:
        print(f"\n❌ Seeding failed: {e}", file=sys.stderr)
        sys.exit(1)
