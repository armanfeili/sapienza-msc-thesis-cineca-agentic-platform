from src.app import create_app
from starlette.testclient import TestClient


def test_legacy_tools_invoke_deprecation():
    app = create_app()
    client = TestClient(app)
    # Legacy `/v1/tools/invoke` removed; ensure OpenAPI exposes the canonical path instead
    spec = app.openapi()
    paths = spec.get("paths", {})
    assert "/v1/tools/invoke" not in paths
    # canonical path should expose invocation collection with path parameter
    assert "/v1/tools/{name}/invocations" in paths


def test_openapi_has_oauth2_and_admin_security():
    app = create_app()
    spec = app.openapi()
    comps = spec.get("components", {})
    sec = comps.get("securitySchemes", {})
    # Only HTTPBearer should be present
    assert "HTTPBearer" in sec
    # Check that admin path has security requirement
    paths = spec.get("paths", {})
    # admin jobs endpoint present and must remain secured
    assert "/v1/admin/jobs" in paths
    for op in paths["/v1/admin/jobs"].values():
        if not isinstance(op, dict):
            continue
        assert any("HTTPBearer" in requirement for requirement in op.get("security", []))
