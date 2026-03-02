def test_job_events_is_documented_as_sse(client):
    spec = client.get("/v1/openapi.json").json()
    # find endpoint that ends with jobs/{job_id}/events
    candidates = [p for p in spec.get("paths", {}) if p.endswith("/jobs/{job_id}/events")]
    assert candidates, "SSE endpoint not found in spec"
    op = spec["paths"][candidates[0]].get("get") or spec["paths"][candidates[0]].get("post")
    assert op and "responses" in op
    sse = op["responses"]["200"]["content"]
    assert "text/event-stream" in sse
