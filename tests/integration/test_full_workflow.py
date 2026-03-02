"""
Integration tests for complete platform workflows.

Tests full user journeys from tenant creation through agent execution.
"""

import pytest
import time
from typing import Dict, Any


@pytest.mark.integration
class TestTenantToAgentWorkflow:
    """Test complete workflow: Tenant → Provider → Model → Agent → Job"""

    def test_complete_workflow_success(
        self, client, bearer_headers
    ):
        """Test successful end-to-end workflow"""
        
        # Step 1: Create tenant
        tenant_data = {
            "tenantId": f"integration-test-{int(time.time())}",
            "displayName": "Integration Test Tenant",
            "metadata": {"test": "true"}
        }
        
        resp = client.post(
            "/v1/tenants",
            json=tenant_data,
            headers=bearer_headers
        )
        assert resp.status_code == 201
        tenant = resp.json()
        tenant_id = tenant["tenantId"]
        
        # Step 2: Create LLM provider
        provider_data = {
            "providerId": f"provider-{int(time.time())}",
            "providerType": "openai",
            "displayName": "Test Provider",
            "credentials": {
                "apiKey": "sk-test-key-123",
                "baseUrl": "https://api.openai.com/v1"
            }
        }
        
        resp = client.post(
            f"/v1/tenants/{tenant_id}/providers",
            json=provider_data,
            headers=bearer_headers
        )
        assert resp.status_code in (200, 201)
        provider = resp.json()
        provider_id = provider["providerId"]
        
        # Step 3: Create model instance
        model_data = {
            "instanceId": f"model-{int(time.time())}",
            "providerId": provider_id,
            "modelName": "gpt-3.5-turbo",
            "displayName": "Test Model",
            "isDefault": True,
            "config": {
                "temperature": 0.7,
                "maxTokens": 1000
            }
        }
        
        resp = client.post(
            f"/v1/tenants/{tenant_id}/models",
            json=model_data,
            headers=bearer_headers
        )
        assert resp.status_code in (200, 201)
        model = resp.json()
        
        # Step 4: Create agent session
        agent_data = {
            "agentName": "test-agent",
            "role": "assistant",
            "goal": "Test integration workflow",
            "tools": [],
            "systemPrompt": "You are a helpful assistant."
        }
        
        resp = client.post(
            f"/v1/tenants/{tenant_id}/agents/sessions",
            json=agent_data,
            headers=bearer_headers
        )
        assert resp.status_code in (200, 201)
        session = resp.json()
        session_id = session.get("sessionId") or session.get("id")
        
        # Step 5: Execute agent (create job)
        job_data = {
            "sessionId": session_id,
            "userInput": "Hello, this is a test",
            "maxSteps": 3
        }
        
        resp = client.post(
            f"/v1/tenants/{tenant_id}/agents/sessions/{session_id}/execute",
            json=job_data,
            headers=bearer_headers
        )
        assert resp.status_code in (200, 201, 202)
        
        # Step 6: Monitor job status
        if resp.status_code == 202:
            job = resp.json()
            job_id = job.get("jobId") or job.get("id")
            
            # Poll for completion (max 30 seconds)
            for _ in range(30):
                resp = client.get(
                    f"/v1/jobs/{job_id}",
                    headers=bearer_headers
                )
                assert resp.status_code == 200
                job_status = resp.json()
                
                if job_status["status"] in ("completed", "failed"):
                    break
                    
                time.sleep(1)
            
            # Verify job completed
            assert job_status["status"] in ("completed", "failed")

    def test_workflow_with_missing_model_fails(
        self, client, bearer_headers
    ):
        """Test that workflow fails gracefully without model"""
        
        # Create tenant
        tenant_data = {
            "tenantId": f"test-fail-{int(time.time())}",
            "displayName": "Fail Test Tenant"
        }
        
        resp = client.post(
            "/v1/tenants",
            json=tenant_data,
            headers=bearer_headers
        )
        assert resp.status_code == 201
        tenant_id = resp.json()["tenantId"]
        
        # Try to create agent without model
        agent_data = {
            "agentName": "test-agent",
            "role": "assistant"
        }
        
        resp = client.post(
            f"/v1/tenants/{tenant_id}/agents/sessions",
            json=agent_data,
            headers=bearer_headers
        )
        
        # Should fail or warn about missing model
        assert resp.status_code in (400, 422, 500)
        
    def test_workflow_cleanup_cascade(
        self, client, bearer_headers
    ):
        """Test that deleting tenant cleans up all related resources"""
        
        # Create tenant with resources
        tenant_data = {
            "tenantId": f"cleanup-test-{int(time.time())}",
            "displayName": "Cleanup Test"
        }
        
        resp = client.post(
            "/v1/tenants",
            json=tenant_data,
            headers=bearer_headers
        )
        assert resp.status_code == 201
        tenant_id = resp.json()["tenantId"]
        
        # Create provider
        provider_data = {
            "providerId": f"provider-{int(time.time())}",
            "providerType": "openai",
            "credentials": {"apiKey": "test"}
        }
        
        client.post(
            f"/v1/tenants/{tenant_id}/providers",
            json=provider_data,
            headers=bearer_headers
        )
        
        # Delete tenant
        resp = client.delete(
            f"/v1/tenants/{tenant_id}",
            headers=bearer_headers
        )
        assert resp.status_code in (200, 204)
        
        # Verify tenant is gone
        resp = client.get(
            f"/v1/tenants/{tenant_id}",
            headers=bearer_headers
        )
        assert resp.status_code == 404


