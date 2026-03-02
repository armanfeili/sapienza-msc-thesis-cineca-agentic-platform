def _has_v2(client):
    return client.get("/v2/openapi.json").status_code == 200


def test_v1_servers_and_paths(client):
    res = client.get("/v1/openapi.json")
    assert res.status_code == 200
    spec = res.json()
    urls = [s["url"] for s in spec.get("servers", [])]
    # current version first
    assert spec["servers"][0]["url"] == "/v1"
    assert "/v1" in urls
    # include v2 if it exists
    if _has_v2(client):
        assert "/v2" in urls
    # paths are stripped
    assert all(not p.startswith("/v1") for p in spec.get("paths", {}))


def test_v2_servers_and_paths_if_present(client):
    resp = client.get("/v2/openapi.json")
    if resp.status_code != 200:
        return
    spec = resp.json()
    urls = [s["url"] for s in spec.get("servers", [])]
    assert spec["servers"][0]["url"] == "/v2"
    assert "/v2" in urls and "/v1" in urls
    assert all(not p.startswith("/v2") for p in spec.get("paths", {}))
