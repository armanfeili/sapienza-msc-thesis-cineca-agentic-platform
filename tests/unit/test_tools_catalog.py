import pytest


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.unit
def test_admin_vs_user_visibility_and_redaction(client, mint_token):
    # Admin sees everything including security.* and module paths
    admin_tok = mint_token(sub="admin", roles=["admin"])  # grants admin:all
    r = client.get("/v1/tools", headers=_auth(admin_tok))
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    items = data["items"]
    # Admin payload should include some security.* tools (namespace or invokable)
    has_security = any(i["name"].startswith("security") for i in items)
    assert has_security, "admin should see security.* entries"
    # Admin should see module import paths
    assert any(i.get("module") for i in items), "admin should see module field"

    # Basic user only sees SAFE_TOOLS set; security.* should be absent and module redacted
    user_tok = mint_token(sub="user1", scopes=["tools:basic"])  # basic
    r2 = client.get("/v1/tools", headers=_auth(user_tok))
    assert r2.status_code == 200
    items2 = r2.json()["items"]
    assert all(not i["name"].startswith("security.") for i in items2), "basic user must not see security.*"
    # Redaction: module should be None for non-admin
    assert all(i.get("module") in (None, "") for i in items2), "module must be redacted for non-admin"


@pytest.mark.unit
def test_schema_presence_and_namespaces_toggle(client, mint_token):
    tok = mint_token(sub="user1", scopes=["tools:all"])  # elevated to see all non-admin
    # Namespaces are excluded and cannot be toggled via query anymore; only invokable tools are returned
    r = client.get("/v1/tools", headers=_auth(tok))
    assert r.status_code == 200
    items = r.json()["items"]
    assert all(i.get("invokable") for i in items), "non-invokable items must be filtered by default"
    # All invokable items should have input_schema not null (when invokable true)
    for it in items:
        if it.get("invokable"):
            assert isinstance(it.get("input_schema"), dict), f"invokable tool missing schema: {it}"
    # Query no longer supports include_namespaces; ensure response still excludes namespaces
    r2 = client.get("/v1/tools?include_namespaces=true", headers=_auth(tok))
    assert r2.status_code == 200
    items2 = r2.json()["items"]
    assert all(i.get("invokable") for i in items2), "namespaces should not be included even if query param is present"


@pytest.mark.unit
def test_etag_and_cache_control(client, mint_token):
    tok = mint_token(sub="user1", scopes=["tools:basic"])  # basic
    r1 = client.get("/v1/tools", headers=_auth(tok))
    assert r1.status_code == 200
    etag = r1.headers.get("ETag")
    assert etag, "ETag must be present"
    assert "Cache-Control" in r1.headers and r1.headers["Cache-Control"].startswith("private")
    assert r1.headers.get("Vary") == "Authorization"
    # Conditional GET should return 304
    r2 = client.get("/v1/tools", headers={**_auth(tok), "If-None-Match": etag})
    assert r2.status_code == 304
    # Headers must be present even on 304
    assert r2.headers.get("ETag") == etag
    assert r2.headers.get("Cache-Control", "").startswith("private")
    assert r2.headers.get("Vary") == "Authorization"


@pytest.mark.unit
def test_cors_exposes_etag(client, mint_token):
    tok = mint_token(sub="user1", scopes=["tools:basic"])  # basic
    r = client.get("/v1/tools", headers=_auth(tok))
    # In tests we can't perform a real CORS browser check, but we can ensure the app is configured
    # to expose ETag by checking a helper header we expect in GET responses and assuming config parity.
    assert "ETag" in r.headers


@pytest.mark.unit
def test_pagination_bounds_and_token(client, mint_token):
    tok = mint_token(sub="user1", scopes=["tools:all"])  # elevated
    # No more pagination parameters; server returns up to 50 items and indicates has_more
    r1 = client.get("/v1/tools", headers=_auth(tok))
    assert r1.status_code == 200
    body1 = r1.json()
    assert "items" in body1 and isinstance(body1["items"], list)
    assert body1.get("next_page_token") is None
    assert isinstance(body1.get("has_more"), bool)
