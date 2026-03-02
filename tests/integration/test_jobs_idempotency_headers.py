import pytest


def test_post_jobs_idempotency_headers(client, bearer_headers):
    headers = {**bearer_headers, "Idempotency-Key": "t-idem-1"}
    payload = {"type": "demo", "payload": {"x": 5}}
    r1 = client.post("/v1/jobs", headers=headers, json=payload)
    assert r1.status_code == 202
    job_id = r1.json()["id"]
    loc1 = r1.headers.get("Location")
    assert r1.headers.get("Idempotency-Key") == "t-idem-1"
    assert r1.headers.get("Idempotency-Replayed") == "false"
    assert r1.headers.get("Cache-Control") == "no-store"
    assert r1.headers.get("X-Request-Id") == job_id

    r2 = client.post("/v1/jobs", headers=headers, json=payload)
    assert r2.status_code == 200
    assert r2.headers.get("Idempotency-Replayed") == "true"
    assert r2.headers.get("Location") == loc1
    assert r2.json()["id"] == job_id
