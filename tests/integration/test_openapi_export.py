import json
from typing import Any, Dict

import pytest
from httpx import AsyncClient, ASGITransport


def _is_openapi(doc: Dict[str, Any]) -> bool:
    return isinstance(doc, dict) and "openapi" in doc and "paths" in doc


@pytest.mark.anyio
async def test_openapi_schema_object(app):
    """
    The FastAPI app should expose a valid OpenAPI schema object via app.openapi().
    """
    schema = app.openapi()
    assert _is_openapi(schema), "app.openapi() did not return a valid OpenAPI document"
    # basic shape
    assert isinstance(schema["paths"], dict)
    assert len(schema["paths"]) >= 1

    # Heuristic: health route should normally exist
    health_like = [p for p in schema["paths"].keys() if "health" in p]
    assert health_like, f"expected a health-like path in OpenAPI, found: {list(schema['paths'].keys())[:10]}"


@pytest.mark.anyio
async def test_openapi_json_endpoint_matches_object(app):
    """
    /openapi.json should return JSON that matches (or is at least consistent with) app.openapi().
    """
    expected = app.openapi()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/openapi.json")
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/json")
        payload = r.json()

    assert _is_openapi(payload)
    # Compare a few stable fields
    assert payload.get("openapi") == expected.get("openapi")
    assert isinstance(payload.get("paths"), dict) and len(payload["paths"]) >= 1
    # Ensure all expected health-like paths exist
    exp_health = [p for p in expected["paths"].keys() if "health" in p]
    for p in exp_health:
        assert p in payload["paths"], f"missing expected path {p} in /openapi.json"


@pytest.mark.anyio
async def test_docs_and_redoc_render(app):
    """
    The docs UIs should render (HTML) even in test mode.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r_docs = await client.get("/docs")
        r_redoc = await client.get("/redoc")

    # FastAPI serves HTML for both, ensure they load
    assert r_docs.status_code == 200
    assert "text/html" in r_docs.headers.get("content-type", "")
    assert "<html" in r_docs.text.lower()
    assert "swagger" in r_docs.text.lower() or "rapidoc" in r_docs.text.lower()

    assert r_redoc.status_code == 200
    assert "text/html" in r_redoc.headers.get("content-type", "")
    assert "<html" in r_redoc.text.lower()
    assert "redoc" in r_redoc.text.lower() or "rapidoc" in r_redoc.text.lower()
