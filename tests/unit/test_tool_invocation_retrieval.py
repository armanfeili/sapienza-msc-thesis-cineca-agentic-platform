import pytest


def _auth(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


@pytest.mark.unit
def test_post_then_get_parity_and_etag(client, mint_token):
    tok = mint_token(sub="alice", scopes=["tools:basic"])  # system.health is safe
    # POST an invocation
    r = client.post(
        "/v1/tools/system.health/invocations",
        json={"args": {"action": "liveness"}},
        headers=_auth(tok),
    )
    assert r.status_code in (200, 201)
    body = r.json()
    eid = body.get("event_id")
    assert eid
    loc = r.headers.get("Location") or f"/v1/tools/system.health/invocations/{eid}"

    # GET by Location should return same body
    g = client.get(loc, headers=_auth(tok))
    assert g.status_code == 200
    assert g.json() == body
    etag = g.headers.get("ETag")
    assert etag
    # Conditional GET 304
    g2 = client.get(loc, headers={**_auth(tok), "If-None-Match": etag})
    assert g2.status_code == 304


@pytest.mark.unit
def test_post_idempotent_replay_includes_location(client, mint_token):
    tok = mint_token(sub="alice", scopes=["tools:basic"])  # safe tool
    headers = _auth(tok)
    headers["Idempotency-Key"] = "idem-tool-1"
    r1 = client.post(
        "/v1/tools/system.health/invocations",
        json={"args": {"action": "liveness"}},
        headers=headers,
    )
    assert r1.status_code in (200, 201)
    loc1 = r1.headers.get("Location")
    assert loc1, "first response should include Location"

    # Replay
    r2 = client.post(
        "/v1/tools/system.health/invocations",
        json={"args": {"action": "liveness"}},
        headers=headers,
    )
    assert r2.status_code == 200
    loc2 = r2.headers.get("Location")
    assert loc2 == loc1, "idempotent replay must include same Location"


@pytest.mark.unit
def test_anti_enumeration_404_for_other_user(client, mint_token):
    # Alice creates an invocation
    alice = mint_token(sub="alice", scopes=["tools:basic"])  # basic
    r = client.post(
        "/v1/tools/system.health/invocations",
        json={"args": {"action": "liveness"}},
        headers=_auth(alice),
    )
    assert r.status_code in (200, 201)
    eid = r.json()["event_id"]
    loc = r.headers.get("Location") or f"/v1/tools/system.health/invocations/{eid}"

    # Bob cannot fetch it -> 404 (anti-enumeration)
    bob = mint_token(sub="bob", scopes=["tools:basic"])  # different user
    g = client.get(loc, headers=_auth(bob))
    assert g.status_code == 404


@pytest.mark.unit
def test_get_with_bad_uuid_returns_400(client, mint_token):
    tok = mint_token(sub="alice", scopes=["tools:basic"])  # basic
    g = client.get("/v1/tools/system.health/invocations/not-a-uuid", headers=_auth(tok))
    assert g.status_code == 400
