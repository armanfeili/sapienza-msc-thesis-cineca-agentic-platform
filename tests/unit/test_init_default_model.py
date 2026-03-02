from types import SimpleNamespace

import pytest


def test_init_default_model_reuses_existing(monkeypatch):
    """Existing healthy default should short-circuit heavy initialization."""
    existing = SimpleNamespace(
        provider_model_id="phi3:mini",
        base_url="http://ollama:11434/v1",
        provider_id="prov-1",
        instance_id="inst-1",
        instance_name="phi3-mini",
    )

    monkeypatch.setenv("DEFAULT_MODEL_NAME", "phi3:mini")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama:11434/v1")

    monkeypatch.setattr("scripts.init_default_model.model_instance_repo.get_default", lambda scope, tenant_id: existing)
    monkeypatch.setattr(
        "scripts.init_default_model.provider_repo.get_provider_health",
        lambda provider_id: {"ok": True, "reachable": True},
    )

    def _fail(*args, **kwargs):  # pragma: no cover - ensures short-circuit
        raise AssertionError("should not be called when default is healthy")

    # None of these should be reached when we reuse the existing default
    monkeypatch.setattr("scripts.init_default_model.provider_repo.list_providers", _fail)
    monkeypatch.setattr("scripts.init_default_model.model_instance_repo.list_instances", _fail)
    monkeypatch.setattr("scripts.init_default_model.model_instance_repo.create_instance", _fail)
    monkeypatch.setattr("scripts.init_default_model.model_instance_repo.set_default", _fail)

    from scripts.init_default_model import init_default_model

    result = init_default_model()

    assert result["provider_id"] == existing.provider_id
    assert result["model_id"] == existing.provider_model_id
    assert result["instance_name"] == existing.instance_name
