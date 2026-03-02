import pytest


def _auth(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


@pytest.mark.unit
def test_get_invocation_304_includes_required_headers(client, mint_token):
    tok = mint_token(sub="alice", scopes=["tools:basic"])  # safe tool
    # Create an invocation first
    r = client.post(
        "/v1/tools/system.health/invocations",
        json={"args": {"action": "liveness"}},
        headers=_auth(tok),
    )
    assert r.status_code in (200, 201)
    eid = r.json()["event_id"]
    loc = r.headers.get("Location") or f"/v1/tools/system.health/invocations/{eid}"

    # Initial GET to obtain ETag
    g1 = client.get(loc, headers=_auth(tok))
    assert g1.status_code == 200
    etag = g1.headers.get("ETag")
    assert etag

    # Conditional GET expects 304 and required headers present
    g2 = client.get(loc, headers={**_auth(tok), "If-None-Match": etag})
    assert g2.status_code == 304
    assert g2.headers.get("ETag") == etag
    assert g2.headers.get("Vary") == "Authorization"
    assert g2.headers.get("Cache-Control", "").startswith("private")
    # X-Request-Id should mirror the event id
    assert g2.headers.get("X-Request-Id") == eid


@pytest.mark.unit
def test_tools_list_304_includes_required_headers(client, mint_token):
    tok = mint_token(sub="bob", scopes=["tools:basic"])  # basic
    r1 = client.get("/v1/tools", headers=_auth(tok))
    assert r1.status_code == 200
    etag = r1.headers.get("ETag")
    assert etag

    r2 = client.get("/v1/tools", headers={**_auth(tok), "If-None-Match": etag})
    assert r2.status_code == 304
    assert r2.headers.get("ETag") == etag
    assert r2.headers.get("Vary") == "Authorization"
    assert r2.headers.get("Cache-Control", "").startswith("private")
