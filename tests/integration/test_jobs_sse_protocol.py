import re
import pytest


def _create_job(client, bearer_headers, idem_key="t-sse-1"):
    r = client.post(
        "/v1/jobs", headers={**bearer_headers, "Idempotency-Key": idem_key}, json={"type": "demo", "payload": {"x": 1}}
    )
    assert r.status_code in (202, 200)
    return r.json()["id"]


def test_sse_emits_retry_id_and_event_lines(client, bearer_headers):
    job_id = _create_job(client, bearer_headers, idem_key="t-sse-2")
    # Open SSE stream
    with client.stream("GET", f"/v1/jobs/{job_id}/events", headers=bearer_headers) as resp:
        assert resp.status_code == 200
        # Collect a small number of lines
        collected = []
        for chunk in resp.iter_text():
            for line in chunk.splitlines():
                collected.append(line)
                if len(collected) >= 6:
                    break
            if len(collected) >= 6:
                break
    flat = [l for l in collected if l.strip()]
    # Look for retry prefix somewhere in first few lines
    assert any(l.startswith("retry: 5000") for l in flat), f"retry line missing in {flat}"
    # Expect an id line then event line
    assert any(re.match(r"id: \\d+", l) for l in flat), f"no id: line found in {flat}"
    assert any(l.startswith("event:") for l in flat), f"no event: line found in {flat}"
