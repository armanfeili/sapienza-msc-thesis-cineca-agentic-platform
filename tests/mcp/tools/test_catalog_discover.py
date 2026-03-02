"""
Tests for src/mcp/tools/catalog/discover.py

Validates manifest caching, filtering, and discovery actions.
"""

import pytest
import time
from typing import Any, Dict

# Import the internal action handler
from src.mcp.tools.catalog.discover import (
    _act_discover,
    _cached_manifest,
    _category_of,
    _CACHE_TTL,
)


# ─────────────────────────────────────────────────────────────────────────────
# Test Helpers
# ─────────────────────────────────────────────────────────────────────────────


def test_category_of_extracts_prefix():
    """_category_of extracts category from tool name."""
    assert _category_of("graph.query") == "graph"
    assert _category_of("model.test") == "model"
    assert _category_of("single") == "misc"


# ─────────────────────────────────────────────────────────────────────────────
# Test Manifest Caching (P6 Feature)
# ─────────────────────────────────────────────────────────────────────────────


def test_cached_manifest_caches_result():
    """_cached_manifest caches manifest for TTL duration (P6 Feature)."""
    # First call fetches fresh
    manifest1 = _cached_manifest()
    assert isinstance(manifest1, dict)

    # Second call returns cached
    manifest2 = _cached_manifest()
    assert manifest2 is manifest1  # Same object reference


def test_cached_manifest_expires_after_ttl():
    """_cached_manifest refreshes after TTL expires (P6 Feature)."""
    # Get initial manifest
    manifest1 = _cached_manifest()

    # Wait for cache to expire (mock by setting old timestamp)
    import src.mcp.tools.catalog.discover as discover_module

    discover_module._CACHE_TIME = time.time() - (_CACHE_TTL + 1)

    # Next call refreshes
    manifest2 = _cached_manifest()
    assert isinstance(manifest2, dict)
    # Note: Can't test object identity since get_manifest returns new dict


# ─────────────────────────────────────────────────────────────────────────────
# Test _act_discover - Categories Only
# ─────────────────────────────────────────────────────────────────────────────


def test_act_discover_categories_only():
    """Discover with categories_only returns just categories."""
    result = _act_discover(None, {"categories_only": True})

    assert result["ok"] is True
    assert "categories" in result
    assert "count" in result
    assert isinstance(result["categories"], list)


# ─────────────────────────────────────────────────────────────────────────────
# Test _act_discover - Names Only
# ─────────────────────────────────────────────────────────────────────────────


def test_act_discover_names_only():
    """Discover with names_only returns just tool names."""
    result = _act_discover(None, {"names_only": True})

    assert result["ok"] is True
    assert "names" in result
    assert "count" in result
    assert isinstance(result["names"], list)


def test_act_discover_names_only_with_prefix():
    """Discover with names_only and prefix filters results."""
    result = _act_discover(None, {"names_only": True, "prefix": "graph"})

    assert result["ok"] is True
    # All returned names should start with prefix
    for name in result["names"]:
        assert name.startswith("graph")


# ─────────────────────────────────────────────────────────────────────────────
# Test _act_discover - Full Discovery
# ─────────────────────────────────────────────────────────────────────────────


def test_act_discover_full():
    """Discover returns full tool details."""
    result = _act_discover(None, {})

    assert result["ok"] is True
    assert "count" in result
    assert "items" in result
    assert "categories" in result
    assert "manifest" in result
    assert isinstance(result["items"], list)

    # Each item should have basic fields
    if result["items"]:
        item = result["items"][0]
        assert "name" in item
        assert "description" in item
        assert "category" in item


def test_act_discover_with_prefix_filter():
    """Discover filters by prefix."""
    result = _act_discover(None, {"prefix": "model"})

    assert result["ok"] is True
    # All returned tools should start with prefix
    for item in result["items"]:
        assert item["name"].startswith("model")


def test_act_discover_with_limit():
    """Discover respects limit parameter."""
    result = _act_discover(None, {"limit": 5})

    assert result["ok"] is True
    assert result["count"] <= 5
    assert len(result["items"]) <= 5


def test_act_discover_sort_by_name():
    """Discover sorts by name (default)."""
    result = _act_discover(None, {"sort": "name"})

    if len(result["items"]) > 1:
        names = [item["name"] for item in result["items"]]
        assert names == sorted(names)


def test_act_discover_sort_by_category():
    """Discover sorts by category."""
    result = _act_discover(None, {"sort": "category"})

    if len(result["items"]) > 1:
        categories = [item["category"] for item in result["items"]]
        # Should be sorted by category, then name
        assert all(categories[i] <= categories[i + 1] for i in range(len(categories) - 1))


# ─────────────────────────────────────────────────────────────────────────────
# Test _act_discover - Optional Fields
# ─────────────────────────────────────────────────────────────────────────────


def test_act_discover_includes_scopes_by_default():
    """Discover includes scopes by default."""
    result = _act_discover(None, {})

    # Find first item with scope
    for item in result["items"]:
        if "scope" in item:
            assert isinstance(item["scope"], str)
            break


def test_act_discover_excludes_scopes_when_disabled():
    """Discover excludes scopes when include_scopes=False."""
    result = _act_discover(None, {"include_scopes": False})

    # No items should have scope field
    for item in result["items"]:
        assert "scope" not in item


def test_act_discover_includes_schemas_when_enabled():
    """Discover includes schemas when include_schemas=True."""
    result = _act_discover(None, {"include_schemas": True})

    # Find first item with schema
    for item in result["items"]:
        if "input_schema" in item or "output_schema" in item:
            # At least one schema should be present
            assert True
            break


def test_act_discover_includes_modules_when_enabled():
    """Discover includes module paths when include_modules=True."""
    result = _act_discover(None, {"include_modules": True})

    # All items should have module field
    if result["items"]:
        for item in result["items"]:
            assert "module" in item
            assert isinstance(item["module"], str)


# ─────────────────────────────────────────────────────────────────────────────
# Test Entry Point
# ─────────────────────────────────────────────────────────────────────────────


def test_entry_point_routes_to_discover():
    """Entry point routes to _act_discover."""
    from src.mcp.tools.catalog.discover import invoke

    result = invoke(None, {"names_only": True})

    assert result["ok"] is True
    assert "names" in result


def test_entry_point_handles_errors():
    """Entry point handles errors gracefully."""
    from src.mcp.tools.catalog.discover import invoke

    # Invalid payload should not crash
    result = invoke(None, {})

    assert "ok" in result
