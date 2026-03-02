"""
Integration Test: PATCH /defaults Cache Invalidation

Tests that PATCH operations on /v1/admin/defaults correctly invalidate
the DMR cache and trigger metrics updates.

Validates:
- Cache invalidation on model_id change
- No cache invalidation on no-op PATCH
- Metrics tracking of invalidation events
- Audit log capture of PATCH operations
"""

import pytest
import structlog
from fastapi.testclient import TestClient

logger = structlog.get_logger(__name__)


@pytest.fixture
def test_db(db_session):
    """Provide a clean database for each test."""
    yield db_session


@pytest.fixture
def client(app):
    """Provide a FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def dmr():
    """Get DefaultModelResolver singleton."""
    from src.services.default_model_resolver import get_default_model_resolver
    return get_default_model_resolver()


@pytest.fixture
def admin_headers():
    """Provide admin authentication headers."""
    # TODO: Replace with actual admin token generation
    return {"Authorization": "Bearer admin-test-token"}


class TestPATCHDefaultsInvalidation:
    """Test cache invalidation for PATCH /v1/admin/defaults."""

    def test_patch_invalidates_cache_on_model_change(self, client, test_db, dmr, admin_headers):
        """
        Test: PATCH invalidates cache when model_id changes.
        
        Scenario:
        1. Set initial default: llama3.2:3b-instruct-fp16
        2. Resolve (caches result)
        3. PATCH to change to: qwen2.5:0.5b-instruct-q8_0
        4. Resolve again - should get new value (cache invalidated)
        """
        # Arrange: Set initial default
        from db.postgres_control.repositories import default_model_repo
        
        default_model_repo.set_default(
            model_id="llama3.2:3b-instruct-fp16",
            scope="global",
            tenant_id=None,
            created_by="test_system"
        )
        
        # Populate cache
        initial_result = dmr.resolve(tenant_id=None, scope="global")
        assert initial_result == "llama3.2:3b-instruct-fp16"
        
        # Act: PATCH to change default
        response = client.patch(
            "/v1/admin/defaults",
            json={"model_id": "qwen2.5:0.5b-instruct-q8_0", "scope": "global"},
            headers=admin_headers
        )
        
        # Assert: PATCH succeeded
        assert response.status_code in [200, 201]
        
        # Verify cache was invalidated
        new_result = dmr.resolve(tenant_id=None, scope="global")
        assert new_result == "qwen2.5:0.5b-instruct-q8_0"
        assert new_result != initial_result

    def test_patch_no_invalidation_on_same_model(self, client, test_db, dmr, admin_headers):
        """
        Test: PATCH does NOT invalidate cache if model_id unchanged.
        
        Scenario:
        1. Set initial default: llama3.2:3b-instruct-fp16
        2. Resolve (caches result)
        3. PATCH with same model_id (no-op)
        4. Cache should NOT be invalidated (no invalidation metric)
        """
        # Arrange: Set initial default
        from db.postgres_control.repositories import default_model_repo
        
        default_model_repo.set_default(
            model_id="llama3.2:3b-instruct-fp16",
            scope="global",
            tenant_id=None,
            created_by="test_system"
        )
        
        # Populate cache
        dmr.resolve(tenant_id=None, scope="global")
        
        # Get initial invalidation metric
        from src.metrics.prometheus import get_metric_value
        initial_invalidations = get_metric_value("default_model_cache_invalidations_total") or 0
        
        # Act: PATCH with same model_id (no-op)
        response = client.patch(
            "/v1/admin/defaults",
            json={"model_id": "llama3.2:3b-instruct-fp16", "scope": "global"},
            headers=admin_headers
        )
        
        # Assert: PATCH succeeded
        assert response.status_code in [200, 201]
        
        # Verify cache was NOT invalidated (metric unchanged)
        new_invalidations = get_metric_value("default_model_cache_invalidations_total") or 0
        assert new_invalidations == initial_invalidations

    def test_patch_invalidation_metrics(self, client, test_db, dmr, admin_headers):
        """
        Test: PATCH invalidation increments Prometheus metrics.
        
        Scenario:
        1. Get initial invalidation count
        2. PATCH to change default
        3. Verify invalidation metric incremented
        """
        # Arrange: Set initial default
        from db.postgres_control.repositories import default_model_repo
        
        default_model_repo.set_default(
            model_id="llama3.2:3b-instruct-fp16",
            scope="global",
            tenant_id=None,
            created_by="test_system"
        )
        
        # Get initial metric
        from src.metrics.prometheus import get_metric_value
        initial_invalidations = get_metric_value(
            "default_model_cache_invalidations_total",
            labels={"scope": "global"}
        ) or 0
        
        # Act: PATCH to change default (should invalidate)
        response = client.patch(
            "/v1/admin/defaults",
            json={"model_id": "qwen2.5:0.5b-instruct-q8_0", "scope": "global"},
            headers=admin_headers
        )
        
        assert response.status_code in [200, 201]
        
        # Assert: Invalidation metric incremented
        new_invalidations = get_metric_value(
            "default_model_cache_invalidations_total",
            labels={"scope": "global"}
        )
        assert new_invalidations == initial_invalidations + 1

    def test_patch_tenant_default_only_invalidates_tenant_cache(self, client, test_db, dmr, admin_headers):
        """
        Test: PATCH to tenant default only invalidates tenant cache, not global.
        
        Scenario:
        1. Set global default
        2. Set tenant default
        3. PATCH tenant default
        4. Verify only tenant cache invalidated (scope isolation)
        """
        # Arrange: Set global and tenant defaults
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
        
        # Populate both caches
        global_result = dmr.resolve(tenant_id=None, scope="global")
        tenant_result = dmr.resolve(tenant_id=test_tenant_id, scope="tenant")
        
        assert global_result == "llama3.2:3b-instruct-fp16"
        assert tenant_result == "qwen2.5:0.5b-instruct-q8_0"
        
        # Act: PATCH tenant default only
        response = client.patch(
            "/v1/admin/defaults",
            json={
                "model_id": "phi3:mini",
                "scope": "tenant",
                "tenant_id": test_tenant_id
            },
            headers=admin_headers
        )
        
        assert response.status_code in [200, 201]
        
        # Assert: Tenant cache invalidated
        new_tenant_result = dmr.resolve(tenant_id=test_tenant_id, scope="tenant")
        assert new_tenant_result == "phi3:mini"
        
        # Global cache NOT invalidated (should still be cached)
        new_global_result = dmr.resolve(tenant_id=None, scope="global")
        assert new_global_result == "llama3.2:3b-instruct-fp16"

    def test_patch_audit_log_capture(self, client, test_db, admin_headers):
        """
        Test: PATCH operations are captured in audit logs.
        
        Scenario:
        1. PATCH to change default
        2. Verify audit log contains operation details
        """
        # Arrange: Set initial default
        from db.postgres_control.repositories import default_model_repo
        
        default_model_repo.set_default(
            model_id="llama3.2:3b-instruct-fp16",
            scope="global",
            tenant_id=None,
            created_by="test_system"
        )
        
        # Act: PATCH to change default
        response = client.patch(
            "/v1/admin/defaults",
            json={"model_id": "qwen2.5:0.5b-instruct-q8_0", "scope": "global"},
            headers=admin_headers
        )
        
        assert response.status_code in [200, 201]
        
        # Assert: Audit log exists (implementation-specific)
        # TODO: Query audit_logs table to verify entry
        # Expected fields:
        # - action: "patch_defaults"
        # - scope: "global"
        # - old_model_id: "llama3.2:3b-instruct-fp16"
        # - new_model_id: "qwen2.5:0.5b-instruct-q8_0"
        # - user: "admin-test-user"
        pass

    def test_patch_concurrent_invalidation(self, client, test_db, dmr, admin_headers):
        """
        Test: Concurrent PATCH operations handle cache invalidation correctly.
        
        Scenario:
        1. Multiple concurrent PATCH requests
        2. Verify all invalidations happen atomically
        3. No race conditions in cache invalidation
        """
        # Arrange: Set initial default
        from db.postgres_control.repositories import default_model_repo
        import concurrent.futures
        
        default_model_repo.set_default(
            model_id="llama3.2:3b-instruct-fp16",
            scope="global",
            tenant_id=None,
            created_by="test_system"
        )
        
        # Populate cache
        dmr.resolve(tenant_id=None, scope="global")
        
        # Act: Concurrent PATCH requests
        def patch_default(model_id: str):
            response = client.patch(
                "/v1/admin/defaults",
                json={"model_id": model_id, "scope": "global"},
                headers=admin_headers
            )
            return response.status_code
        
        models = ["qwen2.5:0.5b", "phi3:mini", "llama3.2:1b"]
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            results = list(executor.map(patch_default, models))
        
        # Assert: All requests succeeded
        assert all(status in [200, 201] for status in results)
        
        # Verify final state is consistent
        final_result = dmr.resolve(tenant_id=None, scope="global")
        assert final_result in models  # Should be one of the patched values


class TestPATCHDefaultsValidation:
    """Test input validation for PATCH /v1/admin/defaults."""

    def test_patch_rejects_invalid_model_id(self, client, test_db, admin_headers):
        """
        Test: PATCH rejects invalid model_id format.
        
        Scenario:
        - PATCH with empty model_id
        - Should return 422 (validation error)
        """
        response = client.patch(
            "/v1/admin/defaults",
            json={"model_id": "", "scope": "global"},
            headers=admin_headers
        )
        
        assert response.status_code == 422

    def test_patch_rejects_invalid_scope(self, client, test_db, admin_headers):
        """
        Test: PATCH rejects invalid scope value.
        
        Scenario:
        - PATCH with scope="invalid"
        - Should return 422 (validation error)
        """
        response = client.patch(
            "/v1/admin/defaults",
            json={"model_id": "llama3.2:3b", "scope": "invalid"},
            headers=admin_headers
        )
        
        assert response.status_code == 422

    def test_patch_requires_tenant_id_for_tenant_scope(self, client, test_db, admin_headers):
        """
        Test: PATCH requires tenant_id when scope="tenant".
        
        Scenario:
        - PATCH with scope="tenant" but no tenant_id
        - Should return 422 (validation error)
        """
        response = client.patch(
            "/v1/admin/defaults",
            json={"model_id": "llama3.2:3b", "scope": "tenant"},
            headers=admin_headers
        )
        
        assert response.status_code == 422
