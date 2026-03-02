"""
Integration Test: DefaultModelResolver with Real Database

Tests the DefaultModelResolver with actual PostgreSQL and Redis connections.
This validates the complete flow including database queries, caching, and invalidation.
"""

import pytest
import asyncio
from unittest.mock import patch
import structlog

logger = structlog.get_logger(__name__)


@pytest.mark.asyncio
async def test_dmr_resolves_from_database():
    """Test that DMR can resolve default model from real database."""
    from src.services.default_model_resolver import get_dmr
    from db.postgres_control.repositories import model_instance_repo
    
    # Get DMR instance
    dmr = get_dmr()
    
    # First, check if there's a global default in DB
    db_default = model_instance_repo.get_default(scope="global", tenant_id=None)
    expected_model_id = getattr(db_default, "provider_model_id", None) if db_default else None
    
    # Resolve default model
    result = await dmr.get_default_model(tenant_id=None, scope="global")
    
    if db_default:
        # If DB has a default, DMR should return it
        assert result is not None
        assert result["model_id"] == expected_model_id
        assert result["source"] in ["db", "redis"]  # Could be cached
        logger.info("test.dmr_resolves_from_database.success", model_id=result["model_id"])
    else:
        # If no DB default, should fallback to env var
        assert result is not None
        assert result["source"] == "env_fallback"
        logger.info("test.dmr_resolves_from_database.env_fallback", model_id=result["model_id"])


@pytest.mark.asyncio
async def test_dmr_cache_invalidation():
    """Test that cache invalidation works correctly."""
    from src.services.default_model_resolver import get_dmr
    
    dmr = get_dmr()
    
    # Resolve to populate cache
    result1 = await dmr.get_default_model(tenant_id=None, scope="global")
    assert result1 is not None
    
    # Invalidate cache
    invalidated = await dmr.invalidate_cache(scope="global", tenant_id=None, reason="test")
    
    # Resolve again (should query DB again)
    result2 = await dmr.get_default_model(tenant_id=None, scope="global")
    assert result2 is not None
    assert result2["model_id"] == result1["model_id"]
    
    logger.info("test.dmr_cache_invalidation.success", 
                invalidated=invalidated,
                model_id=result2["model_id"])


@pytest.mark.asyncio
async def test_dmr_warmup_cache():
    """Test that cache warmup works correctly."""
    from src.services.default_model_resolver import get_dmr
    
    dmr = get_dmr()
    
    # Invalidate cache first
    await dmr.invalidate_cache(scope="global", tenant_id=None, reason="test_setup")
    
    # Warmup cache
    warmed = await dmr.warmup_cache(tenant_id=None, scope="global")
    
    # Resolve (should be cached now)
    result = await dmr.get_default_model(tenant_id=None, scope="global")
    
    if result and result.get("source") != "env_fallback":
        # If we have a DB default, warmup should have worked
        assert warmed is True
        logger.info("test.dmr_warmup_cache.success", model_id=result["model_id"])
    else:
        # If only env fallback, warmup returns False
        assert warmed is False or result["source"] == "env_fallback"
        logger.info("test.dmr_warmup_cache.no_db_default")


@pytest.mark.asyncio
async def test_dmr_unique_constraint_prevents_duplicates():
    """Test that database unique constraint prevents duplicate defaults."""
    from db.postgres_control.repositories import model_instance_repo
    from db.postgres_control.database import get_db
    from sqlalchemy.exc import IntegrityError
    import uuid
    
    # This test verifies migration 019 is working
    
    # Get existing default if any
    existing = model_instance_repo.get_default(scope="global", tenant_id=None)
    
    if existing:
        # Try to insert another global default (should fail due to unique constraint)
        from db.postgres_control.models.model_instance import ModelDefault
        
        session = next(get_db())
        
        try:
            # Generate a valid UUID for instance_id
            duplicate = ModelDefault(
                scope="global",
                tenant_id=None,
                instance_id=str(uuid.uuid4())
            )
            
            session.add(duplicate)
            
            # This should raise IntegrityError due to unique constraint
            # uq_model_defaults_scope_null_tenant prevents duplicate global defaults
            try:
                session.commit()
                # If we get here, the unique constraint is NOT working
                pytest.fail("Expected IntegrityError due to unique constraint violation")
            except IntegrityError as e:
                # Expected! Unique constraint is working
                session.rollback()
                logger.info("test.dmr_unique_constraint.verified", error=str(e))
                
        finally:
            session.close()
    else:
        # No existing default, skip test
        logger.info("test.dmr_unique_constraint.no_existing_default")
        pytest.skip("No existing global default to test constraint against")


@pytest.mark.asyncio
async def test_dmr_redis_graceful_degradation():
    """Test that DMR works even if Redis is unavailable."""
    from src.services.default_model_resolver import get_dmr
    
    dmr = get_dmr()
    
    # Mock Redis to be unavailable
    with patch("db.redis_cache.client.redis_available", return_value=False):
        # Should still resolve from database
        result = await dmr.get_default_model(tenant_id=None, scope="global")
        
        assert result is not None
        # Source should be db or env_fallback (not redis)
        assert result["source"] in ["db", "env_fallback"]
        
        logger.info("test.dmr_redis_degradation.success", 
                    source=result["source"],
                    model_id=result["model_id"])


@pytest.mark.asyncio  
async def test_dmr_singleton_pattern():
    """Test that DMR follows singleton pattern."""
    from src.services.default_model_resolver import get_dmr, DefaultModelResolver
    
    # Get multiple instances
    dmr1 = get_dmr()
    dmr2 = get_dmr()
    dmr3 = DefaultModelResolver()
    
    # All should be the same instance
    assert dmr1 is dmr2
    assert dmr2 is dmr3
    
    logger.info("test.dmr_singleton.verified")


if __name__ == "__main__":
    # Allow running tests directly
    asyncio.run(test_dmr_resolves_from_database())
    asyncio.run(test_dmr_cache_invalidation())
    asyncio.run(test_dmr_warmup_cache())
    asyncio.run(test_dmr_redis_graceful_degradation())
    asyncio.run(test_dmr_singleton_pattern())
    print("✅ All DMR integration tests passed!")
