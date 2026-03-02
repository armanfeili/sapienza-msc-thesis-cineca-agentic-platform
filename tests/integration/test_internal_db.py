import os
import requests
import time
import pytest


BASE = os.environ.get("BASE_URL", "http://localhost:8000")
HEADERS = {"Authorization": f"Bearer {os.environ.get('ADMIN_TOKEN','ci-secret')}", "Content-Type": "application/json"}


@pytest.mark.skipif(not os.environ.get("ENABLE_ADMIN_ROUTES"), reason="admin routes disabled")
def test_create_db_job_and_cancel():
    # create job (idempotency tested via Idempotency-Key)
    url = f"{BASE}/v1/internal/db/jobs"
    body = {"source": "sample", "mode": "create"}
    r = requests.post(url, json=body, headers=HEADERS, timeout=10)
    assert r.status_code in (200, 201, 202)
    location = r.headers.get("Location")
    assert location, r.text

    # fetch status
    r2 = requests.get(f"{BASE}{location}", headers=HEADERS, timeout=5)
    assert r2.status_code == 200
    data = r2.json()
    assert "status" in data

    # cancel (idempotent)
    r3 = requests.delete(f"{BASE}{location}", headers=HEADERS, timeout=5)
    assert r3.status_code in (200, 204)

    # repeat cancel should be idempotent
    r4 = requests.delete(f"{BASE}{location}", headers=HEADERS, timeout=5)
    assert r4.status_code in (200, 204)
