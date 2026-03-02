"""Test health service behavior when MemgraphAdapter is missing."""
import pytest


@pytest.mark.asyncio
async def test_memgraph_probe_returns_adapter_missing_when_adapter_sentinel_is_none(monkeypatch):
    """
    If the MemgraphAdapter sentinel is None and fallback is allowed,
    the probe should report 'unknown' with reason 'adapter-missing'.
    """
    from src.services import health as health_mod
    from src.services.health import HealthService

    # Set MemgraphAdapter to None to simulate adapter-missing condition
    monkeypatch.setattr(health_mod, "MemgraphAdapter", None, raising=True)

    svc = HealthService()
    res = await svc.check()
    assert res.ok
    checks = res.data["checks"]
    assert checks["memgraph"]["status"] == "unknown"
    assert checks["memgraph"].get("reason") == "adapter-missing"
