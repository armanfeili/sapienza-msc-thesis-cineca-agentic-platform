"""
Unit Tests: DefaultModelResolver Service (Simplified)

Tests the core functionality of the DefaultModelResolver service.
"""

import pytest
import json
from unittest.mock import patch, MagicMock


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
    """Mock Prometheus metrics - no-op to avoid errors."""
    with patch("src.metrics.prometheus.dmr_cache_hits", create=True) as hits_mock, \
         patch("src.metrics.prometheus.dmr_cache_misses", create=True) as misses_mock:
        # Create mock counter objects with labels method
        hits_counter = MagicMock()
        misses_counter = MagicMock()
        
        hits_mock.labels.return_value = hits_counter
        misses_mock.labels.return_value = misses_counter
        
        yield {
            "cache_hits": hits_mock,
            "cache_misses": misses_mock
        }


@pytest.fixture
def dmr(mock_redis, mock_db, mock_metrics):
    """Get DefaultModelResolver with mocked dependencies."""
    from src.services.default_model_resolver import DefaultModelResolver
    # Reset the singleton for testing
    DefaultModelResolver._instance = None
    DefaultModelResolver._initialized = False
    return DefaultModelResolver()


class TestDefaultModelResolver:
    """Test DefaultModelResolver functionality."""

    @pytest.mark.asyncio
    async def test_get_default_model_from_db(self, dmr, mock_redis, mock_db):
        """Test resolving default model from database."""
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

    @pytest.mark.asyncio
    async def test_get_default_model_from_cache(self, dmr, mock_redis, mock_db):
        """Test resolving default model from Redis cache."""
        # Arrange
        cached_data = {
            "model_id": "llama3.2:3b-instruct-fp16",
            "instance_id": "inst-123",
            "provider_id": "prov-456",
            "source": "db",
            "cached": True
        }
        mock_redis["client"].get.return_value = json.dumps(cached_data)
        
        # Act
        result = await dmr.get_default_model(tenant_id=None, scope="global")
        
        # Assert
        assert result is not None
        assert result["model_id"] == "llama3.2:3b-instruct-fp16"
        # Database should NOT be queried
        mock_db.assert_not_called()

    @pytest.mark.asyncio
    async def test_fallback_to_env_var(self, dmr, mock_redis, mock_db):
        """Test fallback to environment variable when DB has no default."""
        # Arrange
        mock_redis["client"].get.return_value = None
        mock_db.return_value = None  # No database default
        
        with patch("src.services.default_model_resolver.settings") as settings_mock:
            settings_mock.DEFAULT_MODEL_NAME = "phi3:mini"
            
            # Act
            result = await dmr.get_default_model(tenant_id=None, scope="global")
            
            # Assert
            assert result is not None
            assert result["model_id"] == "phi3:mini"
            assert result["source"] == "env_fallback"

    @pytest.mark.asyncio
    async def test_invalidate_cache(self, dmr, mock_redis):
        """Test cache invalidation."""
        # Act
        result = await dmr.invalidate_cache(scope="global", tenant_id=None)
        
        # Assert
        assert result is True
        mock_redis["client"].delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_warmup_cache(self, dmr, mock_redis, mock_db):
        """Test cache warmup."""
        # Arrange
        mock_redis["client"].get.return_value = None
        mock_db.return_value = {
            "model_id": "llama3.2:3b-instruct-fp16",
            "instance_id": "inst-123",
            "provider_id": "prov-456"
        }
        
        # Act
        result = await dmr.warmup_cache(tenant_id=None, scope="global")
        
        # Assert
        assert result is True
        # Cache should be populated
        mock_redis["client"].setex.assert_called()
