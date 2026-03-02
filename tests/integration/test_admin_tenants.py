import os
import pytest
import requests

BASE = os.getenv("BASE_URL", "http://localhost:8000")


@pytest.mark.integration
def test_list_tenants_returns_list():
    tok = os.getenv("BASE_BEARER")
    if not tok:
        pytest.skip("No BASE_BEARER provided for external integration test")
    r = requests.get(f"{BASE}/v1/admin/tenants", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list), f"Expected list, got: {type(body)}"
