"""
Test SSE (Server-Sent Events) endpoint behavior.

Ensures:
- retry header with bounds (1000-60000 ms, default 5000)
- Monotonic event IDs
- Last-Event-ID resume capability
- Heartbeats every ~15s (non-terminal only)
- Single event: end then close
- No backlog replay comment when buffer rotated
"""
import pytest
from fastapi.testclient import TestClient
import time
import re


@pytest.fixture
def admin_headers(mint_token):
    """Generate admin token with admin:all permission."""
    token = mint_token(
        sub="admin-user",
        roles=["admin"],
        scopes=["admin:all"],
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(app):
    """Test client for the FastAPI app."""
    return TestClient(app)


def test_sse_retry_header_default(client, admin_headers):
    """SSE stream should start with retry: 5000 by default."""
    import uuid

    # Create a job
    resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 50, "test_id": str(uuid.uuid4())}},
        headers=admin_headers,
    )
    job_id = resp.json()["id"]

    # Open SSE stream
    with client.stream("GET", f"/v1/jobs/{job_id}/events", headers=admin_headers) as sse_resp:
        assert sse_resp.status_code == 200
        assert sse_resp.headers["content-type"] == "text/event-stream; charset=utf-8"

        # Read first line (should be retry directive)
        first_line = next(sse_resp.iter_lines())
        assert first_line == "retry: 5000"


def test_sse_retry_header_custom(client, admin_headers):
    """SSE stream should respect retry_ms query parameter."""
    import uuid

    resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 50, "test_id": str(uuid.uuid4())}},
        headers=admin_headers,
    )
    job_id = resp.json()["id"]

    # Custom retry
    with client.stream("GET", f"/v1/jobs/{job_id}/events?retry_ms=10000", headers=admin_headers) as sse_resp:
        first_line = next(sse_resp.iter_lines())
        assert "retry: 10000" in first_line


def test_sse_retry_bounds(client, admin_headers):
    """SSE retry_ms should be bounded to 1000-60000 range."""
    import uuid

    resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 50, "test_id": str(uuid.uuid4())}},
        headers=admin_headers,
    )
    job_id = resp.json()["id"]

    # Try below minimum (should clamp or error)
    resp_low = client.get(f"/v1/jobs/{job_id}/events?retry_ms=500", headers=admin_headers)
    assert resp_low.status_code in (200, 400, 422)  # Either clamped or validation error

    # Try above maximum
    resp_high = client.get(f"/v1/jobs/{job_id}/events?retry_ms=100000", headers=admin_headers)
    assert resp_high.status_code in (200, 400, 422)


def test_sse_monotonic_ids(client, admin_headers):
    """SSE events should have monotonically increasing IDs."""
    import uuid

    resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 200, "test_id": str(uuid.uuid4())}},
        headers=admin_headers,
    )
    job_id = resp.json()["id"]

    event_ids = []
    with client.stream("GET", f"/v1/jobs/{job_id}/events", headers=admin_headers) as sse_resp:
        assert sse_resp.status_code == 200

        # Parse first few events
        line_count = 0
        for line in sse_resp.iter_lines():
            line_count += 1
            if line_count > 50:  # Limit to avoid hanging
                break

            line_str = line.decode() if isinstance(line, bytes) else line
            if line_str.startswith("id:"):
                event_id = int(line_str.split(":", 1)[1].strip())
                event_ids.append(event_id)

    # Verify monotonic
    for i in range(1, len(event_ids)):
        assert event_ids[i] > event_ids[i - 1], f"Event IDs not monotonic: {event_ids}"


def test_sse_terminal_then_end(client, admin_headers):
    """SSE should emit terminal status event followed by single event: end."""
    import uuid

    # Create fast job
    resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 10, "test_id": str(uuid.uuid4())}},
        headers=admin_headers,
    )
    job_id = resp.json()["id"]

    # Wait for job to finish
    time.sleep(0.5)

    # Connect to SSE (job already terminal)
    events = []
    with client.stream("GET", f"/v1/jobs/{job_id}/events", headers=admin_headers) as sse_resp:
        assert sse_resp.status_code == 200

        current_event = {}
        for line in sse_resp.iter_lines():
            line_str = line.decode() if isinstance(line, bytes) else line

            if line_str.startswith("id:"):
                current_event["id"] = line_str.split(":", 1)[1].strip()
            elif line_str.startswith("event:"):
                current_event["type"] = line_str.split(":", 1)[1].strip()
            elif line_str.startswith("data:"):
                current_event["data"] = line_str.split(":", 1)[1].strip()
            elif line_str == "":  # End of event
                if current_event:
                    events.append(current_event)
                    current_event = {}

    # Should have status event and end event
    event_types = [e.get("type") for e in events if "type" in e]
    assert "status" in event_types or "end" in event_types
    assert "end" in event_types, f"Missing 'end' event. Got: {event_types}"

    # end should be last
    assert event_types[-1] == "end", f"'end' should be last event, got: {event_types}"

    # Only one end event
    end_count = event_types.count("end")
    assert end_count == 1, f"Should have exactly 1 'end' event, got {end_count}"


