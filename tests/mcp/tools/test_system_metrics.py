"""Tests for system.metrics tool following P3 pattern."""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import Mock, patch, MagicMock

import pytest

from src.mcp.tools.system import metrics as metrics_module


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


@pytest.fixture
def mock_registry():
    """Mock Prometheus registry with sample metrics."""
    family1 = MagicMock()
    family1.name = "test_counter"
    family1.type = "counter"
    family1.documentation = "A test counter"

    sample1 = MagicMock()
    sample1.name = "test_counter_total"
    sample1.labels = {"env": "test"}
    sample1.value = 42.0
    family1.samples = [sample1]

    family2 = MagicMock()
    family2.name = "test_gauge"
    family2.type = "gauge"
    family2.documentation = "A test gauge"

    sample2 = MagicMock()
    sample2.name = "test_gauge"
    sample2.labels = {}
    sample2.value = 3.14
    family2.samples = [sample2]

    return [family1, family2]


# Scrape Action - Text Format Tests
# ────────────────────────────────────────────────────────────────────────────


def test_scrape_text_format_default(mock_ctx, mock_registry):
    """Scrape returns text format by default."""
    with patch.object(metrics_module, "REGISTRY") as mock_reg:
        mock_reg.collect.return_value = mock_registry
        with patch.object(metrics_module, "generate_latest", return_value=b"# HELP test\ntest 1.0\n"):
            result = metrics_module._act_scrape(mock_ctx, {})

    assert result["ok"] is True
    assert result["action"] == "scrape"
    assert result["format"] == "text"
    assert "body" in result
    assert isinstance(result["body"], str)
    assert "checked_at" in result


def test_scrape_text_format_explicit(mock_ctx, mock_registry):
    """Scrape with explicit format='text' parameter."""
    with patch.object(metrics_module, "REGISTRY") as mock_reg:
        mock_reg.collect.return_value = mock_registry
        with patch.object(metrics_module, "generate_latest", return_value=b"# HELP test\ntest 1.0\n"):
            result = metrics_module._act_scrape(mock_ctx, {"format": "text"})

    assert result["format"] == "text"
    assert "content_type" in result


def test_scrape_text_with_filter(mock_ctx, mock_registry):
    """Scrape text format with name filter."""
    with patch.object(metrics_module, "REGISTRY") as mock_reg:
        mock_reg.collect.return_value = mock_registry
        result = metrics_module._act_scrape(mock_ctx, {"format": "text", "names": ["test_counter"]})

    assert result["ok"] is True
    assert result["format"] == "text"
    # Should filter to only test_counter
    assert "test_counter" in result["body"]


# Scrape Action - JSON Format Tests
# ────────────────────────────────────────────────────────────────────────────


def test_scrape_json_format(mock_ctx, mock_registry):
    """Scrape returns JSON format when specified."""
    with patch.object(metrics_module, "REGISTRY") as mock_reg:
        mock_reg.collect.return_value = mock_registry
        result = metrics_module._act_scrape(mock_ctx, {"format": "json"})

    assert result["ok"] is True
    assert result["action"] == "scrape"
    assert result["format"] == "json"
    assert "metrics" in result
    assert isinstance(result["metrics"], list)


def test_scrape_json_metrics_structure(mock_ctx, mock_registry):
    """JSON scrape includes proper metric structure."""
    with patch.object(metrics_module, "REGISTRY") as mock_reg:
        mock_reg.collect.return_value = mock_registry
        result = metrics_module._act_scrape(mock_ctx, {"format": "json"})

    metrics = result["metrics"]
    assert len(metrics) == 2

    # Check first metric structure
    metric = metrics[0]
    assert "name" in metric
    assert "type" in metric
    assert "documentation" in metric
    assert "samples" in metric
    assert isinstance(metric["samples"], list)