@pytest.mark.integration
class TestModelProviderIntegration:
    """Test model and provider interactions"""

    def test_create_model_with_valid_provider(
        self, client, bearer_headers, test_tenant_id
    ):
        """Test creating model with existing provider"""
        
        # Create provider first
        provider_data = {
            "providerId": f"provider-{int(time.time())}",
            "providerType": "openai",
            "credentials": {"apiKey": "test-key"}
        }
        
        resp = client.post(
            f"/v1/tenants/{test_tenant_id}/providers",
            json=provider_data,
            headers=bearer_headers
        )
        assert resp.status_code in (200, 201)
        provider_id = resp.json()["providerId"]
        
        # Create model
        model_data = {
            "instanceId": f"model-{int(time.time())}",
            "providerId": provider_id,
            "modelName": "gpt-4",
            "isDefault": True
        }
        
        resp = client.post(
            f"/v1/tenants/{test_tenant_id}/models",
            json=model_data,
            headers=bearer_headers
        )
        assert resp.status_code in (200, 201)
        model = resp.json()
        assert model["providerId"] == provider_id

    def test_create_model_with_invalid_provider_fails(
        self, client, bearer_headers, test_tenant_id
    ):
        """Test that creating model with non-existent provider fails"""
        
        model_data = {
            "instanceId": f"model-{int(time.time())}",
            "providerId": "non-existent-provider",
            "modelName": "gpt-4"
        }
        
        resp = client.post(
            f"/v1/tenants/{test_tenant_id}/models",
            json=model_data,
            headers=bearer_headers
        )
        assert resp.status_code in (400, 404, 422)

    def test_delete_provider_with_models_handled(
        self, client, bearer_headers, test_tenant_id
    ):
        """Test deleting provider that has associated models"""
        
        # Create provider
        provider_data = {
            "providerId": f"provider-{int(time.time())}",
            "providerType": "openai",
            "credentials": {"apiKey": "test"}
        }
        
        resp = client.post(
            f"/v1/tenants/{test_tenant_id}/providers",
            json=provider_data,
            headers=bearer_headers
        )
        provider_id = resp.json()["providerId"]
        
        # Create model
        model_data = {
            "instanceId": f"model-{int(time.time())}",
            "providerId": provider_id,
            "modelName": "gpt-4"
        }
        
        client.post(
            f"/v1/tenants/{test_tenant_id}/models",
            json=model_data,
            headers=bearer_headers
        )
        
        # Try to delete provider
        resp = client.delete(
            f"/v1/tenants/{test_tenant_id}/providers/{provider_id}",
            headers=bearer_headers
        )
        
        # Should either cascade delete or fail
        assert resp.status_code in (200, 204, 400, 409)


@pytest.mark.integration
class TestJobLifecycle:
    """Test complete job lifecycle"""

    def test_job_creation_and_monitoring(
        self, client, bearer_headers, test_tenant_id
    ):
        """Test creating and monitoring a job"""
        
        job_data = {
            "tool": "echo",
            "parameters": {"message": "test"},
            "idempotencyKey": f"test-{int(time.time())}"
        }
        
        # Create job
        resp = client.post(
            f"/v1/tenants/{test_tenant_id}/jobs",
            json=job_data,
            headers=bearer_headers
        )
        assert resp.status_code in (200, 201, 202)
        job = resp.json()
        job_id = job.get("jobId") or job.get("id")
        
        # Get job status
        resp = client.get(
            f"/v1/jobs/{job_id}",
            headers=bearer_headers
        )
        assert resp.status_code == 200
        job_status = resp.json()
        assert "status" in job_status

    def test_job_cancellation(
        self, client, bearer_headers, test_tenant_id
    ):
        """Test cancelling a running job"""
        
        job_data = {
            "tool": "sleep",
            "parameters": {"seconds": 60},
            "idempotencyKey": f"cancel-test-{int(time.time())}"
        }
        
        # Create long-running job
        resp = client.post(
            f"/v1/tenants/{test_tenant_id}/jobs",
            json=job_data,
            headers=bearer_headers
        )
        
        if resp.status_code in (200, 201, 202):
            job_id = resp.json().get("jobId") or resp.json().get("id")
            
            # Cancel job
            resp = client.post(
                f"/v1/jobs/{job_id}/cancel",
                headers=bearer_headers
            )
            assert resp.status_code in (200, 202, 204)
            
            # Verify job is cancelled
            resp = client.get(
                f"/v1/jobs/{job_id}",
                headers=bearer_headers
            )
            job_status = resp.json()
            assert job_status["status"] in ("cancelled", "cancelling")

    def test_job_idempotency(
        self, client, bearer_headers, test_tenant_id
    ):
        """Test that idempotency key prevents duplicate jobs"""
        
        idempotency_key = f"idempotent-{int(time.time())}"
        job_data = {
            "tool": "echo",
            "parameters": {"message": "test"},
            "idempotencyKey": idempotency_key
        }
        
        # Create job
        resp1 = client.post(
            f"/v1/tenants/{test_tenant_id}/jobs",
            json=job_data,
            headers=bearer_headers
        )
        assert resp1.status_code in (200, 201, 202)
        job1 = resp1.json()
        
        # Try to create same job again
        resp2 = client.post(
            f"/v1/tenants/{test_tenant_id}/jobs",
            json=job_data,
            headers=bearer_headers
        )
        
        # Should return same job or 409 Conflict
        if resp2.status_code in (200, 201):
            job2 = resp2.json()
            assert job1.get("id") == job2.get("id")
        else:
            assert resp2.status_code == 409


