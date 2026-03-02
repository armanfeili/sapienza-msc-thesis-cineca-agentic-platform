from typing import Any, Dict

import pytest


@pytest.mark.security
def test_admin_routes_require_bearer(client):
    """Every /v1/admin route should reject requests without Authorization."""
    resp = client.get("/v1/admin/jobs")
    assert resp.status_code == 401


@pytest.mark.security
def test_admin_routes_require_admin_scope(client, mint_token):
    token = mint_token(sub="non-admin", scopes=["user:me"], roles=[])
    resp = client.get("/v1/admin/jobs", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


@pytest.mark.security
def test_admin_routes_allow_admin_scope(client, bearer_headers):
    resp = client.get("/v1/admin/jobs", headers=bearer_headers)
    assert resp.status_code in {200, 201, 202, 204, 404}


def test_openapi_declares_single_httpbearer_scheme(app) -> None:
    spec: Dict[str, Any] = app.openapi()
    schemes = spec.get("components", {}).get("securitySchemes", {})
    assert list(schemes.keys()) == ["HTTPBearer"], schemes
    bearer = schemes["HTTPBearer"]
    assert bearer["type"] == "http"
    assert bearer["scheme"] == "bearer"
    assert bearer.get("bearerFormat") == "JWT"
    assert spec.get("security") == [{"HTTPBearer": []}]

    admin_paths = {path: ops for path, ops in spec.get("paths", {}).items() if path.startswith("/v1/admin")}
    assert admin_paths, "expected admin paths to be present in OpenAPI spec"
    for operations in admin_paths.values():
        for operation in operations.values():
            if not isinstance(operation, dict):
                continue
            security = operation.get("security", [])
            assert any("HTTPBearer" in req for req in security), f"admin op missing HTTPBearer security: {operation}"
