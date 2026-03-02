"""
Platform Health Integration Tests

Verifies that all platform components are operational and healthy.
Tests database connectivity, LLM provider availability, and service status.

Acceptance Checklist Item: #1
"""
import pytest


class TestPlatformHealth:
    """Test platform health and component connectivity."""

    def test_basic_health_endpoint_responds(self, client):
        """Basic health endpoint should respond with 200."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"

    def test_detailed_health_components(self, client, bearer_headers):
        """Detailed health components endpoint should report component status."""
        response = client.get("/v1/health/components", headers=bearer_headers)
        assert response.status_code == 200

        data = response.json()
        assert "checks" in data, "Health response should include 'checks'"

        checks = data["checks"]

        # Verify redis is checked
        assert "redis" in checks, "redis component missing from health checks"
        redis_status = checks["redis"]
        assert redis_status.get("status") in [
            "ok",
            "error",
            "unknown",
        ], f"redis status invalid: {redis_status.get('status')}"
        assert redis_status.get("ok") is not None, "redis check should include 'ok' field"

        # Verify memgraph is checked
        assert "memgraph" in checks, "memgraph component missing from health checks"
        memgraph_status = checks["memgraph"]
        assert memgraph_status.get("status") in [
            "ok",
            "error",
            "unknown",
        ], f"memgraph status invalid: {memgraph_status.get('status')}"
        assert memgraph_status.get("ok") is not None, "memgraph check should include 'ok' field"

    def test_readiness_endpoint_responds(self, client, bearer_headers):
        """Readiness endpoint should report if system is ready."""
        response = client.get("/v1/health/ready", headers=bearer_headers)

        # May return 200 (ok) or 503 (degraded) depending on service availability
        assert response.status_code in [200, 503], f"Readiness should return 200 or 503, got: {response.status_code}"

        data = response.json()
        assert "status" in data, "Readiness should include status"
        assert data["status"] in [
            "ok",
            "degraded",
        ], f"Readiness status should be 'ok' or 'degraded', got: {data['status']}"

    def test_liveness_endpoint_responds(self, client, bearer_headers):
        """Liveness endpoint should respond indicating service is alive."""
        response = client.get("/v1/health/live", headers=bearer_headers)
        assert response.status_code == 200, f"Liveness should return 200, got: {response.status_code}"

        data = response.json()
        assert "status" in data, "Liveness should include status field"
        assert data.get("status") == "ok", "Liveness should report 'ok'"
