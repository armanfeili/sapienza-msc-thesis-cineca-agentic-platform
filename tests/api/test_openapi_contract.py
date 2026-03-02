import os
import requests
import pytest


def _fetch_openapi():
    base = os.environ.get("BASE_URL", "http://localhost:8000")
    candidates = [f"{base}/v1/openapi.json", f"{base}/openapi.json"]
    for url in candidates:
        try:
            r = requests.get(url, timeout=5)
        except Exception:
            continue
        if r.status_code == 200:
            return r.json()
    pytest.skip("openapi.json not available at /v1/openapi.json or /openapi.json")


def test_no_colon_in_openapi_paths():
    spec = _fetch_openapi()
    paths = spec.get("paths", {})
    bad = [p for p in paths.keys() if ":" in p]
    assert not bad, f"Found deprecated path actions in OpenAPI: {bad}"