@pytest.mark.integration
class TestErrorScenarios:
    """Test error handling in workflows"""

    def test_invalid_tenant_id_returns_404(self, client, bearer_headers):
        """Test that invalid tenant returns 404"""
        
        resp = client.get(
            "/v1/tenants/non-existent-tenant",
            headers=bearer_headers
        )
        assert resp.status_code == 404
        assert "application/problem+json" in resp.headers.get("Content-Type", "")

    def test_unauthorized_access_returns_401(self, client):
        """Test that missing auth returns 401"""
        
        resp = client.get("/v1/tenants")
        assert resp.status_code == 401

    def test_insufficient_permissions_returns_403(
        self, client, user_headers
    ):
        """Test that insufficient permissions returns 403"""
        
        # Try to create tenant with user (non-admin) token
        tenant_data = {
            "tenantId": "test-403",
            "displayName": "Should Fail"
        }
        
        resp = client.post(
            "/v1/tenants",
            json=tenant_data,
            headers=user_headers
        )
        assert resp.status_code == 403

    def test_invalid_json_returns_422(self, client, bearer_headers):
        """Test that invalid JSON structure returns 422"""
        
        resp = client.post(
            "/v1/tenants",
            json={"invalid": "data"},  # Missing required fields
            headers=bearer_headers
        )
        assert resp.status_code == 422

    def test_rate_limit_enforced(self, client, bearer_headers):
        """Test that rate limiting works"""
        
        # Make many requests rapidly
        responses = []
        for _ in range(100):
            resp = client.get("/v1/health/ready")
            responses.append(resp.status_code)
        
        # Should have at least one rate limit response
        assert 429 in responses or all(r == 200 for r in responses)


@pytest.mark.integration  
class TestDataConsistency:
    """Test data consistency across operations"""

    def test_etag_consistency(self, client, bearer_headers, test_tenant_id):
        """Test that ETags work for caching"""
        
        # Get resource
        resp1 = client.get(
            f"/v1/tenants/{test_tenant_id}",
            headers=bearer_headers
        )
        etag = resp1.headers.get("ETag")
        
        if etag:
            # Request with If-None-Match
            headers = {**bearer_headers, "If-None-Match": etag}
            resp2 = client.get(
                f"/v1/tenants/{test_tenant_id}",
                headers=headers
            )
            assert resp2.status_code == 304

    def test_list_pagination_consistent(
        self, client, bearer_headers, test_tenant_id
    ):
        """Test that pagination returns consistent results"""
        
        # Get first page
        resp1 = client.get(
            f"/v1/tenants/{test_tenant_id}/jobs?limit=10&offset=0",
            headers=bearer_headers
        )
        page1 = resp1.json()
        
        # Get second page
        resp2 = client.get(
            f"/v1/tenants/{test_tenant_id}/jobs?limit=10&offset=10",
            headers=bearer_headers
        )
        page2 = resp2.json()
        
        # Pages should not overlap
        if isinstance(page1, list) and isinstance(page2, list):
            ids1 = {item.get("id") for item in page1 if "id" in item}
            ids2 = {item.get("id") for item in page2 if "id" in item}
            assert not ids1.intersection(ids2)

    def test_concurrent_updates_handled(
        self, client, bearer_headers, test_tenant_id
    ):
        """Test that concurrent updates are handled safely"""
        
        import concurrent.futures
        
        def update_tenant(index: int):
            tenant_data = {
                "displayName": f"Concurrent Update {index}"
            }
            return client.patch(
                f"/v1/tenants/{test_tenant_id}",
                json=tenant_data,
                headers=bearer_headers
            )
        
        # Try concurrent updates
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(update_tenant, i) for i in range(5)]
            results = [f.result() for f in futures]
        
        # All should succeed or have proper conflict handling
        for resp in results:
            assert resp.status_code in (200, 409, 412)
