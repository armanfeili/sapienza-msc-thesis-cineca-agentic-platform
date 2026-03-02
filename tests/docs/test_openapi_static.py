import pytest


def test_v1_openapi_is_versioned_and_paths_stripped(client):
    res = client.get("/v1/openapi.json")
    assert res.status_code == 200
    spec = res.json()
    assert spec.get("servers") == [{"url": "/v1"}]
    paths = spec.get("paths", {})
    for p in paths.keys():
        assert not p.startswith("/v1"), f"path still contains version prefix: {p}"


def test_v1_openapi_contains_paths(client):
    res = client.get("/v1/openapi.json")
    assert res.status_code == 200
    spec = res.json()
    assert isinstance(spec.get("paths", {}), dict)
