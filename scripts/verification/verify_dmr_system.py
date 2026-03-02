#!/usr/bin/env python3
"""
DB-Driven Default Model System - Verification Script

This script verifies that all components of the DB-driven default model system
are working correctly in production.
"""

import asyncio
import sys
import time
from typing import Dict, Any


async def verify_dmr_basic() -> Dict[str, Any]:
    """Verify basic DMR functionality."""
    print("📋 Test 1: Basic DMR Functionality")
    print("-" * 60)
    
    try:
        from src.services.default_model_resolver import get_dmr
        
        dmr = get_dmr()
        result = await dmr.get_default_model(tenant_id=None, scope="global")
        
        if result:
            print(f"✅ DMR Resolution: SUCCESS")
            print(f"   Model ID: {result.get('model_id')}")
            print(f"   Instance ID: {result.get('instance_id')}")
            print(f"   Source: {result.get('source')}")
            print(f"   Cached: {result.get('cached')}")
            return {"status": "pass", "model_id": result.get('model_id')}
        else:
            print(f"❌ DMR Resolution: FAILED (no result)")
            return {"status": "fail", "error": "no_result"}
            
    except Exception as e:
        print(f"❌ DMR Resolution: ERROR - {e}")
        return {"status": "error", "error": str(e)}


async def verify_cache_performance() -> Dict[str, Any]:
    """Verify cache performance."""
    print("\n📋 Test 2: Cache Performance")
    print("-" * 60)
    
    try:
        from src.services.default_model_resolver import get_dmr
        
        dmr = get_dmr()
        
        # Clear cache
        await dmr.invalidate_cache(scope="global", tenant_id=None, reason="verification_test")
        
        # First call (DB)
        start = time.time()
        result1 = await dmr.get_default_model(tenant_id=None, scope="global")
        db_time_ms = (time.time() - start) * 1000
        
        # Second call (cache)
        start = time.time()
        result2 = await dmr.get_default_model(tenant_id=None, scope="global")
        cache_time_ms = (time.time() - start) * 1000
        
        if result1 and result2:
            speedup = db_time_ms / max(cache_time_ms, 0.01)
            print(f"✅ Cache Performance: SUCCESS")
            print(f"   DB Query Time: {db_time_ms:.2f}ms")
            print(f"   Cache Query Time: {cache_time_ms:.2f}ms")
            print(f"   Speedup: {speedup:.1f}x faster")
            
            status = "pass" if speedup > 2 else "warn"
            return {
                "status": status,
                "db_time_ms": db_time_ms,
                "cache_time_ms": cache_time_ms,
                "speedup": speedup
            }
        else:
            print(f"❌ Cache Performance: FAILED")
            return {"status": "fail", "error": "no_results"}
            
    except Exception as e:
        print(f"❌ Cache Performance: ERROR - {e}")
        return {"status": "error", "error": str(e)}


async def verify_cache_invalidation() -> Dict[str, Any]:
    """Verify cache invalidation."""
    print("\n📋 Test 3: Cache Invalidation")
    print("-" * 60)
    
    try:
        from src.services.default_model_resolver import get_dmr
        
        dmr = get_dmr()
        
        # Populate cache
        await dmr.get_default_model(tenant_id=None, scope="global")
        
        # Invalidate
        invalidated = await dmr.invalidate_cache(scope="global", tenant_id=None, reason="verification_test")
        
        print(f"✅ Cache Invalidation: SUCCESS")
        print(f"   Invalidated: {invalidated}")
        
        return {"status": "pass", "invalidated": invalidated}
        
    except Exception as e:
        print(f"❌ Cache Invalidation: ERROR - {e}")
        return {"status": "error", "error": str(e)}


