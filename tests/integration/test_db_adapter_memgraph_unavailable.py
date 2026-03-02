import pytest


@pytest.mark.asyncio
async def test_memgraph_probe_returns_error_when_adapter_init_fails(monkeypatch):
    """
    Force the Memgraph adapter constructor to raise to simulate an unavailable DB.
    HealthService.check() should surface an 'error' status for the 'memgraph' probe.
    """
    from src.services import health as health_mod
    from src.services.health import HealthService

    class BoomAdapter:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("cannot connect to memgraph")

    # Patch the symbol used by HealthService._probe_memgraph
    monkeypatch.setattr(health_mod, "MemgraphAdapter", BoomAdapter, raising=True)

    svc = HealthService()
    res = await svc.check()
    assert res.ok
    checks = res.data["checks"]
    assert "memgraph" in checks
    assert checks["memgraph"]["status"] == "error"
    assert "cannot connect" in checks["memgraph"].get("error", "").lower()


@pytest.mark.asyncio
async def test_memgraph_probe_unknown_when_adapter_missing(monkeypatch):
    """
    If the adapter is not available in the module (simulating missing dependency),
    the probe should report 'unknown' with reason 'adapter-missing'.
    """
    from src.services import health as health_mod
    from src.services.health import HealthService

    monkeypatch.setattr(health_mod, "MemgraphAdapter", None, raising=True)

    svc = HealthService()
    res = await svc.check()
    assert res.ok
    checks = res.data["checks"]
    assert checks["memgraph"]["status"] == "unknown"
    assert checks["memgraph"].get("reason") == "adapter-missing"
