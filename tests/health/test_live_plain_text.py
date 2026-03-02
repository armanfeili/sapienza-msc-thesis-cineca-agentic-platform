def test_health_live_plain_text(client):
    r = client.get("/v1/health/live")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert r.text.strip() == "ok"
