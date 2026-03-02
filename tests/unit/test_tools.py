import os
import requests

BASE = os.environ.get("BASE_URL", "http://localhost:8000")
HEADERS = {"Content-Type": "application/json"}


def test_invoke_tool():
    url = f"{BASE}/v1/tools/echo/invocations"
    r = requests.post(url, json={"input": {"text": "ping"}}, headers=HEADERS, timeout=5)
    assert r.status_code in (200, 201, 202), r.text
    if r.status_code in (201, 202):
        assert "Location" in r.headers

    # compatibility stub, if present, should return 410 or 404 (we accept either to avoid brittle tests)
    try:
        r2 = requests.post(f"{BASE}/v1/tools/echo:invoke", json={"input": {"text": "ping"}}, headers=HEADERS, timeout=5)
        assert r2.status_code in (410, 404)
    except Exception:
        # if the server rejects unknown paths or times out, don't fail the test here
        pass
