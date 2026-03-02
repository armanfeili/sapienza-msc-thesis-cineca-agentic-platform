import httpx
import pytest

from src.config import settings
from src.routers import models as models_router


class DummyProvider:
    def __init__(
        self,
        *,
        provider_id: str,
        base_url: str | None,
        provider_type: str = "openai_compatible",
        config: dict | None = None,
        name: str | None = None,
    ):
        self.id = provider_id
        self.name = name or provider_id
        self.type = provider_type
        self.base_url = base_url
        self.config = config or {}


@pytest.fixture(autouse=True)
def reset_settings(monkeypatch):
    original_base_url = getattr(settings, "OLLAMA_BASE_URL", None)
    original_timeout = getattr(settings, "OLLAMA_TIMEOUT_SECS", 60)
    original_model_map = getattr(settings, "OLLAMA_MODEL_MAP", None)
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", original_base_url, raising=False)
    monkeypatch.setattr(settings, "OLLAMA_TIMEOUT_SECS", original_timeout, raising=False)
    monkeypatch.setattr(settings, "OLLAMA_MODEL_MAP", original_model_map, raising=False)
    yield
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", original_base_url, raising=False)
    monkeypatch.setattr(settings, "OLLAMA_TIMEOUT_SECS", original_timeout, raising=False)
    monkeypatch.setattr(settings, "OLLAMA_MODEL_MAP", original_model_map, raising=False)


def test_non_ollama_provider_returns_instance_model():
    provider = DummyProvider(provider_id="openai", base_url="https://api.openai.com")
    instance = {"model_id": "gpt-4o-mini"}
    result = models_router._resolve_upstream_model_id(provider, "gpt-4o-mini", "gpt-4o-mini", instance)
    assert result == "gpt-4o-mini"


def test_default_ollama_mapping_applies(monkeypatch):
    provider = DummyProvider(provider_id="ollama-local", base_url="http://ollama:11434")
    instance = {"model_id": "llama32-3b-q4"}
    result = models_router._resolve_upstream_model_id(provider, "llama32-3b-q4", None, instance)
    assert result == settings.effective_ollama_model_map["llama32-3b-q4"]


def test_custom_model_map_overrides_default(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_MODEL_MAP", {"custom-logic": "custom:tag"}, raising=False)
    provider = DummyProvider(provider_id="ollama-remote", base_url=None, config={"base_url": "http://remote:11434"})
    instance = {"model_id": "custom-logic"}
    result = models_router._resolve_upstream_model_id(provider, "custom-logic", None, instance)
    assert result == "custom:tag"


def test_timeout_uses_ollama_setting(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_TIMEOUT_SECS", 25, raising=False)
    provider = DummyProvider(provider_id="ollama-fast", base_url="http://ollama:11434")
    timeout = models_router._timeout_for_provider(provider)
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.connect == 25
    assert timeout.read == 25
    assert timeout.write == 25


def test_resolve_ollama_base_url_prefers_override(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "http://example:5555", raising=False)
    provider = DummyProvider(provider_id="ollama-local", base_url=None)
    resolved = models_router._resolve_provider_base_url(provider)
    assert resolved == "http://example:5555"


def test_is_ollama_provider_matches_by_name():
    provider = DummyProvider(provider_id="local-llm", base_url="http://localhost:11434", name="Ollama Cloud")
    assert models_router._is_ollama_provider(provider)