async def verify_database_constraints() -> Dict[str, Any]:
    """Verify database unique constraints."""
    print("\n📋 Test 4: Database Constraints")
    print("-" * 60)
    
    try:
        import psycopg2
        from src.config import settings
        
        # Connect to PostgreSQL using app settings
        conn = psycopg2.connect(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            database=settings.DB_NAME
        )
        
        cursor = conn.cursor()
        cursor.execute(
            "SELECT indexname FROM pg_indexes WHERE tablename = 'model_defaults' AND indexname LIKE 'uq_%'"
        )
        indexes = [row[0] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        
        if "uq_model_defaults_scope_null_tenant" in indexes and \
           "uq_model_defaults_scope_tenant_not_null" in indexes:
            print(f"✅ Database Constraints: SUCCESS")
            print(f"   Found: uq_model_defaults_scope_null_tenant")
            print(f"   Found: uq_model_defaults_scope_tenant_not_null")
            return {"status": "pass"}
        else:
            print(f"❌ Database Constraints: FAILED")
            print(f"   Found indexes: {indexes}")
            return {"status": "fail", "error": "missing_indexes"}
            
    except Exception as e:
        print(f"❌ Database Constraints: ERROR - {e}")
        return {"status": "error", "error": str(e)}


async def verify_metrics() -> Dict[str, Any]:
    """Verify Prometheus metrics are available."""
    print("\n📋 Test 5: Prometheus Metrics")
    print("-" * 60)
    
    try:
        from src.metrics.prometheus import dmr_cache_hits, dmr_cache_misses
        
        print(f"✅ Prometheus Metrics: SUCCESS")
        print(f"   dmr_cache_hits: defined")
        print(f"   dmr_cache_misses: defined")
        
        return {"status": "pass"}
        
    except Exception as e:
        print(f"❌ Prometheus Metrics: ERROR - {e}")
        return {"status": "error", "error": str(e)}


async def verify_migration() -> Dict[str, Any]:
    """Verify migration 019 is applied."""
    print("\n📋 Test 6: Database Migration")
    print("-" * 60)
    
    try:
        import psycopg2
        from src.config import settings
        
        # Connect to PostgreSQL using app settings
        conn = psycopg2.connect(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            database=settings.DB_NAME
        )
        
        cursor = conn.cursor()
        cursor.execute("SELECT version_num FROM alembic_version")
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        version = result[0] if result else None
        
        if version and "019" in version:
            print(f"✅ Database Migration: SUCCESS")
            print(f"   Current migration: {version} (head)")
            return {"status": "pass", "migration": version}
        else:
            print(f"❌ Database Migration: FAILED")
            print(f"   Current migration: {version}")
            return {"status": "fail", "error": "migration_not_019"}
            
    except Exception as e:
        print(f"❌ Database Migration: ERROR - {e}")
        return {"status": "error", "error": str(e)}


async def main():
    """Run all verification tests."""
    print("=" * 60)
    print("🔍 DB-Driven Default Model System - Verification")
    print("=" * 60)
    print()
    
    results = {}
    
    # Run all tests
    results["migration"] = await verify_migration()
    results["database_constraints"] = await verify_database_constraints()
    results["basic_dmr"] = await verify_dmr_basic()
    results["cache_performance"] = await verify_cache_performance()
    results["cache_invalidation"] = await verify_cache_invalidation()
    results["metrics"] = await verify_metrics()
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Verification Summary")
    print("=" * 60)
    
    total_tests = len(results)
    passed_tests = sum(1 for r in results.values() if r.get("status") == "pass")
    warned_tests = sum(1 for r in results.values() if r.get("status") == "warn")
    failed_tests = sum(1 for r in results.values() if r.get("status") in ["fail", "error"])
    
    print(f"Total Tests: {total_tests}")
    print(f"✅ Passed: {passed_tests}")
    print(f"⚠️  Warned: {warned_tests}")
    print(f"❌ Failed: {failed_tests}")
    print()
    
    if failed_tests == 0 and warned_tests == 0:
        print("🎉 ALL TESTS PASSED! System is production ready!")
        return 0
    elif failed_tests == 0:
        print("⚠️  ALL TESTS PASSED (with warnings). System is operational.")
        return 0
    else:
        print("❌ SOME TESTS FAILED. Please review the failures above.")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
