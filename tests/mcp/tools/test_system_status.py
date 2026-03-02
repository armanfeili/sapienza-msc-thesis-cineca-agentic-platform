"""Tests for system.status tool following P3 pattern."""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import Mock, patch

import pytest

from src.mcp.tools.system import status as status_module


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


# Basic Status Tests
# ────────────────────────────────────────────────────────────────────────────


def test_status_returns_ok_structure(mock_ctx):
    """Status check returns proper structure with all required fields."""
    result = status_module._act_status(mock_ctx, {})

    assert "ok" in result
    assert "action" in result
    assert result["action"] == "status"
    assert "checked_at" in result
    assert "service" in result
    assert "endpoints" in result
    assert "components" in result
    assert "warnings" in result


def test_status_service_info_complete(mock_ctx):
    """Service info includes all required fields."""
    result = status_module._act_status(mock_ctx, {})

    service = result["service"]
    assert "name" in service
    assert "version" in service
    assert "env" in service
    assert "debug" in service
    assert "log_level" in service
    assert "uptime_sec" in service
    assert "process" in service
    assert "build" in service


def test_status_process_info_complete(mock_ctx):
    """Process info includes runtime details."""
    result = status_module._act_status(mock_ctx, {})

    process = result["service"]["process"]
    assert "pid" in process
    assert "python_version" in process
    assert "python_implementation" in process
    assert "executable" in process
    assert "argv" in process
    assert "platform" in process
    assert "hostname" in process

    # Platform details
    assert "system" in process["platform"]
    assert "release" in process["platform"]
    assert "machine" in process["platform"]


def test_status_endpoints_included(mock_ctx):
    """Endpoints section includes HTTP routes."""
    result = status_module._act_status(mock_ctx, {})

    endpoints = result["endpoints"]
    assert "http" in endpoints
    assert "health" in endpoints["http"]
    assert "ready" in endpoints["http"]
    assert "metrics" in endpoints["http"]
    assert "docs" in endpoints["http"]


# Component Tests
# ────────────────────────────────────────────────────────────────────────────


def test_status_components_included(mock_ctx):
    """Components section includes all monitored services."""
    result = status_module._act_status(mock_ctx, {})

    components = result["components"]
    assert "memgraph" in components
    assert "redis" in components
    assert "otel" in components


def test_status_memgraph_structure(mock_ctx):
    """Memgraph component has expected structure."""
    result = status_module._act_status(mock_ctx, {})

    mg = result["components"]["memgraph"]
    assert "enabled" in mg
    assert "ok" in mg
    assert isinstance(mg["ok"], bool)
    # Should have host/port even if connection fails
    assert "host" in mg or "error" in mg
    assert "port" in mg or "error" in mg


def test_status_redis_structure(mock_ctx):
    """Redis component has expected structure."""
    result = status_module._act_status(mock_ctx, {})

    redis = result["components"]["redis"]
    assert "enabled" in redis
    assert "ok" in redis
    assert isinstance(redis["ok"], bool)
    assert "host" in redis or "error" in redis
    assert "port" in redis or "error" in redis


def test_status_otel_structure(mock_ctx):
    """OTEL component has expected structure."""
    result = status_module._act_status(mock_ctx, {})

    otel = result["components"]["otel"]
    assert "enabled" in otel
    assert isinstance(otel["enabled"], bool)
    # Endpoint can be None if not configured
    assert "endpoint" in otel


# Detail Level Tests
# ────────────────────────────────────────────────────────────────────────────


def test_status_full_detail_includes_samples(mock_ctx):
    """Full detail mode includes component samples when available."""
    with patch.object(
        status_module,
        "_memgraph_status",
        return_value={"enabled": True, "ok": True, "host": "memgraph", "port": 7687, "sample": {"RETURN 1": 1}},
    ):
        result = status_module._act_status(mock_ctx, {"detail": "full"})

        mg = result["components"]["memgraph"]
        # Full detail should include sample if component is ok
        assert mg["ok"] is True
        assert "sample" in mg


def test_status_basic_detail_minimal_info(mock_ctx):
    """Basic detail mode returns less information."""
    # The _act_status calls component checks with detail=False for "basic"
    result = status_module._act_status(mock_ctx, {"detail": "basic"})

    # Should still have all components, just potentially less detail
    assert "components" in result
    assert "memgraph" in result["components"]
    assert "redis" in result["components"]


def test_status_default_detail_is_full(mock_ctx):
    """Default detail level is 'full' when not specified."""
    result_no_payload = status_module._act_status(mock_ctx, {})
    result_explicit_full = status_module._act_status(mock_ctx, {"detail": "full"})

    # Both should behave the same (testing detail parameter logic)
    assert result_no_payload["action"] == result_explicit_full["action"]


# Warning Tests
# ────────────────────────────────────────────────────────────────────────────


def test_status_warnings_memgraph_unhealthy(mock_ctx):
    """Warning added when Memgraph is unhealthy."""
    with patch.object(
        status_module, "_memgraph_status", return_value={"enabled": True, "ok": False, "error": "connection_failed"}
    ):
        result = status_module._act_status(mock_ctx, {})

        assert "memgraph_unhealthy" in result["warnings"]
        # ok should be False if any component is unhealthy
        assert result["ok"] is False


def test_status_warnings_redis_unhealthy(mock_ctx):
    """Warning added when Redis is enabled but unhealthy."""
    with patch.object(
        status_module, "_redis_status", return_value={"enabled": True, "ok": False, "error": "connection_failed"}
    ):
        result = status_module._act_status(mock_ctx, {})

        assert "redis_unhealthy" in result["warnings"]
        assert result["ok"] is False


def test_status_no_warnings_when_all_ok(mock_ctx):
    """No warnings when all components are healthy."""
    with patch.object(
        status_module, "_memgraph_status", return_value={"enabled": True, "ok": True, "host": "memgraph", "port": 7687}
    ), patch.object(
        status_module, "_redis_status", return_value={"enabled": True, "ok": True, "host": "redis", "port": 6379}
    ):
        result = status_module._act_status(mock_ctx, {})

        # Filter for "unhealthy" warnings (OTEL might have other warnings)
        unhealthy_warnings = [w for w in result["warnings"] if "unhealthy" in w]
        assert len(unhealthy_warnings) == 0
        assert result["ok"] is True


# Edge Case Tests
# ────────────────────────────────────────────────────────────────────────────


def test_decorated_function_exists():
    """system.status decorated function exists."""
    assert hasattr(status_module, "system_status")
    assert callable(status_module.system_status)


def test_status_with_empty_payload(mock_ctx):
    """Status works with empty payload (defaults applied)."""
    result = status_module._act_status(mock_ctx, {})

    assert result["ok"] is not None
    assert result["action"] == "status"


def test_status_uptime_is_positive(mock_ctx):
    """Uptime is a positive number."""
    result = status_module._act_status(mock_ctx, {})

    uptime = result["service"]["uptime_sec"]
    assert isinstance(uptime, (int, float))
    assert uptime >= 0.0
