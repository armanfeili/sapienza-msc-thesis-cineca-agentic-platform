import time
import pytest


def _create_job(client, bearer_headers, idem_key="t-cache-1"):
    r = client.post(
        "/v1/jobs", headers={**bearer_headers, "Idempotency-Key": idem_key}, json={"type": "demo", "payload": {"x": 1}}
    )
    assert r.status_code in (202, 200)
    body = r.json()
    job_id = body["id"]
    return job_id


def test_get_job_has_etag_and_cache_headers(client, bearer_headers, settings_patch):
    # Ensure deterministic quick completion
    settings_patch(JOB_SIM_SLEEP_MS=5)
    job_id = _create_job(client, bearer_headers, idem_key="t-cache-2")
    # GET job
    r = client.get(f"/v1/jobs/{job_id}", headers=bearer_headers)
    assert r.status_code == 200
    # Headers
    assert "etag" in {k.lower() for k in r.headers.keys()}
    assert r.headers.get("Cache-Control") == "private, max-age=15"
    assert r.headers.get("Vary") == "Authorization"
    assert r.headers.get("X-Request-Id") == job_id
    # Body shape
    body = r.json()
    assert body["id"] == job_id
    assert "status" in body


def test_get_job_returns_304_on_if_none_match(client, bearer_headers, settings_patch):
    settings_patch(JOB_SIM_SLEEP_MS=5)
    job_id = _create_job(client, bearer_headers, idem_key="t-cache-3")
    r1 = client.get(f"/v1/jobs/{job_id}", headers=bearer_headers)
    etag = r1.headers.get("ETag")
    assert etag, "Expected ETag header"
    r2 = client.get(f"/v1/jobs/{job_id}", headers={**bearer_headers, "If-None-Match": etag})
    assert r2.status_code == 304
    # 304 should echo these headers
    assert r2.headers.get("ETag") == etag
    assert r2.headers.get("Cache-Control") == "private, max-age=15"
    assert r2.headers.get("Vary") == "Authorization"
    assert r2.headers.get("X-Request-Id") == job_id
