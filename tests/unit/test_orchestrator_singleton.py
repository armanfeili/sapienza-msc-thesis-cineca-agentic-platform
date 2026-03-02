import threading

from src.services import orchestrator as orch_mod


def test_get_orchestrator_instance_singleton(monkeypatch):
    """get_orchestrator_instance should only construct one orchestrator per process."""
    sentinel = object()

    monkeypatch.setattr(orch_mod, "_GLOBAL_ORCH", None)
    monkeypatch.setattr(orch_mod, "_ORCHESTRATOR_LOCK", threading.Lock())
    monkeypatch.setattr(orch_mod.Orchestrator, "from_env", classmethod(lambda cls: sentinel))  # type: ignore[misc]

    inst1 = orch_mod.get_orchestrator_instance()
    inst2 = orch_mod.get_orchestrator_instance()

    assert inst1 is sentinel
    assert inst2 is sentinel
