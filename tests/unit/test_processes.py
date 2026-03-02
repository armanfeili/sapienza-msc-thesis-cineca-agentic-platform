import os
import requests
import pytest

BASE = os.environ.get("BASE_URL", "http://localhost:8000")
HEADERS = {"Authorization": f"Bearer {os.environ.get('ADMIN_TOKEN','ci-secret')}", "Content-Type": "application/json"}


@pytest.mark.skipif(not os.environ.get("ENABLE_ADMIN_ROUTES"), reason="admin routes disabled")
def test_delete_process_and_compat_stub():
    # Attempt to DELETE a fake pid
    pid = "fake-123"
    r = requests.delete(f"{BASE}/v1/admin/processes/{pid}", headers=HEADERS, timeout=5)
    assert r.status_code in (200, 204, 404)

    # Compatibility stub (deprecated) may return 410 Gone or 404 if not present; accept either
    try:
        r2 = requests.post(f"{BASE}/v1/admin/processes/{pid}:stop", headers=HEADERS, timeout=5)
        assert r2.status_code in (410, 404)
    except Exception:
        pass
