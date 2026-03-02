"""
Unit Tests: DefaultModelResolver Service

Tests the core business logic of the DefaultModelResolver service,
including resolution precedence, caching, invalidation, and metrics.
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import structlog

logger = structlog.get_logger(__name__)


@pytest.fixture
def mock_redis():
    """Mock Redis cache client."""
    with patch("db.redis_cache.client.redis_available") as available_mock, \
         patch("db.redis_cache.client.get_redis") as redis_mock:
        # Configure redis_available to return True by default
        available_mock.return_value = True
        
        # Create mock Redis client
        mock_client = MagicMock()
        mock_client.get.return_value = None
        mock_client.setex.return_value = True
        mock_client.delete.return_value = 1
        redis_mock.return_value = mock_client
        
        yield {
            "available": available_mock,
            "client": mock_client,
            "get_redis": redis_mock
        }


@pytest.fixture
def mock_db():
    """Mock database repository."""
    with patch("db.postgres_control.repositories.model_instance_repo.get_default") as get_default_mock:
        yield get_default_mock


@pytest.fixture
def mock_metrics():
    """Mock Prometheus metrics."""
    with patch("src.metrics.prometheus.dmr_cache_hits") as hits_mock, \
         patch("src.metrics.prometheus.dmr_cache_misses") as misses_mock:
        # Create mock counter objects with labels method
        hits_counter = MagicMock()
        misses_counter = MagicMock()
        
        hits_mock.labels.return_value = hits_counter
        misses_mock.labels.return_value = misses_counter
        
        yield {
            "cache_hits": hits_mock,
            "cache_misses": misses_mock,
            "hits_counter": hits_counter,
            "misses_counter": misses_counter
        }


@pytest.fixture
def dmr(mock_redis, mock_db, mock_metrics):
    """Get DefaultModelResolver with mocked dependencies."""
    from src.services.default_model_resolver import DefaultModelResolver
    # Reset the singleton for testing
    DefaultModelResolver._instance = None
    DefaultModelResolver._initialized = False
    return DefaultModelResolver()


class TestDefaultModelResolution:
    """Test default model resolution logic."""

    @pytest.mark.asyncio
    async def test_resolve_from_database_when_cache_empty(self, dmr, mock_redis, mock_db, mock_metrics):
        """
        Test: Resolve from database on cache miss.
        
        Scenario:
        - Redis cache empty (miss)
        - Database returns global default
        - Result cached in Redis
        - Metrics recorded
        """
        # Arrange
        mock_redis["client"].get.return_value = None  # Cache miss
        mock_db.return_value = {
            "model_id": "llama3.2:3b-instruct-fp16",
            "instance_id": "inst-123",
            "provider_id": "prov-456"
        }
        
        # Act
        result = await dmr.get_default_model(tenant_id=None, scope="global")
        
        # Assert
        assert result is not None
        assert result["model_id"] == "llama3.2:3b-instruct-fp16"
        assert result["source"] == "db"
        assert result["cached"] is False
        
        # Verify database queried
        mock_db.assert_called_once_with(scope="global", tenant_id=None)
        
        # Verify result cached
        mock_redis["client"].setex.assert_called_once()
        
        # Verify cache miss metric
        mock_metrics["cache_misses"].labels.assert_called()

    @pytest.mark.asyncio
    async def test_resolve_from_cache_on_cache_hit(self, dmr, mock_redis, mock_db, mock_metrics):
        """
        Test: Resolve from Redis cache on cache hit.
        
        Scenario:
        - Redis cache contains result
        - Database NOT queried
        - Cache hit metric incremented
        """
        # Arrange
        cached_result = {
            "model_id": "llama3.2:3b-instruct-fp16",
            "instance_id": "inst-123",
            "provider_id": "prov-456",
            "source": "db",
            "cached": True
        }
        mock_redis["client"].get.return_value = json.dumps(cached_result)
        
        # Act
        result = await dmr.get_default_model(tenant_id=None, scope="global")
        
        # Assert
        assert result is not None
        assert result["model_id"] == "llama3.2:3b-instruct-fp16"
        
        # Verify database NOT queried
        mock_db.assert_not_called()
        
        # Verify cache hit metric
        mock_metrics["cache_hits"].labels.assert_called()

    @pytest.mark.asyncio
    async def test_resolve_tenant_default_overrides_global(self, dmr, mock_redis, mock_db, mock_metrics):
        """
        Test: Tenant default has higher precedence than global.
        
        Scenario:
        - Global default: llama3.2:3b
        - Tenant default: qwen2.5:0.5b
        - Resolve for tenant → should return tenant default
        """
        # Arrange: Cache miss
        mock_redis["client"].get.return_value = None
        
        # Mock database to return tenant default
        mock_db.return_value = {
            "model_id": "qwen2.5:0.5b-instruct-q8_0",
            "instance_id": "inst-tenant",
            "provider_id": "prov-tenant"
        }
        
        # Act
        result = await dmr.get_default_model(tenant_id="tenant-123", scope="tenant")
        
        # Assert
        assert result is not None
        assert result["model_id"] == "qwen2.5:0.5b-instruct-q8_0"
        
        # Verify database queried with tenant_id
        mock_db.assert_called_once_with(
            scope="tenant",
            tenant_id="tenant-123"
        )

    @pytest.mark.asyncio
    async def test_fallback_to_env_var_when_no_database_default(self, dmr, mock_redis, mock_db, mock_metrics):
        """
        Test: Falls back to env var when database has no default.
        
        Scenario:
        - Cache miss
        - Database returns None (no default configured)
        - Falls back to DEFAULT_MODEL_NAME env var
        - Source marked as "env_var"
        """
        # Arrange
        mock_redis["get"].return_value = None
        mock_db.get_default.return_value = None  # No database default
        
        with patch("src.services.default_model_resolver.settings") as settings_mock:
            settings_mock.DEFAULT_MODEL_NAME = "phi3:mini"
            
            # Act
            result = dmr.resolve(tenant_id=None, scope="global")
            
            # Assert
            assert result == "phi3:mini"
            
            # Verify source is env_var
            detailed_result = dmr.get_default_model(tenant_id=None, scope="global")
            assert detailed_result["source"] == "env_var"


class TestCacheInvalidation:
    """Test cache invalidation logic."""

    def test_invalidate_cache_deletes_redis_key(self, dmr, mock_redis, mock_metrics):
        """
        Test: invalidate_cache() deletes Redis key.
        
        Scenario:
        - Call invalidate_cache(scope="global")
        - Redis DELETE called with correct key
        - Invalidation metric incremented
        """
        # Act
        dmr.invalidate_cache(tenant_id=None, scope="global")
        
        # Assert
        mock_redis["delete"].assert_called_once()
        mock_metrics["invalidations"].assert_called_once()

    def test_invalidate_tenant_cache_only_affects_tenant(self, dmr, mock_redis, mock_metrics):
        """
        Test: Tenant cache invalidation doesn't affect global cache.
        
        Scenario:
        - Invalidate tenant cache
        - Only tenant Redis key deleted
        - Global cache untouched
        """
        # Act
        dmr.invalidate_cache(tenant_id="tenant-123", scope="tenant")
        
        # Assert: Redis delete called with tenant-specific key
        call_args = mock_redis["delete"].call_args[0]
        assert "tenant-123" in str(call_args)
        
        # Metric recorded with tenant scope
        mock_metrics["invalidations"].assert_called_once()

    def test_warmup_cache_populates_redis(self, dmr, mock_redis, mock_db, mock_metrics):
        """
        Test: warmup_cache() pre-populates Redis cache.
        
        Scenario:
        - Call warmup_cache() on startup
        - Database queried
        - Result cached in Redis
        - No cache miss metric (warmup is proactive)
        """
        # Arrange
        mock_db.get_default.return_value = {
            "model_id": "llama3.2:3b-instruct-fp16",
            "scope": "global",
            "tenant_id": None
        }
        
        # Act
        dmr.warmup_cache(tenant_id=None, scope="global")
        
        # Assert
        mock_db.get_default.assert_called_once()
        mock_redis["set"].assert_called_once()
        
        # No cache miss metric (warmup is intentional)
        mock_metrics["cache_misses"].assert_not_called()


class TestMetrics:
    """Test Prometheus metrics tracking."""

    def test_metrics_track_resolution_duration(self, dmr, mock_redis, mock_db, mock_metrics):
        """
        Test: Resolution duration tracked in histogram.
        
        Scenario:
        - Resolve default model
        - record_default_model_resolution() called with duration
        """
        # Arrange
        mock_redis["get"].return_value = None
        mock_db.get_default.return_value = {
            "model_id": "llama3.2:3b-instruct-fp16",
            "scope": "global",
            "tenant_id": None
        }
        
        # Act
        dmr.resolve(tenant_id=None, scope="global")
        
        # Assert: Metric recorded with duration
        mock_metrics["record"].assert_called_once()
        call_args = mock_metrics["record"].call_args
        assert "duration" in str(call_args)

    def test_metrics_distinguish_database_vs_env_var_source(self, dmr, mock_redis, mock_db, mock_metrics):
        """
        Test: Metrics track source (database vs env_var).
        
        Scenario:
        1. Resolve from database → source="database"
        2. Fallback to env var → source="env_var"
        """
        # Test 1: Database source
        mock_redis["get"].return_value = None
        mock_db.get_default.return_value = {
            "model_id": "llama3.2:3b-instruct-fp16",
            "scope": "global",
            "tenant_id": None
        }
        
        dmr.resolve(tenant_id=None, scope="global")
        
        # Verify source="database" in metric
        call_args = mock_metrics["record"].call_args[1]
        assert call_args["source"] == "database"
        
        # Test 2: Env var fallback
        mock_db.get_default.return_value = None  # No database default
        
        with patch("src.services.default_model_resolver.settings") as settings_mock:
            settings_mock.DEFAULT_MODEL_NAME = "phi3:mini"
            
            dmr.resolve(tenant_id=None, scope="global")
            
            # Verify source="env_var" in metric
            call_args = mock_metrics["record"].call_args[1]
            assert call_args["source"] == "env_var"


class TestErrorHandling:
    """Test error handling and fallback behavior."""

    def test_graceful_fallback_on_redis_failure(self, dmr, mock_redis, mock_db, mock_metrics):
        """
        Test: Graceful fallback when Redis is unavailable.
        
        Scenario:
        - Redis cache_get() raises exception
        - Degrades to database query
        - Resolution succeeds
        """
        # Arrange
        mock_redis["get"].side_effect = Exception("Redis connection failed")
        mock_db.get_default.return_value = {
            "model_id": "llama3.2:3b-instruct-fp16",
            "scope": "global",
            "tenant_id": None
        }
        
        # Act
        result = dmr.resolve(tenant_id=None, scope="global")
        
        # Assert: Still resolves from database
        assert result == "llama3.2:3b-instruct-fp16"
        
        # Database queried despite Redis failure
        mock_db.get_default.assert_called_once()

    def test_graceful_fallback_on_database_failure(self, dmr, mock_redis, mock_db, mock_metrics):
        """
        Test: Graceful fallback when database is unavailable.
        
        Scenario:
        - Cache miss
        - Database query raises exception
        - Falls back to env var
        """
        # Arrange
        mock_redis["get"].return_value = None
        mock_db.get_default.side_effect = Exception("Database connection failed")
        
        with patch("src.services.default_model_resolver.settings") as settings_mock:
            settings_mock.DEFAULT_MODEL_NAME = "phi3:mini"
            settings_mock.DEFAULT_MODEL_ALLOW_ENV_FALLBACK = True
            
            # Act
            result = dmr.resolve(tenant_id=None, scope="global")
            
            # Assert: Falls back to env var
            assert result == "phi3:mini"

    def test_raises_error_if_no_fallback_allowed(self, dmr, mock_redis, mock_db, mock_metrics):
        """
        Test: Raises error if fallback disabled and database fails.
        
        Scenario:
        - DEFAULT_MODEL_ALLOW_ENV_FALLBACK = False
        - Database query fails
        - Should raise exception (no fallback)
        """
        # Arrange
        mock_redis["get"].return_value = None
        mock_db.get_default.return_value = None
        
        with patch("src.services.default_model_resolver.settings") as settings_mock:
            settings_mock.DEFAULT_MODEL_ALLOW_ENV_FALLBACK = False
            
            # Act & Assert
            with pytest.raises(Exception, match="No default model configured"):
                dmr.resolve(tenant_id=None, scope="global")
