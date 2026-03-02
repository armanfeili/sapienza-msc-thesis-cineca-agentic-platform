import os
import requests
import pytest

BASE = os.environ.get("BASE_URL", "http://localhost:8000")

# Get Auth0 token from environment (provided by user)
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")
if not ADMIN_TOKEN:
    pytest.skip("ADMIN_TOKEN environment variable not set", allow_module_level=True)

HEADERS = {"Content-Type": "application/json", "Authorization": f"Bearer {ADMIN_TOKEN}"}


def test_create_agent_run():
    url = f"{BASE}/v1/agent-runs"
    body = {"prompt": "hello"}  # Fixed: prompt should be at top level, not nested in input
    r = requests.post(url, json=body, headers=HEADERS, timeout=10)
    assert r.status_code in (200, 201, 202), r.text
    if r.status_code in (201, 202):
        assert "Location" in r.headers


def test_session_lifecycle():
    # create session
    url = f"{BASE}/v1/agents/sessions"
    r = requests.post(url, json={"name": "test-session"}, headers=HEADERS, timeout=5)
    assert r.status_code in (200, 201)
    loc = r.headers.get("Location")
    if not loc:
        pytest.skip("session Location header not present; server may be in legacy mode")

    # Location might be a full URL or a path - handle both cases
    if loc.startswith("http"):
        # Full URL returned, extract the path
        from urllib.parse import urlparse

        parsed = urlparse(loc)
        loc = parsed.path

    # post a step
    step_url = f"{BASE}{loc}/steps"
    r2 = requests.post(
        step_url,
        json={"type": "message", "message": "step1", "input": {"text": "hello"}},  # Fixed: must include type field
        headers=HEADERS,
        timeout=5,
    )
    assert r2.status_code in (200, 201, 202)

    # delete session (idempotent)
    r3 = requests.delete(f"{BASE}{loc}", headers=HEADERS, timeout=5)
    assert r3.status_code in (200, 204, 404)

    # repeat delete
    r4 = requests.delete(f"{BASE}{loc}", headers=HEADERS, timeout=5)
    assert r4.status_code in (200, 204, 404)
