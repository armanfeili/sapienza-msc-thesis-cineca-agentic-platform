import pytest


def _create_admin_job(client, bearer_headers):
    r = client.post(
        "/v1/jobs", headers={**bearer_headers, "Idempotency-Key": "t-rbac-1"}, json={"type": "demo", "payload": {}}
    )
    assert r.status_code in (202, 200)
    return r.json()["id"]


@pytest.fixture
def user_headers(mint_token):
    token = mint_token(sub="user-basic", scopes=["user:me"], roles=[])  # no admin:all
    return {"Authorization": f"Bearer {token}"}


def test_jobs_requires_admin_scope(client, bearer_headers, user_headers):
    job_id = _create_admin_job(client, bearer_headers)
    # Unauthenticated
    r_unauth = client.get(f"/v1/jobs/{job_id}")
    assert r_unauth.status_code == 401

    # Non-admin -> 404 (anti-enumeration: don't reveal job exists)
    r_forbidden = client.get(f"/v1/jobs/{job_id}", headers=user_headers)
    assert r_forbidden.status_code == 404

    # Admin OK
    r_ok = client.get(f"/v1/jobs/{job_id}", headers=bearer_headers)
    assert r_ok.status_code == 200

    # DELETE endpoints - also 404 for anti-enumeration
    r_del_forbidden = client.delete(f"/v1/jobs/{job_id}", headers=user_headers)
    assert r_del_forbidden.status_code == 404

    # SSE endpoint (non-admin) - also 404 for anti-enumeration
    with client.stream("GET", f"/v1/jobs/{job_id}/events", headers=user_headers) as sse_resp:
        # SSE should also enforce 404 (anti-enumeration)
        assert sse_resp.status_code == 404
