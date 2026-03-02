"""
Tests for model.manage tool (P3 pattern).

Tests internal _act_* functions directly following P3 testing pattern.
"""

from __future__ import annotations

import pytest
from typing import Any, Dict
from unittest.mock import MagicMock, patch

# Import the tool module
from src.mcp.tools.model import manage as model_manage_module


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_ctx():
    """Mock ToolContext."""
    ctx = MagicMock()
    ctx.principal = "test-user"
    ctx.tenant = "test-tenant"
    ctx.trace_id = "test-trace-123"
    return ctx


@pytest.fixture(autouse=True)
def reset_overrides():
    """Reset _OVERRIDES between tests."""
    model_manage_module._OVERRIDES.clear()
    yield
    model_manage_module._OVERRIDES.clear()


@pytest.fixture
def mock_adapter():
    """Mock LLMAdapter with typical methods."""
    adapter = MagicMock()
    adapter.provider = "openai"
    adapter.model = "gpt-4"
    adapter.temperature = 0.7
    adapter.max_tokens = 2000
    adapter.api_base = "https://api.openai.com/v1"
    adapter.features.return_value = ["chat", "embeddings"]
    adapter.health.return_value = True
    adapter.available_models.return_value = ["gpt-4", "gpt-3.5-turbo"]
    adapter.info.return_value = {
        "provider": "openai",
        "model": "gpt-4",
        "temperature": 0.7,
        "max_tokens": 2000,
        "api_base": "https://api.openai.com/v1",
        "features": ["chat", "embeddings"],
    }
    # Mock configure to raise AttributeError (adapter doesn't support runtime config)
    # This triggers fallback to _OVERRIDES
    adapter.configure.side_effect = AttributeError("configure not supported")
    return adapter


# ─────────────────────────────────────────────────────────────────────────────
# Test _validate_temperature
# ─────────────────────────────────────────────────────────────────────────────


def test_validate_temperature_valid():
    """Valid temperature values should pass."""
    assert model_manage_module._validate_temperature(0.0) == 0.0
    assert model_manage_module._validate_temperature(1.0) == 1.0
    assert model_manage_module._validate_temperature(2.0) == 2.0
    assert model_manage_module._validate_temperature(0.7) == 0.7
    assert model_manage_module._validate_temperature("1.5") == 1.5


def test_validate_temperature_out_of_range():
    """Temperature outside [0.0, 2.0] should fail."""
    with pytest.raises(ValueError, match="between 0.0 and 2.0"):
        model_manage_module._validate_temperature(-0.1)
    with pytest.raises(ValueError, match="between 0.0 and 2.0"):
        model_manage_module._validate_temperature(2.1)


def test_validate_temperature_invalid_type():
    """Invalid types should fail with clear message."""
    with pytest.raises(ValueError, match="must be a number"):
        model_manage_module._validate_temperature("not-a-number")
    with pytest.raises(ValueError, match="must be a number"):
        model_manage_module._validate_temperature(None)


# ─────────────────────────────────────────────────────────────────────────────
# Test _validate_max_tokens
# ─────────────────────────────────────────────────────────────────────────────


def test_validate_max_tokens_valid():
    """Valid max_tokens values should pass."""
    assert model_manage_module._validate_max_tokens(1) == 1
    assert model_manage_module._validate_max_tokens(1000) == 1000
    assert model_manage_module._validate_max_tokens(32000) == 32000
    assert model_manage_module._validate_max_tokens("500") == 500


def test_validate_max_tokens_out_of_range():
    """max_tokens outside [1, 32000] should fail."""
    with pytest.raises(ValueError, match="between 1 and 32000"):
        model_manage_module._validate_max_tokens(0)
    with pytest.raises(ValueError, match="between 1 and 32000"):
        model_manage_module._validate_max_tokens(-100)
    with pytest.raises(ValueError, match="between 1 and 32000"):
        model_manage_module._validate_max_tokens(32001)


def test_validate_max_tokens_invalid_type():
    """Invalid types should fail with clear message."""
    with pytest.raises(ValueError, match="must be an integer"):
        model_manage_module._validate_max_tokens("not-a-number")
    with pytest.raises(ValueError, match="must be an integer"):
        model_manage_module._validate_max_tokens(None)


