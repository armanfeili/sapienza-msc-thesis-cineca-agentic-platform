import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from schemas.auth import UserInfo
from schemas.models import TestInstanceRequest
from src.routers import model_instances


class _DummyEvent:
    def __init__(self, trace: str = "trace", event: str = "event") -> None:
        self.trace_id = trace
        self.event_id = event


@pytest.fixture(autouse=True)
def _patch_provenance(monkeypatch):
    monkeypatch.setattr("src.routers.model_instances.record_provenance", lambda **_: _DummyEvent())


@pytest.fixture
def dummy_request() -> Request:
    return Request(scope={"type": "http", "headers": []})


@pytest.fixture
def dummy_user() -> UserInfo:
    return UserInfo(sub="admin", scopes=["admin:all"], permissions=["admin:all"])


@pytest.mark.asyncio
async def test_instance_test_missing_instance_returns_problem_json(monkeypatch, dummy_user):
    monkeypatch.setattr("db.postgres_control.repositories.model_instance_repo.get_instance", lambda _id: None)

    with pytest.raises(HTTPException) as exc_info:
        await model_instances.test_instance("missing", Response(), dummy_user, TestInstanceRequest(prompt="test"))
    
    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    detail = exc_info.value.detail
    assert detail["title"] == "Not Found"
    assert "Instance not found" in detail["detail"]


@pytest.mark.asyncio
async def test_instance_test_preflight_failure_returns_problem(monkeypatch, dummy_user):
    """Test that HTTP errors from provider are properly handled."""
    instance = {
        "id": "llama",
        "name": "llama",
        "provider_id": "local",
        "model_id": "llama32-3b",
        "loaded": True,
        "enabled": True,
    }
    monkeypatch.setattr("db.postgres_control.repositories.model_instance_repo.get_instance", lambda _id: instance)

    provider = {
        "id": "local",
        "type": "openai_compatible",
        "base_url": "http://example:11434",
        "config_json": {"paths": {"chat_completions": "/chat/completions"}},
    }
    monkeypatch.setattr(
        "db.postgres_control.repositories.provider_repo.get_provider", lambda _pid, **kwargs: provider
    )

    # Mock warm-up check helpers
    monkeypatch.setattr("src.utils.test_helpers.should_warmup", lambda _id: False)
    monkeypatch.setattr("src.utils.test_helpers.hash_prompt", lambda _p: "hash123")
    monkeypatch.setattr(
        "src.utils.test_helpers.normalize_request_to_messages",
        lambda **kwargs: [{"role": "user", "content": "test"}],
    )
    monkeypatch.setattr("src.utils.test_helpers.get_stop_sequences", lambda **kwargs: None)

    # Mock httpx.AsyncClient to simulate provider failure
    class _FailingAsyncClient:
        def __init__(self, *_, **__):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_) -> None:
            return None

        async def post(self, *_args, **_kwargs):
            # Simulate 502 Bad Gateway from provider
            import httpx

            raise httpx.HTTPStatusError(
                "Bad Gateway", request=None, response=SimpleNamespace(status_code=status.HTTP_502_BAD_GATEWAY)
            )

    monkeypatch.setattr("httpx.AsyncClient", _FailingAsyncClient)

    # Mock record_test_event to avoid DB calls
    monkeypatch.setattr("db.postgres_control.repositories.model_instance_repo.record_test_event", lambda **_: None)

    with pytest.raises(HTTPException) as exc_info:
        await model_instances.test_instance("llama", Response(), dummy_user, TestInstanceRequest(prompt="test"))

    # Check that provider error is re-raised as HTTPException
    assert exc_info.value.status_code == status.HTTP_502_BAD_GATEWAY


@pytest.mark.asyncio
async def test_instance_test_happy_path_returns_payload(monkeypatch, dummy_user):
    """Test successful model instance test with full response."""
    instance = {
        "id": "llama",
        "name": "llama",
        "provider_id": "local",
        "model_id": "llama32-3b",
        "loaded": True,
        "enabled": True,
    }
    monkeypatch.setattr("db.postgres_control.repositories.model_instance_repo.get_instance", lambda _id: instance)

    provider = {
        "id": "local",
        "type": "openai_compatible",
        "base_url": "http://example:11434",
        "config_json": {"paths": {"chat_completions": "/chat/completions"}},
    }
    monkeypatch.setattr(
        "db.postgres_control.repositories.provider_repo.get_provider", lambda _pid, **kwargs: provider
    )

    # Mock warm-up check helpers
    monkeypatch.setattr("src.utils.test_helpers.should_warmup", lambda _id: False)
    monkeypatch.setattr("src.utils.test_helpers.hash_prompt", lambda _p: "hash123")
    monkeypatch.setattr(
        "src.utils.test_helpers.normalize_request_to_messages",
        lambda **kwargs: [{"role": "user", "content": "test"}],
    )
    monkeypatch.setattr("src.utils.test_helpers.get_stop_sequences", lambda **kwargs: None)
    monkeypatch.setattr(
        "src.utils.test_helpers.extract_text_from_response",
        lambda response_data, model_id: ("pong", {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}),
    )
    monkeypatch.setattr("src.utils.test_helpers.truncate_to_sentence", lambda text, one_sentence: text)

    # Mock successful HTTP response
    class _DummyResponse:
        status_code = status.HTTP_200_OK

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "choices": [{"message": {"content": "pong"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }

    class _DummyAsyncClient:
        def __init__(self, *_, **__):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_) -> None:
            return None

        async def post(self, *_args, **_kwargs):
            return _DummyResponse()

    monkeypatch.setattr("httpx.AsyncClient", _DummyAsyncClient)

    # Mock record_test_event to avoid DB calls
    monkeypatch.setattr("db.postgres_control.repositories.model_instance_repo.record_test_event", lambda **_: None)

    result = await model_instances.test_instance("llama", Response(), dummy_user, TestInstanceRequest(prompt="test"))

    assert isinstance(result.model, str)
    assert result.model == "llama32-3b"
    assert result.output == "pong"
    assert result.usage["total_tokens"] == 2  # usage is dict, not object
    assert result.provider == "local"
    assert result.provider_base_url == "http://example:11434"
    assert result.latency_ms > 0

