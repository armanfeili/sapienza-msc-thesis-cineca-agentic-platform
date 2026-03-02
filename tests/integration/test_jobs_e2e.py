import time
import json
from fastapi.testclient import TestClient
from src.app import create_app
import os

app = create_app()
client = TestClient(app)


def _get_headers(bearer_headers):
    return {**bearer_headers, "Content-Type": "application/json"}


def test_create_job_202_and_poll_and_sse(bearer_headers):
    headers = _get_headers(bearer_headers)

    # Create job without idempotency key
    payload = {"type": "demo", "payload": {}}
    r = client.post("/v1/jobs:create", json=payload, headers=headers)
    assert r.status_code == 202
    assert "Location" in r.headers
    loc = r.headers["Location"]
    jid = r.json().get("id")
    assert r.headers.get("X-Request-Id") == jid
    assert r.headers.get("Idempotency-Replayed") == "false"
    assert r.headers.get("Cache-Control") == "no-store"

    # Poll the job until finished (with small backoff)
    for _ in range(20):
        pr = client.get(loc, headers=headers)
        assert pr.status_code in (200, 404)
        if pr.status_code == 404:
            # ProblemDetails format
            assert pr.headers.get("content-type", "").startswith("application/problem+json")
            break
        data = pr.json()
        if data.get("status") == "finished":
            break
        time.sleep(0.05)
    else:
        raise AssertionError("job did not finish in time")

    # Idempotency: create job again with same Idempotency-Key should return same job id
    idem_headers = headers.copy()
    idem_headers["Idempotency-Key"] = "idem-test-1"
    r1 = client.post("/v1/jobs:create", json=payload, headers=idem_headers)
    assert r1.status_code == 202
    loc1 = r1.headers.get("Location")

    r2 = client.post("/v1/jobs:create", json=payload, headers=idem_headers)
    assert r2.status_code in (200, 202)  # 200 preferred for replay
    loc2 = r2.headers.get("Location")
    assert loc1 == loc2
    # Replay headers
    assert r2.headers.get("Idempotency-Replayed") == "true"
    assert r2.headers.get("Idempotency-Key") == idem_headers["Idempotency-Key"]
    assert r2.headers.get("Cache-Control") == "no-store"


def test_job_events_sse(bearer_headers):
    headers = _get_headers(bearer_headers)
    payload = {"type": "demo", "payload": {}}

    # Create job
    r = client.post("/v1/jobs:create", json=payload, headers=headers)
    assert r.status_code == 202
    loc = r.headers["Location"]
    job_id = loc.rsplit("/", 1)[-1]

    # Consume SSE stream (should receive running and finished events)
    with client.stream("GET", f"/v1/jobs/{job_id}/events", headers=headers) as stream:
        events = []
        for line in stream.iter_lines():
            if not line:
                continue
            text = line.decode() if isinstance(line, bytes) else line
            if text.startswith("data:"):
                payload = text.split("data:", 1)[1].strip()
                try:
                    obj = json.loads(payload)
                except Exception:
                    obj = {"raw": payload}
                events.append(obj)
            if any(e.get("status") == "finished" for e in events if isinstance(e, dict)):
                break
    assert any(isinstance(e, dict) and e.get("status") == "running" for e in events) or any(
        isinstance(e, dict) and e.get("status") == "finished" for e in events
    )