# ─────────────────────────────────────────────────────────────────────────────
# Test _mask_secrets
# ─────────────────────────────────────────────────────────────────────────────


def test_mask_secrets_removes_api_key():
    """API keys should be removed entirely."""
    data = {"model": "gpt-4", "api_key": "sk-secret123"}
    masked = model_manage_module._mask_secrets(data)
    assert "api_key" not in masked
    assert masked["model"] == "gpt-4"


def test_mask_secrets_removes_multiple_secret_fields():
    """All secret fields should be removed."""
    data = {
        "model": "gpt-4",
        "api_key": "sk-secret",
        "api_token": "token123",
        "password": "pass123",
        "secret": "mysecret",
    }
    masked = model_manage_module._mask_secrets(data)
    assert "api_key" not in masked
    assert "api_token" not in masked
    assert "password" not in masked
    assert "secret" not in masked
    assert masked["model"] == "gpt-4"


def test_mask_secrets_masks_api_base_query_params():
    """Query params in api_base should be masked."""
    data = {"api_base": "https://api.example.com/v1?token=secret123&key=value"}
    masked = model_manage_module._mask_secrets(data)
    assert masked["api_base"] == "https://api.example.com/v1?<query_masked>"


def test_mask_secrets_preserves_clean_api_base():
    """api_base without query params should be preserved."""
    data = {"api_base": "https://api.example.com/v1"}
    masked = model_manage_module._mask_secrets(data)
    assert masked["api_base"] == "https://api.example.com/v1"


def test_mask_secrets_preserves_non_secret_fields():
    """Non-secret fields should pass through unchanged."""
    data = {"provider": "openai", "model": "gpt-4", "temperature": 0.7, "max_tokens": 2000}
    masked = model_manage_module._mask_secrets(data)
    assert masked == data


# ─────────────────────────────────────────────────────────────────────────────
# Test _act_info
# ─────────────────────────────────────────────────────────────────────────────


@patch.object(model_manage_module, "_adapter")
def test_act_info_success(mock_adapter_factory, mock_adapter, mock_ctx):
    """_act_info should return current config with secrets masked."""
    mock_adapter_factory.return_value = mock_adapter

    result = model_manage_module._act_info(mock_ctx, {})

    assert result["ok"] is True
    assert result["action"] == "info"
    assert result["provider"] == "openai"
    assert result["model"] == "gpt-4"
    assert "api_key" not in result  # Secrets masked


@patch.object(model_manage_module, "_adapter")
def test_act_info_with_overrides(mock_adapter_factory, mock_adapter, mock_ctx):
    """_act_info should reflect overrides."""
    mock_adapter_factory.return_value = mock_adapter
    model_manage_module._OVERRIDES["temperature"] = 1.5

    result = model_manage_module._act_info(mock_ctx, {})

    assert result["ok"] is True
    assert result["temperature"] == 1.5  # Override applied


# ─────────────────────────────────────────────────────────────────────────────
# Test _act_get_config
# ─────────────────────────────────────────────────────────────────────────────


@patch.object(model_manage_module, "_adapter")
def test_act_get_config_success(mock_adapter_factory, mock_adapter, mock_ctx):
    """_act_get_config should return same as info."""
    mock_adapter_factory.return_value = mock_adapter

    result = model_manage_module._act_get_config(mock_ctx, {})

    assert result["ok"] is True
    assert result["action"] == "get_config"
    assert result["model"] == "gpt-4"


# ─────────────────────────────────────────────────────────────────────────────
# Test _act_set_config
# ─────────────────────────────────────────────────────────────────────────────


@patch.object(model_manage_module, "_adapter")
def test_act_set_config_valid_temperature(mock_adapter_factory, mock_adapter, mock_ctx):
    """Setting valid temperature should succeed."""
    mock_adapter_factory.return_value = mock_adapter

    result = model_manage_module._act_set_config(mock_ctx, {"temperature": 1.2})

    assert result["ok"] is True
    assert result["action"] == "set_config"
    # Check override was applied
    assert model_manage_module._OVERRIDES.get("temperature") == 1.2


