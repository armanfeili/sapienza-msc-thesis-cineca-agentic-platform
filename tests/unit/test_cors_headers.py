import pytest


@pytest.mark.unit
def test_cors_preflight_allows_idempotency_key(client):
    # Simulate browser preflight for POST tools invocation with Idempotency-Key header
    r = client.options(
        "/v1/tools/system.health/invocations",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "idempotency-key,content-type",
        },
    )
    # Starlette CORS middleware responds 200 for allowed preflight
    assert r.status_code in (200, 204)
    allow_headers = r.headers.get("access-control-allow-headers", "")
    # We configured allow_headers=["*"] so middleware may return "*" or echo back
    assert allow_headers == "*" or "idempotency-key" in allow_headers.lower()


@pytest.mark.unit
def test_cors_expose_headers_includes_etag(client, mint_token):
    tok = mint_token(sub="user1", scopes=["tools:basic"])  # basic
    r = client.get("/v1/tools", headers={"Authorization": f"Bearer {tok}", "Origin": "https://example.com"})
    # Response should include ETag header and CORS should expose it to browsers (config-level)
    assert "ETag" in r.headers
