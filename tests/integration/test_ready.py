import pytest
from httpx import AsyncClient, ASGITransport


@pytest.mark.anyio
async def test_ready_endpoint_json_shape(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/v1/health/ready")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/json")

    data = r.json()
    # top-level shape
    assert isinstance(data, dict)
    assert "status" in data
    assert "time" in data or "timestamp" in data  # allow minor variations
    assert "checks" in data and isinstance(data["checks"], dict)

    # Probe structure is flexible: each entry should at least have a status
    for name, probe in data["checks"].items():
        assert isinstance(name, str) and name, "probe name must be a non-empty string"
        assert isinstance(probe, dict)
        assert "status" in probe
        # Optional latency field, if present should be numeric and non-negative
        if "latency_ms" in probe:
            lat = probe["latency_ms"]
            assert isinstance(lat, (int, float))
            assert lat >= 0


@pytest.mark.anyio
async def test_ready_status_value_is_reasonable(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/v1/health/ready")
    assert r.status_code == 200
    payload = r.json()
    assert payload["status"] in {"ok", "degraded", "unknown", "error"}

    # If specific dependencies are reported, they must include a status
    checks = payload.get("checks", {})
    for dep in ("redis", "memgraph"):
        if dep in checks:
            assert "status" in checks[dep]