@patch.object(model_manage_module, "_adapter")
def test_act_set_config_invalid_temperature(mock_adapter_factory, mock_adapter, mock_ctx):
    """Setting invalid temperature should raise ValueError."""
    mock_adapter_factory.return_value = mock_adapter

    with pytest.raises(ValueError, match="between 0.0 and 2.0"):
        model_manage_module._act_set_config(mock_ctx, {"temperature": 3.0})


@patch.object(model_manage_module, "_adapter")
def test_act_set_config_valid_max_tokens(mock_adapter_factory, mock_adapter, mock_ctx):
    """Setting valid max_tokens should succeed."""
    mock_adapter_factory.return_value = mock_adapter

    result = model_manage_module._act_set_config(mock_ctx, {"max_tokens": 4000})

    assert result["ok"] is True
    assert model_manage_module._OVERRIDES.get("max_tokens") == 4000


@patch.object(model_manage_module, "_adapter")
def test_act_set_config_invalid_max_tokens(mock_adapter_factory, mock_adapter, mock_ctx):
    """Setting invalid max_tokens should raise ValueError."""
    mock_adapter_factory.return_value = mock_adapter

    with pytest.raises(ValueError, match="between 1 and 32000"):
        model_manage_module._act_set_config(mock_ctx, {"max_tokens": 0})


@patch.object(model_manage_module, "_adapter")
def test_act_set_config_model(mock_adapter_factory, mock_adapter, mock_ctx):
    """Setting model should succeed (no validation)."""
    mock_adapter_factory.return_value = mock_adapter

    result = model_manage_module._act_set_config(mock_ctx, {"model": "gpt-3.5-turbo"})

    assert result["ok"] is True
    assert model_manage_module._OVERRIDES.get("model") == "gpt-3.5-turbo"


@patch.object(model_manage_module, "_adapter")
def test_act_set_config_multiple_params(mock_adapter_factory, mock_adapter, mock_ctx):
    """Setting multiple params at once should work."""
    mock_adapter_factory.return_value = mock_adapter

    result = model_manage_module._act_set_config(
        mock_ctx, {"model": "gpt-4-turbo", "temperature": 0.5, "max_tokens": 8000}
    )

    assert result["ok"] is True
    assert model_manage_module._OVERRIDES["model"] == "gpt-4-turbo"
    assert model_manage_module._OVERRIDES["temperature"] == 0.5
    assert model_manage_module._OVERRIDES["max_tokens"] == 8000


# ─────────────────────────────────────────────────────────────────────────────
# Test _act_reset_config
# ─────────────────────────────────────────────────────────────────────────────


@patch.object(model_manage_module, "_adapter")
def test_act_reset_config_clears_overrides(mock_adapter_factory, mock_adapter, mock_ctx):
    """reset_config should clear all overrides."""
    mock_adapter_factory.return_value = mock_adapter
    model_manage_module._OVERRIDES["temperature"] = 1.5
    model_manage_module._OVERRIDES["model"] = "custom-model"

    result = model_manage_module._act_reset_config(mock_ctx, {})

    assert result["ok"] is True
    assert result["action"] == "reset_config"
    assert len(model_manage_module._OVERRIDES) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Test _act_list_models
# ─────────────────────────────────────────────────────────────────────────────


@patch.object(model_manage_module, "_adapter")
def test_act_list_models_from_adapter(mock_adapter_factory, mock_adapter, mock_ctx):
    """list_models should use adapter.available_models() first."""
    mock_adapter_factory.return_value = mock_adapter

    result = model_manage_module._act_list_models(mock_ctx, {})

    assert result["ok"] is True
    assert result["action"] == "list_models"
    assert result["models"] == ["gpt-4", "gpt-3.5-turbo"]


@patch.object(model_manage_module, "_adapter")
@patch.object(model_manage_module, "settings")
def test_act_list_models_from_settings(mock_settings, mock_adapter_factory, mock_adapter, mock_ctx):
    """list_models should fall back to settings if adapter doesn't provide."""
    mock_adapter.available_models.side_effect = AttributeError("no method")
    mock_adapter_factory.return_value = mock_adapter
    mock_settings.LLM_AVAILABLE_MODELS = ["model-a", "model-b"]

    result = model_manage_module._act_list_models(mock_ctx, {})

    assert result["ok"] is True
    assert "model-a" in result["models"]


