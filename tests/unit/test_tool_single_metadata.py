import pytest


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.unit
def test_get_tool_etag_and_304(client, mint_token):
    # Tools catalog has safe tool system.health; assume present
    tok = mint_token(sub="user1", scopes=["tools:basic"])  # basic visibility
    r1 = client.get("/v1/tools/system.health", headers=_auth(tok))
    # For non-admins, if system.health is visible and invokable, it should return 200
    assert r1.status_code == 200
    etag = r1.headers.get("ETag")
    assert etag, "ETag must be present on GET /v1/tools/{name}"
    assert r1.headers.get("Vary") == "Authorization"
    assert r1.headers.get("Cache-Control", "").startswith("private")

    # Conditional GET should return 304 with the same headers
    r2 = client.get("/v1/tools/system.health", headers={**_auth(tok), "If-None-Match": etag})
    assert r2.status_code == 304
    assert r2.headers.get("ETag") == etag
    assert r2.headers.get("Vary") == "Authorization"
    assert r2.headers.get("Cache-Control", "").startswith("private")


@pytest.mark.unit
def test_get_tool_404_for_namespace_or_invisible(client, mint_token):
    # A basic-only user should not see admin tools (e.g., security.*)
    tok = mint_token(sub="user1", scopes=["tools:basic"])  # basic
    r = client.get("/v1/tools/security.permissions", headers=_auth(tok))
    assert r.status_code == 404
