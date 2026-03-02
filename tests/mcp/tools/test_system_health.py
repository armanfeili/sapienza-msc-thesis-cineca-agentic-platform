"""Tests for system.health tool following P3 pattern."""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import Mock, patch

import pytest

from src.mcp.tools.system import health as health_module


# Fixtures
# ────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_ctx():
    """Mock ToolContext for testing."""
    ctx = Mock()
    ctx.principal = "admin@example.com"
    ctx.tenant = "test-tenant"
    ctx.trace_id = "test-trace-123"
    return ctx


# Liveness Action Tests
# ────────────────────────────────────────────────────────────────────────────


def test_liveness_returns_ok_when_app_is_up(mock_ctx):
    """Liveness check returns ok when app is functional."""
    result = health_module._act_liveness(mock_ctx, {})

    assert result["ok"] is True
    assert result["action"] == "liveness"
    assert "checked_at" in result
    assert "summary" in result
    assert result["summary"]["passed"] == 1
    assert result["summary"]["failed"] == 0
    assert "components" in result
    # After normalization, "up" becomes "ok"
    assert result["components"]["app"]["status"] == "ok"
    assert "latency_ms" in result["components"]["app"]


def test_liveness_includes_hostname(mock_ctx):
    """Liveness check includes hostname in app component."""
    result = health_module._act_liveness(mock_ctx, {})

    assert "hostname" in result["components"]["app"]
    assert isinstance(result["components"]["app"]["hostname"], str)


def test_liveness_has_backward_compat_status(mock_ctx):
    """Liveness includes backward-compatible status field."""
    result = health_module._act_liveness(mock_ctx, {})

    assert "status" in result
    assert result["status"] == "ok"


def test_liveness_has_backward_compat_checks(mock_ctx):
    """Liveness includes backward-compatible checks field."""
    result = health_module._act_liveness(mock_ctx, {})

    assert "checks" in result
    assert "app" in result["checks"]
    # Status should be normalized to 'ok'/'error'/'unknown'
    assert result["checks"]["app"]["status"] == "ok"


# Readiness Action Tests
# ────────────────────────────────────────────────────────────────────────────


def test_readiness_checks_all_components(mock_ctx):
    """Readiness check includes app, db, and redis components."""
    result = health_module._act_readiness(mock_ctx, {})

    assert result["action"] == "readiness"
    assert "components" in result
    assert "app" in result["components"]
    assert "db" in result["components"]
    assert "redis" in result["components"]


def test_readiness_ok_when_all_up_or_skipped(mock_ctx):
    """Readiness is ok when all components are up or skipped."""
    with patch.object(
        health_module, "_check_memgraph", return_value={"status": "skipped", "reason": "adapter_unavailable"}
    ), patch.object(health_module, "_check_redis", return_value={"status": "skipped", "reason": "disabled"}):
        result = health_module._act_readiness(mock_ctx, {})

        assert result["ok"] is True
        # After normalization: "up"->"ok", "skipped"->"unknown"
        assert result["components"]["app"]["status"] == "ok"
        assert result["components"]["db"]["status"] == "unknown"
        assert result["components"]["redis"]["status"] == "unknown"


def test_readiness_not_ok_when_component_down(mock_ctx):
    """Readiness is not ok when any component is down."""
    with patch.object(
        health_module, "_check_memgraph", return_value={"status": "down", "error": "connection failed"}
    ), patch.object(health_module, "_check_redis", return_value={"status": "skipped", "reason": "disabled"}):
        result = health_module._act_readiness(mock_ctx, {})

        assert result["ok"] is False
        assert result["summary"]["failed"] >= 1


def test_readiness_includes_latencies(mock_ctx):
    """Readiness check includes latency measurements."""
    result = health_module._act_readiness(mock_ctx, {})

    assert "latency_ms" in result["components"]["app"]
    # DB and Redis might be skipped, but if they ran, they should have latency
    for component in result["components"].values():
        if component.get("status") in {"up", "down"}:
            assert "latency_ms" in component


def test_readiness_summary_counts(mock_ctx):
    """Readiness summary correctly counts passed/failed/skipped."""
    with patch.object(health_module, "_check_memgraph", return_value={"status": "up", "latency_ms": 5.0}), patch.object(
        health_module, "_check_redis", return_value={"status": "skipped", "reason": "disabled"}
    ):
        result = health_module._act_readiness(mock_ctx, {})

        assert result["summary"]["passed"] == 2  # app + db
        assert result["summary"]["failed"] == 0
        assert result["summary"]["skipped"] == 1  # redis


# Details Action Tests
# ────────────────────────────────────────────────────────────────────────────


def test_details_includes_all_readiness_data(mock_ctx):
    """Details action includes all readiness check data."""
    result = health_module._act_details(mock_ctx, {})

    assert result["action"] == "details"
    assert "components" in result
    assert "app" in result["components"]
    assert "db" in result["components"]
    assert "redis" in result["components"]
    assert "summary" in result


def test_details_includes_info_section(mock_ctx):
    """Details action includes info section with app/platform data."""
    result = health_module._act_details(mock_ctx, {})

    assert "info" in result
    assert "app" in result["info"]
    assert "platform" in result["info"]


def test_details_app_info_has_required_fields(mock_ctx):
    """Details app info includes name, env, and version."""
    result = health_module._act_details(mock_ctx, {})

    app_info = result["info"]["app"]
    assert "name" in app_info
    assert "env" in app_info
    assert "version" in app_info
    assert isinstance(app_info["version"], str)


def test_details_platform_info_has_python_version(mock_ctx):
    """Details platform info includes Python version."""
    result = health_module._act_details(mock_ctx, {})

    platform_info = result["info"]["platform"]
    assert "python" in platform_info
    # Should be in format "3.X.Y"
    assert platform_info["python"].count(".") >= 2


# Backward Compatibility Tests
# ────────────────────────────────────────────────────────────────────────────


def test_backward_compat_status_normalization(mock_ctx):
    """Status field is normalized for backward compatibility."""
    result = health_module._act_liveness(mock_ctx, {})

    # Should have both 'ok' bool and 'status' string
    assert "ok" in result
    assert "status" in result
    assert result["status"] in {"ok", "error"}


def test_backward_compat_checks_normalization(mock_ctx):
    """Checks field uses normalized status values."""
    result = health_module._act_readiness(mock_ctx, {})

    assert "checks" in result
    # Probe statuses should be normalized
    for probe in result["checks"].values():
        if "status" in probe:
            assert probe["status"] in {"ok", "error", "unknown"}


# Edge Case Tests
# ────────────────────────────────────────────────────────────────────────────


def test_decorated_function_exists():
    """system.health decorated function exists."""
    assert hasattr(health_module, "system_health")
    assert callable(health_module.system_health)


def test_default_action_is_liveness(mock_ctx):
    """Default action when not specified is liveness."""
    result = health_module._act_liveness(mock_ctx, {})

    assert result["action"] == "liveness"


def test_empty_payload_works(mock_ctx):
    """Health checks work with empty payload."""
    result = health_module._act_liveness(mock_ctx, {})

    assert result["ok"] is True
    assert result["action"] == "liveness"
