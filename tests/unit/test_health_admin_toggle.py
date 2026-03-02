import os
from fastapi.testclient import TestClient
from src.app import create_app
from src.routers.health import _is_ready, set_ready
from src.routers.health import _enable_admin


def test_admin_token_auth_and_toggle(monkeypatch):
    # Ensure admin routes enabled and ADMIN_TOKEN set
    monkeypatch.setenv("ENABLE_ADMIN_ROUTES", "1")
    monkeypatch.setenv("ADMIN_TOKEN", "secrettoken")
    app = create_app()
    client = TestClient(app)

    # Ensure initial ready is True
    set_ready(True)

    # Missing header -> 401
    r = client.post("/v1/health/startup/readiness", params={"state": "not-ready"})
    assert r.status_code == 401

    # Wrong header -> 403
    r = client.post("/v1/health/startup/readiness", params={"state": "not-ready"}, headers={"X-Admin-Token": "wrong"})
    assert r.status_code == 403

    try:
        # Correct header -> 200 and flips readiness
        r = client.post(
            "/v1/health/startup/readiness", params={"state": "not-ready"}, headers={"X-Admin-Token": "secrettoken"}
        )
        assert r.status_code == 200
        # GET readiness should reflect not-ready (503)
        r2 = client.get("/v1/health/ready")
        assert r2.status_code == 503
    finally:
        # Reset global readiness for other tests
        set_ready(True)


def test_jwt_admin_scope_toggle(monkeypatch, bearer_headers):
    # Enable admin routes, but unset ADMIN_TOKEN to force JWT path
    monkeypatch.setenv("ENABLE_ADMIN_ROUTES", "1")
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    app = create_app()
    client = TestClient(app)

    # Use minted admin token via fixture
    headers = bearer_headers

    # Ensure initial ready True
    set_ready(True)

    try:
        r = client.post("/v1/health/startup/readiness", params={"state": "not-ready"}, headers=headers)
        assert r.status_code == 200
        r2 = client.get("/v1/health/ready")
        assert r2.status_code == 503
    finally:
        set_ready(True)


def test_admin_routes_gated_from_openapi(monkeypatch):
    # Disable admin routes and ensure openapi does not expose the toggle
    monkeypatch.setenv("ENABLE_ADMIN_ROUTES", "0")
    # Ensure ADMIN_TOKEN not set
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    app = create_app()
    client = TestClient(app)

    # OpenAPI should not contain the admin toggle path
    spec = client.get("/v1/openapi.json").json()
    paths = spec.get("paths", {})
    assert "/v1/health/startup/readiness" not in paths
