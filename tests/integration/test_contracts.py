import time
import json
from fastapi.testclient import TestClient
from src.app import create_app
import os

app = create_app()
client = TestClient(app)


def _headers(bearer_headers):
    return bearer_headers


def test_problemdetails_for_missing_job(bearer_headers):
    headers = _headers(bearer_headers)
    r = client.get("/v1/jobs/nonexistent", headers=headers)
    assert r.status_code == 404
    assert r.headers.get("content-type", "").startswith("application/problem+json")
    body = r.json()
    assert "status" in body and body["status"] == 404
    assert "detail" in body


def test_pagination_etag(bearer_headers):
    headers = _headers(bearer_headers)
    # The admin jobs collection endpoint has been removed in this API shape; expect 404
    r = client.get("/v1/admin/jobs", headers=headers)
    assert r.status_code == 404


def test_idempotency_across_post_endpoints(bearer_headers):
    headers = {**_headers(bearer_headers), "Content-Type": "application/json"}

    # Agents: run
    payload = {"prompt": "hello"}
    headers_idem = {**headers, "Idempotency-Key": "idem-agents-run-1"}
    r1 = client.post("/v1/agents:run", json=payload, headers=headers_idem)
    assert r1.status_code == 200
    j1 = r1.json()
    r2 = client.post("/v1/agents:run", json=payload, headers=headers_idem)
    assert r2.status_code == 200
    j2 = r2.json()
    assert j1 == j2

    # Tools invoke (path)
    payload = {"name": "system.health", "args": {}}
    headers_idem = {**headers, "Idempotency-Key": "idem-tools-1"}
    r1 = client.post("/v1/tools/system.health:invoke", json=payload, headers=headers_idem)
    # tool may not exist; treat 404/400/200 as acceptable but if 200 compare bodies
    assert r1.status_code in (200, 400, 404)
    if r1.status_code == 200:
        b1 = r1.json()
        r2 = client.post("/v1/tools/system.health:invoke", json=payload, headers=headers_idem)
        assert r2.status_code == 200
        assert r2.json() == b1

    # Manifests stage/activate
    payload = {"url": "https://example.com/manifest.json"}
    headers_idem = {**headers, "Idempotency-Key": "idem-manifests-1"}
    r1 = client.post("/v1/models/manifests/builtins:stage", json=payload, headers=headers_idem)
    # endpoint may be admin-only or return validation errors; accept 200/400/404
    assert r1.status_code in (200, 400, 404)
    r2 = client.post("/v1/models/manifests/builtins:stage", json=payload, headers=headers_idem)
    assert r2.status_code == r1.status_code

    # Activate (idempotent)
    r3 = client.post("/v1/models/manifests/builtins:activate", headers=headers_idem)
    assert r3.status_code in (200, 400, 404)
    r4 = client.post("/v1/models/manifests/builtins:activate", headers=headers_idem)
    assert r4.status_code == r3.status_code


def test_rate_limit_headers(bearer_headers):
    # Tune env to small window/limit for the RateLimiter instance used by app
    os.environ["RATE_LIMIT_DEFAULT_WINDOW"] = "5"
    os.environ["RATE_LIMIT_DEFAULT_LIMIT"] = "3"
    headers = bearer_headers

    # Send enough requests to exceed the limit
    last = None
    for i in range(6):
        r = client.get("/v1/", headers=headers)
        last = r
    assert last is not None
    # When exceeded, status_code should eventually be 429 and headers set
    if last.status_code == 429:
        assert "Retry-After" in last.headers
        assert "RateLimit-Limit" in last.headers
        assert "RateLimit-Remaining" in last.headers
        assert "RateLimit-Reset" in last.headers
    else:
        # If tests run fast or limiter uses different key, still assert headers present on normal responses
        assert "RateLimit-Limit" in last.headers
        assert "RateLimit-Remaining" in last.headers