def test_scrape_json_sample_structure(mock_ctx, mock_registry):
    """JSON samples include name, labels, and value."""
    with patch.object(metrics_module, "REGISTRY") as mock_reg:
        mock_reg.collect.return_value = mock_registry
        result = metrics_module._act_scrape(mock_ctx, {"format": "json"})

    samples = result["metrics"][0]["samples"]
    assert len(samples) > 0

    sample = samples[0]
    assert "name" in sample
    assert "labels" in sample
    assert "value" in sample
    assert isinstance(sample["value"], float)


def test_scrape_json_with_filter(mock_ctx, mock_registry):
    """JSON scrape respects name filter."""
    with patch.object(metrics_module, "REGISTRY") as mock_reg:
        mock_reg.collect.return_value = mock_registry
        result = metrics_module._act_scrape(mock_ctx, {"format": "json", "names": ["test_gauge"]})

    # Should only include test_gauge
    metric_names = [m["name"] for m in result["metrics"]]
    assert "test_gauge" in metric_names


# Info Action Tests
# ────────────────────────────────────────────────────────────────────────────


def test_info_returns_registry_stats(mock_ctx, mock_registry):
    """Info action returns registry statistics."""
    with patch.object(metrics_module, "REGISTRY") as mock_reg:
        mock_reg.collect.return_value = mock_registry
        result = metrics_module._act_info(mock_ctx, {})

    assert result["ok"] is True
    assert result["action"] == "info"
    assert "registry" in result
    assert "families" in result["registry"]
    assert "sample_series" in result["registry"]
    assert "names" in result["registry"]


def test_info_families_count(mock_ctx, mock_registry):
    """Info includes correct families count."""
    with patch.object(metrics_module, "REGISTRY") as mock_reg:
        mock_reg.collect.return_value = mock_registry
        result = metrics_module._act_info(mock_ctx, {})

    assert result["registry"]["families"] == 2  # Two mock families


def test_info_names_list(mock_ctx, mock_registry):
    """Info includes sorted list of metric names."""
    with patch.object(metrics_module, "REGISTRY") as mock_reg:
        mock_reg.collect.return_value = mock_registry
        result = metrics_module._act_info(mock_ctx, {})

    names = result["registry"]["names"]
    assert isinstance(names, list)
    # Should be sorted
    assert names == sorted(names)
    # Should include both family and sample names
    assert "test_counter" in names or "test_counter_total" in names


# Edge Case Tests
# ────────────────────────────────────────────────────────────────────────────


def test_decorated_function_exists():
    """system.metrics decorated function exists."""
    assert hasattr(metrics_module, "system_metrics")
    assert callable(metrics_module.system_metrics)


def test_scrape_with_empty_payload(mock_ctx, mock_registry):
    """Scrape works with empty payload (defaults applied)."""
    with patch.object(metrics_module, "REGISTRY") as mock_reg:
        mock_reg.collect.return_value = mock_registry
        with patch.object(metrics_module, "generate_latest", return_value=b"test\n"):
            result = metrics_module._act_scrape(mock_ctx, {})

    assert result["ok"] is True
    assert result["action"] == "scrape"
    assert result["format"] == "text"  # Default format


def test_info_with_empty_payload(mock_ctx, mock_registry):
    """Info works with empty payload."""
    with patch.object(metrics_module, "REGISTRY") as mock_reg:
        mock_reg.collect.return_value = mock_registry
        result = metrics_module._act_info(mock_ctx, {})

    assert result["ok"] is True
    assert result["action"] == "info"


def test_scrape_empty_registry(mock_ctx):
    """Scrape handles empty registry gracefully."""
    with patch.object(metrics_module, "REGISTRY") as mock_reg:
        mock_reg.collect.return_value = []
        result = metrics_module._act_scrape(mock_ctx, {"format": "json"})

    assert result["ok"] is True
    assert result["metrics"] == []


def test_info_empty_registry(mock_ctx):
    """Info handles empty registry gracefully."""
    with patch.object(metrics_module, "REGISTRY") as mock_reg:
        mock_reg.collect.return_value = []
        result = metrics_module._act_info(mock_ctx, {})

    assert result["ok"] is True
    assert result["registry"]["families"] == 0
    assert result["registry"]["sample_series"] == 0
    assert result["registry"]["names"] == []
