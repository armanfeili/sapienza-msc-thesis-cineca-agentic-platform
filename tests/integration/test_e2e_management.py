import os
import time
import requests
import pytest


@pytest.mark.skipif(os.getenv("RUN_E2E") is None, reason="E2E tests disabled")
def test_e2e_management_flow():
    # Wait for app
    for _ in range(30):
        try:
            r = requests.get("http://localhost:8000/health", timeout=2)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(1)

    # Stage local manifest served by python -m http.server in CI (see workflow)
    resp = requests.post(
        "http://localhost:8000/model/builtins/stage",
        json={"url": "http://host.docker.internal:9000/ops/builtins/manifest.yaml"},
        timeout=10,
    )
    assert resp.status_code in (200, 201)

    act = requests.post("http://localhost:8000/model/builtins/activate", timeout=10)
    assert act.status_code in (200, 201)

    hist = requests.get("http://localhost:8000/model/builtins/history", timeout=10)
    assert hist.status_code == 200
    data = hist.json()
    assert isinstance(data, list)
    assert any("version" in h for h in data)
