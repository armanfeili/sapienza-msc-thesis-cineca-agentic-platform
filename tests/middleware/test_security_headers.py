"""
Tests for security headers middleware.

Verifies that all HTTP responses include proper security headers:
- X-Content-Type-Options
- X-Frame-Options
- X-XSS-Protection
- Referrer-Policy
- Permissions-Policy
- Strict-Transport-Security (production only)
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch

from src.middleware.security_headers import SecurityHeadersMiddleware


@pytest.fixture
def app():
    """Create test app with security headers middleware."""
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return {"message": "ok"}

    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


class TestSecurityHeaders:
    """Test security headers middleware."""

    def test_x_content_type_options(self, client):
        """X-Content-Type-Options header prevents MIME-sniffing."""
        response = client.get("/test")
        assert response.headers["X-Content-Type-Options"] == "nosniff"

    def test_x_frame_options(self, client):
        """X-Frame-Options header prevents clickjacking."""
        response = client.get("/test")
        assert response.headers["X-Frame-Options"] == "DENY"

    def test_x_xss_protection(self, client):
        """X-XSS-Protection header enables browser XSS filter."""
        response = client.get("/test")
        assert response.headers["X-XSS-Protection"] == "1; mode=block"

    def test_referrer_policy(self, client):
        """Referrer-Policy header controls referrer information."""
        response = client.get("/test")
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    def test_permissions_policy(self, client):
        """Permissions-Policy header restricts dangerous browser features."""
        response = client.get("/test")
        policy = response.headers["Permissions-Policy"]
        assert "geolocation=()" in policy
        assert "microphone=()" in policy
        assert "camera=()" in policy
        assert "payment=()" in policy
        assert "usb=()" in policy

    @patch("src.middleware.security_headers.settings")
    def test_hsts_in_production(self, mock_settings, app):
        """HSTS header added only in production."""
        mock_settings.APP_ENV = "prod"
        client = TestClient(app)

        response = client.get("/test")
        assert "Strict-Transport-Security" in response.headers
        hsts = response.headers["Strict-Transport-Security"]
        assert "max-age=31536000" in hsts
        assert "includeSubDomains" in hsts
        assert "preload" in hsts

    @patch("src.middleware.security_headers.settings")
    def test_no_hsts_in_development(self, mock_settings, app):
        """HSTS header NOT added in development."""
        mock_settings.APP_ENV = "dev"
        client = TestClient(app)

        response = client.get("/test")
        assert "Strict-Transport-Security" not in response.headers

    def test_headers_on_all_routes(self, client, app):
        """Security headers applied to all routes."""

        # Add another route
        @app.get("/another")
        async def another_endpoint():
            return {"data": "test"}

        client = TestClient(app)  # Recreate client with new route

        # Test both routes
        for path in ["/test", "/another"]:
            response = client.get(path)
            assert response.headers["X-Content-Type-Options"] == "nosniff"
            assert response.headers["X-Frame-Options"] == "DENY"

    def test_headers_on_errors(self, app):
        """Security headers applied even on error responses."""

        @app.get("/error")
        async def error_endpoint():
            from fastapi import HTTPException

            raise HTTPException(status_code=500, detail="Test error")

        client = TestClient(app)
        response = client.get("/error")

        # Should still have security headers despite 500 error
        assert response.status_code == 500
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"

    def test_headers_on_not_found(self, client):
        """Security headers applied even on 404 responses."""
        response = client.get("/nonexistent")

        assert response.status_code == 404
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