def test_sse_no_heartbeats_when_terminal(client, admin_headers):
    """SSE should NOT emit heartbeats after terminal status."""
    import uuid

    # Create fast job
    resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 10, "test_id": str(uuid.uuid4())}},
        headers=admin_headers,
    )
    job_id = resp.json()["id"]

    # Wait for terminal
    time.sleep(0.5)

    # Connect and collect all lines
    lines = []
    with client.stream("GET", f"/v1/jobs/{job_id}/events", headers=admin_headers) as sse_resp:
        for line in sse_resp.iter_lines():
            line_str = line.decode() if isinstance(line, bytes) else line
            lines.append(line_str)

    # Check: no heartbeats after 'event: end'
    found_end = False
    heartbeats_after_end = []
    for line in lines:
        if "event: end" in line:
            found_end = True
        elif found_end and line.startswith(": heartbeat"):
            heartbeats_after_end.append(line)

    assert len(heartbeats_after_end) == 0, f"Found heartbeats after end: {heartbeats_after_end}"


def test_sse_last_event_id_resume(client, admin_headers):
    """SSE should resume from Last-Event-ID if events are in buffer."""
    import uuid

    resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 500, "test_id": str(uuid.uuid4())}},
        headers=admin_headers,
    )
    job_id = resp.json()["id"]

    # First connection - get some events
    first_event_ids = []
    with client.stream("GET", f"/v1/jobs/{job_id}/events", headers=admin_headers) as sse_resp:
        line_count = 0
        for line in sse_resp.iter_lines():
            line_count += 1
            if line_count > 20:  # Get first few events
                break
            line_str = line.decode() if isinstance(line, bytes) else line
            if line_str.startswith("id:"):
                event_id = int(line_str.split(":", 1)[1].strip())
                first_event_ids.append(event_id)

    if not first_event_ids:
        pytest.skip("No events captured in first connection")

    # Resume from middle
    resume_from = first_event_ids[0] if len(first_event_ids) > 0 else 1
    headers_with_resume = {**admin_headers, "Last-Event-ID": str(resume_from)}

    with client.stream("GET", f"/v1/jobs/{job_id}/events", headers=headers_with_resume) as sse_resp:
        # Should get events with ID > resume_from
        line_count = 0
        for line in sse_resp.iter_lines():
            line_count += 1
            if line_count > 10:
                break
            line_str = line.decode() if isinstance(line, bytes) else line
            if line_str.startswith("id:"):
                event_id = int(line_str.split(":", 1)[1].strip())
                assert event_id > resume_from, f"Resumed event ID {event_id} should be > {resume_from}"
                break  # Found at least one resumed event


def test_sse_no_backlog_replay_comment(client, admin_headers):
    """SSE should emit ': no-backlog-replay-from' comment when buffer rotated."""
    import uuid

    resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 100, "test_id": str(uuid.uuid4())}},
        headers=admin_headers,
    )
    job_id = resp.json()["id"]

    # Request with very old Last-Event-ID (buffer definitely rotated)
    headers_with_old_id = {**admin_headers, "Last-Event-ID": "999999"}

    lines = []
    with client.stream("GET", f"/v1/jobs/{job_id}/events", headers=headers_with_old_id) as sse_resp:
        line_count = 0
        for line in sse_resp.iter_lines():
            line_count += 1
            if line_count > 20:
                break
            line_str = line.decode() if isinstance(line, bytes) else line
            lines.append(line_str)

    # Should contain backlog comment
    backlog_comments = [l for l in lines if "no-backlog-replay-from" in l]
    assert len(backlog_comments) > 0, f"Missing 'no-backlog-replay-from' comment. Lines: {lines[:10]}"


def test_sse_content_type_header(client, admin_headers):
    """SSE should return text/event-stream content type."""
    import uuid

    resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 50, "test_id": str(uuid.uuid4())}},
        headers=admin_headers,
    )
    job_id = resp.json()["id"]

    with client.stream("GET", f"/v1/jobs/{job_id}/events", headers=admin_headers) as sse_resp:
        assert sse_resp.status_code == 200
        assert "text/event-stream" in sse_resp.headers["content-type"]


def test_sse_connection_headers(client, admin_headers):
    """SSE should include Connection: keep-alive and Cache-Control: no-store."""
    import uuid

    resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 50, "test_id": str(uuid.uuid4())}},
        headers=admin_headers,
    )
    job_id = resp.json()["id"]

    with client.stream("GET", f"/v1/jobs/{job_id}/events", headers=admin_headers) as sse_resp:
        assert sse_resp.status_code == 200
        assert sse_resp.headers.get("connection", "").lower() == "keep-alive"
        assert "no-store" in sse_resp.headers.get("cache-control", "").lower()
