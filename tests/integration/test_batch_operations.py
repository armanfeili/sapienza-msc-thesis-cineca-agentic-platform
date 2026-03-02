"""
Integration tests for batch operations endpoints.

Tests batch creation/deletion of models and tools with full database integration.
"""

import os
import uuid

import pytest

# Set DB_HOST to localhost for tests running outside Docker
os.environ["DB_HOST"] = "localhost"


@pytest.fixture(scope="session", autouse=True)
def setup_test_env():
    """Set up test environment variables."""
    os.environ["DB_HOST"] = "localhost"
    yield

import pytest
import uuid
import time
from typing import Dict, Any


@pytest.fixture
def admin_headers(mint_token):
    """Generate admin token with admin:all and admin:write permissions."""
    token = mint_token(
        sub="admin-user",
        roles=["admin"],
        scopes=["admin:all", "admin:write"],
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def read_only_headers(mint_token):
    """Generate token with only admin:read permission (should fail on write operations)."""
    token = mint_token(
        sub="readonly-user",
        roles=["user"],  # NOT admin role
        scopes=["admin:read"],  # Only read scope, no write
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def test_tenant_id(db_session):
    """
    Create a test tenant directly in the database.
    
    Returns:
        str: The ID of the created tenant
    """
    from db.postgres_control.models.tenant import Tenant
    from db.postgres_control.models.tool import Tool
    import uuid
    from datetime import datetime
    
    tenant_id = f"test-tenant-{uuid.uuid4()}"
    
    # Create tenant directly in database
    tenant = Tenant(
        id=tenant_id,
        name=f"Test Tenant {uuid.uuid4().hex[:8]}",
        admin_email="admin@test.com",
        metadata_={},
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        version=1
    )
    
    db_session.add(tenant)
    db_session.commit()
    
    yield tenant_id
    
    # Cleanup: Delete tools first (to avoid foreign key constraint), then tenant
    try:
        db_session.query(Tool).filter_by(owner_tenant_id=tenant_id).delete()
        db_session.query(Tenant).filter_by(id=tenant_id).delete()
        db_session.commit()
    except Exception:
        db_session.rollback()


@pytest.fixture
def test_provider_id(db_session, test_tenant_id):
    """Create a test provider directly in database."""
    from db.postgres_control.models.provider import Provider
    from datetime import datetime, UTC
    
    provider_id = f"test-provider-{uuid.uuid4()}"
    provider = Provider(
        id=provider_id,
        name=f"Test Provider {uuid.uuid4().hex[:8]}",
        type="openai_compatible",
        base_url="https://api.test.com",
        model="gpt-4",
        tenant_id=test_tenant_id,
        config_json={},
        has_api_key=False,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(provider)
    db_session.commit()
    
    yield provider_id
    
    # Cleanup
    try:
        db_session.query(Provider).filter(Provider.id == provider_id).delete()
        db_session.commit()
    except Exception:
        db_session.rollback()


@pytest.mark.integration
class TestBatchOperations:
    """Test batch operations endpoint"""

    def test_batch_operations_authentication_required(self, client):
        """Batch operations endpoint should require authentication"""
        resp = client.post(
            "/v1/batch/operations",
            json={"operations": []}
        )
        assert resp.status_code == 401

    def test_batch_operations_admin_permission_required(self, client, read_only_headers):
        """Batch operations should require admin:write permission"""
        resp = client.post(
            "/v1/batch/operations",
            json={"operations": []},
            headers=read_only_headers
        )
        assert resp.status_code == 403

    def test_batch_operations_empty_list(self, client, admin_headers):
        """Empty operations list should succeed with zero counts"""
        resp = client.post(
            "/v1/batch/operations",
            json={"operations": []},
            headers=admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["totalOperations"] == 0
        assert data["successCount"] == 0
        assert data["failureCount"] == 0
        assert data["results"] == []

    def test_batch_operations_exceeds_limit(self, client, admin_headers):
        """Batch with >100 operations should fail"""
        operations = [
            {
                "operation": "create",
                "resourceType": "model",
                "data": {"instanceName": f"model-{i}"}
            }
            for i in range(101)
        ]
        
        resp = client.post(
            "/v1/batch/operations",
            json={"operations": operations},
            headers=admin_headers
        )
        assert resp.status_code == 400
        assert "100 operations" in resp.json()["detail"]

    def test_batch_create_model_missing_data(self, client, admin_headers):
        """Batch create without data should fail validation"""
        resp = client.post(
            "/v1/batch/operations",
            json={
                "operations": [{
                    "operation": "create",
                    "resourceType": "model"
                    # Missing "data" field
                }]
            },
            headers=admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["totalOperations"] == 1
        assert data["failureCount"] == 1
        result = data["results"][0]
        assert not result["success"]
        assert result["statusCode"] == 400
        assert "Missing model data" in result["error"]

    def test_batch_create_model_missing_required_fields(
        self, client, admin_headers, test_tenant_id
    ):
        """Batch create model should validate required fields"""
        resp = client.post(
            "/v1/batch/operations",
            json={
                "operations": [{
                    "operation": "create",
                    "resourceType": "model",
                    "data": {
                        "instanceName": "test-model"
                        # Missing providerId and modelId
                    }
                }]
            },
            headers=admin_headers
        )
        
        assert resp.status_code == 200
        data = resp.json()
        assert data["failureCount"] == 1
        result = data["results"][0]
        assert not result["success"]
        assert result["statusCode"] == 400
        assert "providerId" in result["error"] or "modelId" in result["error"]

    def test_batch_create_model_invalid_provider(
        self, client, admin_headers, test_tenant_id
    ):
        """Batch create model with non-existent provider should fail"""
        resp = client.post(
            "/v1/batch/operations",
            json={
                "operations": [{
                    "operation": "create",
                    "resourceType": "model",
                    "data": {
                        "providerId": "non-existent-provider",
                        "instanceName": "test-model",
                        "modelId": "gpt-4",
                        "tenantId": test_tenant_id
                    }
                }]
            },
            headers=admin_headers
        )
        
        assert resp.status_code == 200
        data = resp.json()
        assert data["failureCount"] == 1
        result = data["results"][0]
        assert not result["success"]
        assert result["statusCode"] == 404
        assert "Provider not found" in result["error"]

    def test_batch_create_model_success(
        self, client, admin_headers, test_tenant_id, test_provider_id
    ):
        """Batch create model with valid data should succeed"""
        instance_name = f"batch-model-{uuid.uuid4()}"
        
        resp = client.post(
            "/v1/batch/operations",
            json={
                "operations": [{
                    "operation": "create",
                    "resourceType": "model",
                    "data": {
                        "providerId": test_provider_id,
                        "instanceName": instance_name,
                        "modelId": "gpt-3.5-turbo",
                        "tenantId": test_tenant_id,
                        "contextWindow": 4096,
                        "parameters": {"temperature": 0.7}
                    }
                }]
            },
            headers=admin_headers
        )
        
        assert resp.status_code == 200
        data = resp.json()
        
        assert data["totalOperations"] == 1
        assert data["successCount"] == 1
        assert data["failureCount"] == 0
        
        result = data["results"][0]
        assert result["success"]
        assert result["statusCode"] == 201
        assert result["operation"] == "create"
        assert result["resourceType"] == "model"
        assert result["resourceId"] is not None
        assert result["data"] is not None

    def test_batch_create_model_idempotency(
        self, client, admin_headers, test_tenant_id, test_provider_id
    ):
        """Creating the same model twice should be idempotent"""
        instance_name = f"idempotent-model-{uuid.uuid4()}"
        model_data = {
            "providerId": test_provider_id,
            "instanceName": instance_name,
            "modelId": "gpt-3.5-turbo",
            "tenantId": test_tenant_id
        }
        
        # First create
        resp1 = client.post(
            "/v1/batch/operations",
            json={
                "operations": [{
                    "operation": "create",
                    "resourceType": "model",
                    "data": model_data
                }]
            },
            headers=admin_headers
        )
        assert resp1.status_code == 200
        result1 = resp1.json()["results"][0]
        assert result1["success"]
        model_id_1 = result1["resourceId"]
        
        # Second create (idempotent)
        resp2 = client.post(
            "/v1/batch/operations",
            json={
                "operations": [{
                    "operation": "create",
                    "resourceType": "model",
                    "data": model_data
                }]
            },
            headers=admin_headers
        )
        assert resp2.status_code == 200
        result2 = resp2.json()["results"][0]
        assert result2["success"]
        model_id_2 = result2["resourceId"]
        
        # Should return same model ID
        assert model_id_1 == model_id_2

    def test_batch_delete_model_not_found(self, client, admin_headers, test_tenant_id):
        """Deleting non-existent model should fail gracefully"""
        resp = client.post(
            "/v1/batch/operations",
            json={
                "operations": [{
                    "operation": "delete",
                    "resourceType": "model",
                    "resourceId": str(uuid.uuid4())
                }]
            },
            headers=admin_headers
        )
        
        assert resp.status_code == 200
        data = resp.json()
        assert data["failureCount"] == 1
        result = data["results"][0]
        assert not result["success"]
        assert result["statusCode"] == 404
        assert "not found" in result["error"].lower()

    def test_batch_create_then_delete_model(
        self, client, admin_headers, test_tenant_id, test_provider_id
    ):
        """Create model then delete it in batch"""
        instance_name = f"temp-model-{uuid.uuid4()}"
        
        # Create model
        create_resp = client.post(
            "/v1/batch/operations",
            json={
                "operations": [{
                    "operation": "create",
                    "resourceType": "model",
                    "data": {
                        "providerId": test_provider_id,
                        "instanceName": instance_name,
                        "modelId": "gpt-3.5-turbo",
                        "tenantId": test_tenant_id
                    }
                }]
            },
            headers=admin_headers
        )
        assert create_resp.status_code == 200
        model_id = create_resp.json()["results"][0]["resourceId"]
        
        # Delete model
        delete_resp = client.post(
            "/v1/batch/operations",
            json={
                "operations": [{
                    "operation": "delete",
                    "resourceType": "model",
                    "resourceId": model_id
                }]
            },
            headers=admin_headers
        )
        
        assert delete_resp.status_code == 200
        data = delete_resp.json()
        assert data["successCount"] == 1
        result = data["results"][0]
        assert result["success"]
        assert result["statusCode"] == 204

    def test_batch_continue_on_error(
        self, client, admin_headers, test_tenant_id, test_provider_id
    ):
        """With continueOnError=true, should process all operations"""
        resp = client.post(
            "/v1/batch/operations",
            json={
                "operations": [
                    {
                        "operation": "create",
                        "resourceType": "model",
                        "data": {
                            "providerId": "invalid-provider",
                            "instanceName": "model-1",
                            "modelId": "gpt-4",
                            "tenantId": test_tenant_id
                        }
                    },
                    {
                        "operation": "create",
                        "resourceType": "model",
                        "data": {
                            "providerId": test_provider_id,
                            "instanceName": f"model-success-{uuid.uuid4()}",
                            "modelId": "gpt-3.5-turbo",
                            "tenantId": test_tenant_id
                        }
                    }
                ],
                "continueOnError": True
            },
            headers=admin_headers
        )
        
        assert resp.status_code == 200
        data = resp.json()
        assert data["totalOperations"] == 2
        assert data["successCount"] == 1
        assert data["failureCount"] == 1
        assert len(data["results"]) == 2
        assert not data["results"][0]["success"]  # First failed
        assert data["results"][1]["success"]  # Second succeeded

    def test_batch_stop_on_error(
        self, client, admin_headers, test_tenant_id, test_provider_id
    ):
        """With continueOnError=false, should stop after first error"""
        resp = client.post(
            "/v1/batch/operations",
            json={
                "operations": [
                    {
                        "operation": "create",
                        "resourceType": "model",
                        "data": {
                            "providerId": "invalid-provider",
                            "instanceName": "model-1",
                            "modelId": "gpt-4",
                            "tenantId": test_tenant_id
                        }
                    },
                    {
                        "operation": "create",
                        "resourceType": "model",
                        "data": {
                            "providerId": test_provider_id,
                            "instanceName": "model-2",
                            "modelId": "gpt-3.5-turbo",
                            "tenantId": test_tenant_id
                        }
                    }
                ],
                "continueOnError": False
            },
            headers=admin_headers
        )
        
        assert resp.status_code == 200
        data = resp.json()
        # Should only process first operation
        assert len(data["results"]) == 1
        assert data["failureCount"] == 1


@pytest.mark.integration
class TestBulkModelOperations:
    """Test bulk model create/delete endpoints"""

    def test_bulk_create_models_authentication_required(self, client):
        """Bulk create models should require authentication"""
        resp = client.post(
            "/v1/batch/models/bulk-create?tenant_id=test",
            json=[]
        )
        assert resp.status_code == 401

    def test_bulk_create_models_exceeds_limit(
        self, client, admin_headers, test_tenant_id
    ):
        """Bulk create with >50 models should fail"""
        models = [
            {
                "instanceName": f"model-{i}",
                "providerId": "test",
                "modelId": "gpt-4"
            }
            for i in range(51)
        ]
        
        resp = client.post(
            f"/v1/batch/models/bulk-create?tenant_id={test_tenant_id}",
            json=models,
            headers=admin_headers
        )
        assert resp.status_code == 400
        assert "50 models" in resp.json()["detail"]

    def test_bulk_create_models_validation(
        self, client, admin_headers, test_tenant_id
    ):
        """Bulk create should validate each model"""
        models = [
            {
                "instanceName": "valid-model",
                "providerId": "test",
                "modelId": "gpt-4"
            },
            {
                "instanceName": "invalid-model"
                # Missing required fields
            }
        ]
        
        resp = client.post(
            f"/v1/batch/models/bulk-create?tenant_id={test_tenant_id}",
            json=models,
            headers=admin_headers
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["totalOperations"] == 2
        assert data["failureCount"] >= 1  # At least the invalid one fails

    def test_bulk_create_models_success(
        self, client, admin_headers, test_tenant_id, test_provider_id
    ):
        """Bulk create multiple valid models"""
        models = [
            {
                "instanceName": f"bulk-model-{i}-{uuid.uuid4()}",
                "providerId": test_provider_id,
                "modelId": "gpt-3.5-turbo",
                "contextWindow": 4096
            }
            for i in range(3)
        ]
        
        resp = client.post(
            f"/v1/batch/models/bulk-create?tenant_id={test_tenant_id}",
            json=models,
            headers=admin_headers
        )
        
        assert resp.status_code == 201
        data = resp.json()
        assert data["totalOperations"] == 3
        assert data["successCount"] == 3
        assert data["failureCount"] == 0
        assert len(data["results"]) == 3
        
        # All should succeed
        for result in data["results"]:
            assert result["success"]
            assert result["statusCode"] == 201
            assert result["resourceId"] is not None

    def test_bulk_delete_models_success(
        self, client, admin_headers, test_tenant_id, test_provider_id
    ):
        """Bulk delete multiple models"""
        # First create some models
        models = [
            {
                "instanceName": f"delete-model-{i}-{uuid.uuid4()}",
                "providerId": test_provider_id,
                "modelId": "gpt-3.5-turbo"
            }
            for i in range(3)
        ]
        
        create_resp = client.post(
            f"/v1/batch/models/bulk-create?tenant_id={test_tenant_id}",
            json=models,
            headers=admin_headers
        )
        assert create_resp.status_code == 201
        
        # Extract model IDs
        model_ids = [
            result["resourceId"]
            for result in create_resp.json()["results"]
            if result["success"]
        ]
        assert len(model_ids) == 3
        
        # Delete them
        delete_resp = client.request(
            "DELETE",
            f"/v1/batch/models/bulk-delete?tenant_id={test_tenant_id}",
            json=model_ids,
            headers=admin_headers
        )
        
        assert delete_resp.status_code == 200
        data = delete_resp.json()
        assert data["totalOperations"] == 3
        assert data["successCount"] == 3
        assert data["failureCount"] == 0

    def test_bulk_delete_models_exceeds_limit(
        self, client, admin_headers, test_tenant_id
    ):
        """Bulk delete with >50 models should fail"""
        model_ids = [str(uuid.uuid4()) for _ in range(51)]
        
        resp = client.request(
            "DELETE",
            f"/v1/batch/models/bulk-delete?tenant_id={test_tenant_id}",
            json=model_ids,
            headers=admin_headers
        )
        assert resp.status_code == 400
        assert "50 models" in resp.json()["detail"]


@pytest.mark.integration
class TestBulkToolOperations:
    """Test bulk tool create endpoint"""

    def test_bulk_create_tools_authentication_required(self, client):
        """Bulk create tools should require authentication"""
        resp = client.post(
            "/v1/batch/tools/bulk-create?tenant_id=test",
            json=[]
        )
        assert resp.status_code == 401

    def test_bulk_create_tools_validation(
        self, client, admin_headers, test_tenant_id
    ):
        """Bulk create should validate each tool"""
        tools = [
            {
                "name": "valid-tool",
                "version": "1.0.0",
                "inputSchema": {"type": "object"}
            },
            {
                "name": "invalid-tool"
                # Missing version and inputSchema
            }
        ]
        
        resp = client.post(
            f"/v1/batch/tools/bulk-create?tenant_id={test_tenant_id}",
            json=tools,
            headers=admin_headers
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["totalOperations"] == 2
        assert data["failureCount"] >= 1

    def test_bulk_create_tools_success(
        self, client, admin_headers, test_tenant_id
    ):
        """Bulk create multiple valid tools"""
        tools = [
            {
                "name": f"batch-tool-{i}-{uuid.uuid4()}",
                "version": "1.0.0",
                "inputSchema": {"type": "object", "properties": {}},
                "description": f"Test tool {i}"
            }
            for i in range(3)
        ]
        
        resp = client.post(
            f"/v1/batch/tools/bulk-create?tenant_id={test_tenant_id}",
            json=tools,
            headers=admin_headers
        )
        
        assert resp.status_code == 201
        data = resp.json()
        assert data["totalOperations"] == 3
        assert data["successCount"] == 3
        assert data["failureCount"] == 0

    def test_bulk_create_tools_idempotency(
        self, client, admin_headers, test_tenant_id
    ):
        """Creating same tool twice should be idempotent"""
        tool_name = f"idempotent-tool-{uuid.uuid4()}"
        tools = [
            {
                "name": tool_name,
                "version": "1.0.0",
                "inputSchema": {"type": "object"}
            }
        ]
        
        # First create
        resp1 = client.post(
            f"/v1/batch/tools/bulk-create?tenant_id={test_tenant_id}",
            json=tools,
            headers=admin_headers
        )
        assert resp1.status_code == 201
        result1 = resp1.json()["results"][0]
        assert result1["success"]
        assert result1["statusCode"] == 201
        tool_id_1 = result1["resourceId"]
        
        # Second create (idempotent)
        resp2 = client.post(
            f"/v1/batch/tools/bulk-create?tenant_id={test_tenant_id}",
            json=tools,
            headers=admin_headers
        )
        assert resp2.status_code == 201
        result2 = resp2.json()["results"][0]
        assert result2["success"]
        assert result2["statusCode"] == 200  # Returns existing
        tool_id_2 = result2["resourceId"]
        
        # Should return same tool ID
        assert tool_id_1 == tool_id_2

    def test_bulk_create_tools_conflict(
        self, client, admin_headers, test_tenant_id
    ):
        """Creating tool with same name/version but different schema should fail"""
        tool_name = f"conflict-tool-{uuid.uuid4()}"
        
        # First create
        tools1 = [
            {
                "name": tool_name,
                "version": "1.0.0",
                "inputSchema": {"type": "object", "properties": {"a": {"type": "string"}}}
            }
        ]
        resp1 = client.post(
            f"/v1/batch/tools/bulk-create?tenant_id={test_tenant_id}",
            json=tools1,
            headers=admin_headers
        )
        assert resp1.status_code == 201
        assert resp1.json()["successCount"] == 1
        
        # Second create with different schema
        tools2 = [
            {
                "name": tool_name,
                "version": "1.0.0",
                "inputSchema": {"type": "object", "properties": {"b": {"type": "number"}}}
            }
        ]
        resp2 = client.post(
            f"/v1/batch/tools/bulk-create?tenant_id={test_tenant_id}",
            json=tools2,
            headers=admin_headers
        )
        assert resp2.status_code == 201
        data = resp2.json()
        assert data["failureCount"] == 1
        result = data["results"][0]
        assert not result["success"]
        assert result["statusCode"] == 409  # Conflict

    def test_bulk_create_tools_exceeds_limit(
        self, client, admin_headers, test_tenant_id
    ):
        """Bulk create with >50 tools should fail"""
        tools = [
            {
                "name": f"tool-{i}",
                "version": "1.0.0",
                "inputSchema": {"type": "object"}
            }
            for i in range(51)
        ]
        
        resp = client.post(
            f"/v1/batch/tools/bulk-create?tenant_id={test_tenant_id}",
            json=tools,
            headers=admin_headers
        )
        assert resp.status_code == 400
        assert "50 tools" in resp.json()["detail"]
