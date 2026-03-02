import os
import pytest

try:
    from fastapi.testclient import TestClient
except Exception:
    TestClient = None


def _import_app():
    try:
        from src.app import app

        return app
    except Exception:
        from src.app import create_app

        return create_app()


@pytest.mark.integration
def test_health_head_endpoints():
    if TestClient is None:
        pytest.skip("fastapi.testclient not available")

    app = _import_app()
    with TestClient(app) as client:
        # root endpoints
        r = client.head("/health")
        assert r.status_code in (200, 204, 301, 302)
        r = client.head("/ready")
        assert r.status_code in (200, 204, 503, 301, 302)

        # v1 endpoints
        r = client.head("/v1/health/live")
        assert r.status_code in (200, 204, 301, 302)
        r = client.head("/v1/health/ready")
        assert r.status_code in (200, 204, 503, 301, 302)
        r = client.head("/v1/health/startup")
        assert r.status_code in (200, 204, 301, 302)
