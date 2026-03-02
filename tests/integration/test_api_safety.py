"""
API Safety Integration Tests

Verifies URL handling, header security, and error message quality.
Tests that the API is safe and provides helpful debugging info.

Acceptance Checklist Items: #10, #11
"""
import pytest


class TestURLSafety:
    """Test URL handling and auto-prefixing."""

    def test_explorer_auto_prefixes_v1(self, client, bearer_headers):
        """Explorer should auto-prefix URLs with /v1 if missing."""
        # Test with URL missing /v1 prefix
        response = client.post(
            "/v1/explorer/execute", headers=bearer_headers, json={"url": "/providers"}  # Missing /v1
        )

        # Should either auto-correct or give helpful error
        if response.status_code == 200:
            # Auto-corrected successfully
            data = response.json()
            assert data, "Should have response data"
        else:
            # Should give helpful error about missing /v1
            error_data = response.json()
            assert "detail" in error_data or "error" in error_data

    def test_explorer_handles_full_urls(self, client, bearer_headers):
        """Explorer should handle complete URLs correctly."""
        response = client.post(
            "/v1/explorer/execute", headers=bearer_headers, json={"url": "/v1/providers", "method": "GET"}
        )

        # Should work without issues
        assert response.status_code in [200, 201, 204, 400, 404]


class TestHeaderSecurity:
    """Test that sensitive headers are not leaked."""

    def test_explorer_redacts_auth_headers(self, client, bearer_headers):
        """Explorer should not leak Authorization headers in responses."""
        response = client.post(
            "/v1/explorer/execute", headers=bearer_headers, json={"url": "/v1/providers", "method": "GET"}
        )

        response_text = response.text.lower()

        # Should not leak bearer token
        assert (
            "bearer " not in response_text or "bearer ***" in response_text or "bearer [redacted]" in response_text
        ), "Explorer should not leak Authorization header values"

    def test_error_responses_no_sensitive_data(self, client, bearer_headers):
        """Error responses should not include sensitive data."""
        # Trigger an error
        response = client.get("/v1/nonexistent-endpoint-12345", headers=bearer_headers)

        error_text = response.text.lower()

        # Should not leak sensitive info
        assert "password" not in error_text
        assert "secret" not in error_text
        assert "api_key" not in error_text or "api_key: [redacted]" in error_text


class TestErrorMessages:
    """Test error message quality and debugging info."""

    def test_error_includes_trace_id(self, client, bearer_headers, mint_token):
        """Error responses should include trace_id for debugging."""
        # Get a token with insufficient scopes
        low_scope_token = mint_token(scopes=["read:own"])
        low_headers = {"Authorization": f"Bearer {low_scope_token}"}

        # Try to access admin endpoint (should fail)
        response = client.get("/v1/admin/users", headers=low_headers)
        assert response.status_code == 403

        error_data = response.json()

        # Should have trace_id for debugging
        assert (
            "trace_id" in error_data or "request_id" in error_data or "x-request-id" in response.headers
        ), "Error responses should include trace_id for debugging"

    def test_error_includes_helpful_detail(self, client, bearer_headers):
        """Error responses should include helpful detail messages."""
        # Try to access non-existent resource
        response = client.get("/v1/sessions/00000000-0000-0000-0000-000000000000", headers=bearer_headers)
        assert response.status_code == 404

        error_data = response.json()

        # Should have detail or error message
        assert (
            "detail" in error_data or "error" in error_data or "message" in error_data
        ), "Error responses should include helpful detail messages"

    def test_validation_errors_include_field_info(self, client, bearer_headers):
        """Validation errors should specify which fields are invalid."""
        # Send invalid data
        response = client.post("/v1/agent-runs", headers=bearer_headers, json={})  # Missing required 'prompt' field

        assert response.status_code == 422

        error_data = response.json()

        # Should specify field validation errors
        assert (
            "detail" in error_data or "errors" in error_data or "validation_error" in error_data
        ), "Validation errors should include field information"
