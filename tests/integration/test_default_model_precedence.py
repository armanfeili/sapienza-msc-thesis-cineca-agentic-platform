"""
Integration Test: Default Model Precedence

Tests the precedence order of default model resolution:
1. Tenant-specific default (highest priority)
2. Global default from database
3. Environment variable fallback (lowest priority, emergency only)

Validates that the DMR correctly follows this precedence and that
cache invalidation works properly after PATCH /defaults operations.
"""

import pytest
import structlog
from fastapi.testclient import TestClient

logger = structlog.get_logger(__name__)


@pytest.fixture
def test_db(db_session):
    """Provide a clean database for each test."""
    yield db_session
    # Cleanup handled by db_session fixture


@pytest.fixture
def client(app):
    """Provide a FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def dmr():
    """Get DefaultModelResolver singleton."""
    from src.services.default_model_resolver import get_default_model_resolver
    return get_default_model_resolver()


class TestDefaultModelPrecedence:
    """Test default model resolution precedence."""

    def test_global_default_from_database(self, client, test_db, dmr):
        """
        Test: Global default resolves from database when configured.
        
        Scenario:
        - Global default exists in database
        - No tenant-specific default
        - DMR should resolve to global default from DB
        """
        # Arrange: Insert global default via database
        from db.postgres_control.repositories import default_model_repo
        
        default_model_repo.set_default(
            model_id="llama3.2:3b-instruct-fp16",
            scope="global",
            tenant_id=None,
            created_by="test_system"
        )
        
        # Act: Resolve default model
        result = dmr.resolve(tenant_id=None, scope="global")
        
        # Assert: Should resolve to database global default
        assert result == "llama3.2:3b-instruct-fp16"
        
        # Verify source is database
        detailed_result = dmr.get_default_model(tenant_id=None, scope="global")
        assert detailed_result["source"] == "database"
        assert detailed_result["model_id"] == "llama3.2:3b-instruct-fp16"

    def test_tenant_default_overrides_global(self, client, test_db, dmr):
        """
        Test: Tenant-specific default overrides global default.
        
        Scenario:
        - Global default: llama3.2:3b-instruct-fp16
        - Tenant default: qwen2.5:0.5b-instruct-q8_0
        - DMR should resolve to tenant default (higher precedence)
        """
        # Arrange: Insert both global and tenant defaults
        from db.postgres_control.repositories import default_model_repo
        
        # Global default
        default_model_repo.set_default(
            model_id="llama3.2:3b-instruct-fp16",
            scope="global",
            tenant_id=None,
            created_by="test_system"
        )
        
        # Tenant default
        test_tenant_id = "tenant-123"
        default_model_repo.set_default(
            model_id="qwen2.5:0.5b-instruct-q8_0",
            scope="tenant",
            tenant_id=test_tenant_id,
            created_by="test_user"
        )
        
        # Act: Resolve for tenant
        result = dmr.resolve(tenant_id=test_tenant_id, scope="tenant")
        
        # Assert: Should resolve to tenant default (higher precedence)
        assert result == "qwen2.5:0.5b-instruct-q8_0"
        
        # Verify source
        detailed_result = dmr.get_default_model(tenant_id=test_tenant_id, scope="tenant")
        assert detailed_result["source"] == "database"
        assert detailed_result["model_id"] == "qwen2.5:0.5b-instruct-q8_0"
        assert detailed_result["scope"] == "tenant"

    def test_env_var_fallback_when_no_database_default(self, client, test_db, dmr, monkeypatch):
        """
        Test: Falls back to env var when no database default configured.
        
        Scenario:
        - No global default in database
        - DEFAULT_MODEL_NAME env var set
        - DMR should fall back to env var (degraded state)
        """
        # Arrange: Ensure no database default exists
        from db.postgres_control.repositories import default_model_repo
        
        # Delete any existing defaults
        default_model_repo.delete_default(scope="global", tenant_id=None)
        
        # Set env var fallback
        monkeypatch.setenv("DEFAULT_MODEL_NAME", "phi3:mini")
        
        # Act: Resolve default model
        result = dmr.resolve(tenant_id=None, scope="global")
        
        # Assert: Should fall back to env var
        assert result == "phi3:mini"
        
        # Verify source is env_var (degraded)
        detailed_result = dmr.get_default_model(tenant_id=None, scope="global")
        assert detailed_result["source"] == "env_var"
        assert detailed_result["model_id"] == "phi3:mini"

    def test_readyz_endpoint_healthy_with_database_default(self, client, test_db):
        """
        Test: /readyz endpoint returns 200 when database default is configured.
        
        Scenario:
        - Global default exists in database
        - /readyz should return 200 (healthy)
        """
        # Arrange: Insert global default
        from db.postgres_control.repositories import default_model_repo
        
        default_model_repo.set_default(
            model_id="llama3.2:3b-instruct-fp16",
            scope="global",
            tenant_id=None,
            created_by="test_system"
        )
        
        # Act: Call /readyz endpoint
        response = client.get("/readyz")
        
        # Assert: Should return 200 (healthy)
        assert response.status_code == 200
        assert response.json()["status"] == "ready"
        assert response.json()["model_id"] == "llama3.2:3b-instruct-fp16"
        assert response.json()["source"] == "database"

    def test_readyz_endpoint_degraded_with_env_fallback(self, client, test_db, monkeypatch):
        """
        Test: /readyz endpoint returns 503 when falling back to env var.
        
        Scenario:
        - No database default configured
        - Falling back to DEFAULT_MODEL_NAME env var
        - /readyz should return 503 (degraded)
        """
        # Arrange: Ensure no database default
        from db.postgres_control.repositories import default_model_repo
        default_model_repo.delete_default(scope="global", tenant_id=None)
        
        # Set env var fallback
        monkeypatch.setenv("DEFAULT_MODEL_NAME", "phi3:mini")
        
        # Act: Call /readyz endpoint
        response = client.get("/readyz")
        
        # Assert: Should return 503 (degraded)
        assert response.status_code == 503
        assert response.json()["status"] == "degraded"
        assert response.json()["reason"] == "fallback_to_env_var"

    def test_prometheus_metrics_track_resolution_source(self, client, test_db, dmr):
        """
        Test: Prometheus metrics correctly track resolution source (database vs env_var).
        
        Scenario:
        - Resolve default from database
        - Check that default_model_resolution_total{source="database"} increments
        """
        # Arrange: Insert global default
        from db.postgres_control.repositories import default_model_repo
        
        default_model_repo.set_default(
            model_id="llama3.2:3b-instruct-fp16",
            scope="global",
            tenant_id=None,
            created_by="test_system"
        )
        
        # Get initial metric value
        from src.metrics.prometheus import get_metric_value
        initial_db_count = get_metric_value(
            "default_model_resolution_total",
            labels={"source": "database", "scope": "global"}
        ) or 0
        
        # Act: Resolve default model (triggers metric)
        dmr.resolve(tenant_id=None, scope="global")
        
        # Assert: Metric incremented
        new_db_count = get_metric_value(
            "default_model_resolution_total",
            labels={"source": "database", "scope": "global"}
        )
        assert new_db_count == initial_db_count + 1


class TestCacheInvalidation:
    """Test cache invalidation after PATCH /defaults operations."""

    def test_cache_invalidated_after_patch_defaults(self, client, test_db, dmr):
        """
        Test: Cache is invalidated after PATCH /v1/admin/defaults.
        
        Scenario:
        1. Resolve default model (caches result)
        2. PATCH /defaults to change default model
        3. Resolve again - should get new value, not cached old value
        """
        # Arrange: Insert initial default
        from db.postgres_control.repositories import default_model_repo
        
        default_model_repo.set_default(
            model_id="llama3.2:3b-instruct-fp16",
            scope="global",
            tenant_id=None,
            created_by="test_system"
        )
        
        # Act 1: Resolve (caches result)
        result1 = dmr.resolve(tenant_id=None, scope="global")
        assert result1 == "llama3.2:3b-instruct-fp16"
        
        # Act 2: PATCH to change default
        patch_response = client.patch(
            "/v1/admin/defaults",
            json={"model_id": "qwen2.5:0.5b-instruct-q8_0", "scope": "global"}
        )
        assert patch_response.status_code in [200, 201]
        
        # Act 3: Resolve again (should not use cached value)
        result2 = dmr.resolve(tenant_id=None, scope="global")
        
        # Assert: Should get new value, proving cache was invalidated
        assert result2 == "qwen2.5:0.5b-instruct-q8_0"
        assert result2 != result1

    def test_cache_hit_rate_metrics(self, client, test_db, dmr):
        """
        Test: Cache hit/miss metrics are tracked correctly.
        
        Scenario:
        1. First resolve (cache miss)
        2. Second resolve (cache hit)
        3. Verify metrics reflect cache hit
        """
        # Arrange: Insert default
        from db.postgres_control.repositories import default_model_repo
        
        default_model_repo.set_default(
            model_id="llama3.2:3b-instruct-fp16",
            scope="global",
            tenant_id=None,
            created_by="test_system"
        )
        
        # Clear any existing cache
        dmr.invalidate_cache(tenant_id=None, scope="global")
        
        # Get initial metrics
        from src.metrics.prometheus import get_metric_value
        initial_hits = get_metric_value("default_model_cache_hits_total") or 0
        initial_misses = get_metric_value("default_model_cache_misses_total") or 0
        
        # Act 1: First resolve (cache miss)
        dmr.resolve(tenant_id=None, scope="global")
        
        # Assert: Cache miss metric incremented
        new_misses = get_metric_value("default_model_cache_misses_total")
        assert new_misses == initial_misses + 1
        
        # Act 2: Second resolve (cache hit)
        dmr.resolve(tenant_id=None, scope="global")
        
        # Assert: Cache hit metric incremented
        new_hits = get_metric_value("default_model_cache_hits_total")
        assert new_hits == initial_hits + 1