@patch.object(model_manage_module, "_adapter")
def test_act_list_models_fallback_current_model(mock_adapter_factory, mock_adapter, mock_ctx):
    """If no catalog available, list_models should return current model."""
    mock_adapter.available_models.side_effect = AttributeError("no method")
    mock_adapter_factory.return_value = mock_adapter

    result = model_manage_module._act_list_models(mock_ctx, {})

    assert result["ok"] is True
    assert len(result["models"]) >= 1  # At least current model


# ─────────────────────────────────────────────────────────────────────────────
# Test _act_capabilities
# ─────────────────────────────────────────────────────────────────────────────


@patch.object(model_manage_module, "_adapter")
def test_act_capabilities_success(mock_adapter_factory, mock_adapter, mock_ctx):
    """capabilities should return adapter features."""
    mock_adapter_factory.return_value = mock_adapter

    result = model_manage_module._act_capabilities(mock_ctx, {})

    assert result["ok"] is True
    assert result["action"] == "capabilities"
    assert "chat" in result["features"]
    assert "embeddings" in result["features"]


# ─────────────────────────────────────────────────────────────────────────────
# Test _act_health
# ─────────────────────────────────────────────────────────────────────────────


@patch.object(model_manage_module, "_adapter")
def test_act_health_healthy(mock_adapter_factory, mock_adapter, mock_ctx):
    """health should return True when adapter is healthy."""
    mock_adapter_factory.return_value = mock_adapter
    mock_adapter.health.return_value = True

    result = model_manage_module._act_health(mock_ctx, {})

    assert result["ok"] is True
    assert result["action"] == "health"
    assert result["healthy"] is True


@patch.object(model_manage_module, "_adapter")
def test_act_health_unhealthy(mock_adapter_factory, mock_adapter, mock_ctx):
    """health should return False when adapter is unhealthy."""
    mock_adapter_factory.return_value = mock_adapter
    mock_adapter.health.return_value = False

    result = model_manage_module._act_health(mock_ctx, {})

    assert result["ok"] is True
    assert result["healthy"] is False


@patch.object(model_manage_module, "_adapter")
def test_act_health_with_detail(mock_adapter_factory, mock_adapter, mock_ctx):
    """health should include detail if adapter returns dict."""
    mock_adapter_factory.return_value = mock_adapter
    mock_adapter.health.return_value = {"ok": True, "latency_ms": 45, "provider": "openai"}

    result = model_manage_module._act_health(mock_ctx, {})

    assert result["ok"] is True
    assert result["healthy"] is True
    assert result["detail"] is not None
    assert result["detail"]["latency_ms"] == 45


@patch.object(model_manage_module, "_adapter")
def test_act_health_adapter_error(mock_adapter_factory, mock_adapter, mock_ctx):
    """health should handle adapter errors gracefully."""
    mock_adapter_factory.return_value = mock_adapter
    mock_adapter.health.side_effect = Exception("Connection failed")

    result = model_manage_module._act_health(mock_ctx, {})

    # Should still return ok=True (best effort), but healthy will be True (default)
    assert result["ok"] is True
    # Error is suppressed, defaults to healthy=True


# ─────────────────────────────────────────────────────────────────────────────
# Test Entry Point Validation
# ─────────────────────────────────────────────────────────────────────────────


def test_entry_point_exists():
    """Entry point function should exist."""
    assert hasattr(model_manage_module, "model_manage")
    assert callable(model_manage_module.model_manage)


def test_backward_compatibility_aliases():
    """Backward compatibility aliases should exist."""
    assert hasattr(model_manage_module, "invoke")
    assert hasattr(model_manage_module, "run")
    assert hasattr(model_manage_module, "handle")
    assert model_manage_module.invoke == model_manage_module.model_manage
    assert model_manage_module.run == model_manage_module.model_manage
    assert model_manage_module.handle == model_manage_module.model_manage
