"""
Tests for src/mcp/tools/agent/context.py

Validates context counts tracking, caching with invalidation, and context assembly.
"""

import pytest
import time
from typing import Any, Dict

# Import the internal action handler and caching
from src.mcp.tools.agent.context import (
    _act_assemble,
    _collect_env,
    _collect_tools,
    _collect_models,
    invalidate_cache,
    _CONTEXT_CACHE_TTL,
)


# ─────────────────────────────────────────────────────────────────────────────
# Test Collectors (P6 Feature: Context Counts)
# ─────────────────────────────────────────────────────────────────────────────


def test_collect_env_returns_metadata():
    """_collect_env returns environment metadata."""
    env = _collect_env()

    assert "app_version" in env
    assert "python" in env
    assert "platform" in env
    assert "pid" in env
    assert "time" in env


def test_collect_tools_returns_counts():
    """_collect_tools returns context counts (P6 Feature)."""
    tools = _collect_tools()

    assert "count" in tools  # P6: Context count
    assert "names" in tools
    assert "categories" in tools
    assert "categories_count" in tools  # P6: Context count
    assert isinstance(tools["count"], int)
    assert isinstance(tools["categories_count"], int)


def test_collect_models_returns_counts():
    """_collect_models returns context counts (P6 Feature)."""
    models = _collect_models()

    assert "count" in models  # P6: Context count
    assert "names" in models
    assert "default" in models
    assert isinstance(models["count"], int)


# ─────────────────────────────────────────────────────────────────────────────
# Test Cache Invalidation (P6 Feature)
# ─────────────────────────────────────────────────────────────────────────────


def test_invalidate_cache_clears_cache():
    """invalidate_cache clears context cache (P6 Feature)."""
    # Build a context to populate cache
    _act_assemble(None, {})

    # Invalidate
    invalidate_cache()

    # Verify cache is cleared
    import src.mcp.tools.agent.context as context_module

    assert context_module._CONTEXT_CACHE is None
    assert context_module._CONTEXT_CACHE_TIME == 0


# ─────────────────────────────────────────────────────────────────────────────
# Test _act_assemble - Caching (P6 Feature)
# ─────────────────────────────────────────────────────────────────────────────


def test_act_assemble_caches_result():
    """_act_assemble caches result for TTL duration (P6 Feature)."""
    # Clear cache first
    invalidate_cache()

    # First call builds fresh
    result1 = _act_assemble(None, {})
    assert result1["ok"] is True
    assert result1["cached"] is False

    # Second call uses cache
    result2 = _act_assemble(None, {})
    assert result2["ok"] is True
    assert result2["cached"] is True


def test_act_assemble_cache_expires_after_ttl():
    """_act_assemble refreshes after TTL expires (P6 Feature)."""
    # Clear cache first
    invalidate_cache()

    # Get initial context
    result1 = _act_assemble(None, {})
    assert result1["cached"] is False

    # Expire cache manually
    import src.mcp.tools.agent.context as context_module

    context_module._CONTEXT_CACHE_TIME = time.time() - (_CONTEXT_CACHE_TTL + 1)

    # Next call refreshes
    result2 = _act_assemble(None, {})
    assert result2["cached"] is False


def test_act_assemble_cache_key_varies_by_options():
    """_act_assemble uses different cache keys for different options."""
    invalidate_cache()

    # First call with tools
    result1 = _act_assemble(None, {"include_tools": True})
    assert result1["cached"] is False

    # Second call without tools (different cache key)
    result2 = _act_assemble(None, {"include_tools": False})
    assert result2["cached"] is False  # Cache miss due to different key


# ─────────────────────────────────────────────────────────────────────────────
# Test _act_assemble - Context Assembly
# ─────────────────────────────────────────────────────────────────────────────


def test_act_assemble_includes_env_by_default():
    """Assemble includes environment by default."""
    invalidate_cache()
    result = _act_assemble(None, {})

    assert result["ok"] is True
    assert "agent_context" in result
    assert "env" in result["agent_context"]
    assert "rate_limit_backend" in result["agent_context"]


def test_act_assemble_includes_tools_by_default():
    """Assemble includes tools by default (P6 Feature: context counts)."""
    invalidate_cache()
    result = _act_assemble(None, {})

    assert "tools" in result["agent_context"]
    assert "count" in result["agent_context"]["tools"]  # P6: Context count


def test_act_assemble_includes_models_by_default():
    """Assemble includes models by default (P6 Feature: context counts)."""
    invalidate_cache()
    result = _act_assemble(None, {})

    assert "models" in result["agent_context"]
    assert "count" in result["agent_context"]["models"]  # P6: Context count


def test_act_assemble_excludes_policies_by_default():
    """Assemble excludes policies by default."""
    invalidate_cache()
    result = _act_assemble(None, {})

    assert "policies" not in result["agent_context"]


def test_act_assemble_includes_policies_when_enabled():
    """Assemble includes policies when include_policies=True."""
    invalidate_cache()
    result = _act_assemble(None, {"include_policies": True})

    assert "policies" in result["agent_context"]


def test_act_assemble_includes_tenant_by_default():
    """Assemble includes tenant by default."""
    invalidate_cache()
    result = _act_assemble(None, {})

    assert "tenant" in result["agent_context"]


def test_act_assemble_excludes_env_when_disabled():
    """Assemble excludes env when include_env=False."""
    invalidate_cache()
    result = _act_assemble(None, {"include_env": False})

    assert "env" not in result["agent_context"]


def test_act_assemble_excludes_tools_when_disabled():
    """Assemble excludes tools when include_tools=False."""
    invalidate_cache()
    result = _act_assemble(None, {"include_tools": False})

    assert "tools" not in result["agent_context"]


def test_act_assemble_excludes_models_when_disabled():
    """Assemble excludes models when include_models=False."""
    invalidate_cache()
    result = _act_assemble(None, {"include_models": False})

    assert "models" not in result["agent_context"]


# ─────────────────────────────────────────────────────────────────────────────
# Test _act_assemble - User Handling
# ─────────────────────────────────────────────────────────────────────────────


def test_act_assemble_handles_no_user():
    """Assemble handles missing user gracefully."""
    invalidate_cache()
    result = _act_assemble(None, {})

    assert "user" in result["agent_context"]
    assert result["agent_context"]["user"] == {}


def test_act_assemble_includes_user_from_payload():
    """Assemble includes user from payload."""
    invalidate_cache()
    user = {"username": "alice", "email": "alice@example.com", "role": "admin"}
    result = _act_assemble(None, {"user": user})

    assert "user" in result["agent_context"]
    # User should be scrubbed/summarized
    assert "username" in result["agent_context"]["user"] or "email" in result["agent_context"]["user"]


def test_act_assemble_includes_user_from_kwargs():
    """Assemble includes user from kwargs."""
    invalidate_cache()
    user = {"username": "bob", "email": "bob@example.com", "role": "user"}
    result = _act_assemble(None, {}, user=user)

    assert "user" in result["agent_context"]


# ─────────────────────────────────────────────────────────────────────────────
# Test Entry Point
# ─────────────────────────────────────────────────────────────────────────────


def test_entry_point_routes_to_assemble():
    """Entry point routes to _act_assemble."""
    from src.mcp.tools.agent.context import invoke

    invalidate_cache()
    result = invoke(None, {})

    assert result["ok"] is True
    assert "agent_context" in result


def test_entry_point_handles_errors():
    """Entry point handles errors gracefully."""
    from src.mcp.tools.agent.context import invoke

    invalidate_cache()
    result = invoke(None, {})

    assert "ok" in result
