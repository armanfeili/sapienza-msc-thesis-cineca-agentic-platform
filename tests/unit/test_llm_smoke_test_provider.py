import pytest
from starlette.requests import Request

from src.routers import internal_ops


class DummyPrincipal:
    sub = "tester"
    tenant_id = "tenant-ops"


class FakeConfig:
    instance_name = "phi3-mini"
    provider_model_id = "phi3:mini"
    base_url = "http://localhost"
    provider_name = "ollama-local"


class FakeLLMClient:
    def __init__(self, model: str, base_url: str, api_key=None):
        self.model = model
        self.base_url = base_url

    async def complete(self, **kwargs):
        return "OK"


@pytest.mark.asyncio
async def test_llm_smoke_test_includes_provider_name(monkeypatch):
    from db.postgres_control.repositories import model_instance_repo
    import src.adapters.llm as llm_module

    monkeypatch.setattr(model_instance_repo, "get_default", lambda scope="global", tenant_id=None: FakeConfig())
    monkeypatch.setattr(internal_ops, "_emit_audit_log", lambda **kwargs: None)
    monkeypatch.setattr(llm_module, "LLMClient", FakeLLMClient)

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/internal/ops/llm-smoke-test",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )
    response = await internal_ops.llm_smoke_test(request, DummyPrincipal(), None)

    assert response.provider_name == "ollama-local"
    assert response.config_source == "db_default"
