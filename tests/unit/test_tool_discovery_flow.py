import pytest

from src.services.orchestrator import OrchestrationContext, OrchestrationResult, Orchestrator


@pytest.mark.asyncio
async def test_tool_discovery_reuse_and_format_and_storage(monkeypatch):
    discover_calls = {"count": 0}
    cached_values: dict[str, str] = {}

    async def fake_discover(payload=None, **kwargs):
        discover_calls["count"] += 1
        return {"items": [{"name": "graph.query"}, {"name": "llm:worker"}]}

    class FakeCache:
        async def set(self, key, value, ttl=None):
            cached_values[key] = value

    orch = Orchestrator(
        tools={"catalog.discover": fake_discover},
        cache=FakeCache(),
    )

    ctx = OrchestrationContext(goal="List available tools", vars={})
    result = OrchestrationResult(goal=ctx.goal)

    todos = [
        {"task": "List available tools", "status": "pending"},
        {"task": "List available tools again", "status": "pending"},
        {"task": "Format tool list", "status": "pending"},
        {"task": "Store tools in cache", "status": "pending"},
    ]

    await orch._execute_todo_with_steps(todos, ctx.goal, ctx, result)

    # First todo called discover; second reused cached tools with zero-latency synthetic step
    assert discover_calls["count"] == 1
    assert any(out.get("output", {}).get("reused") for out in result.outputs)

    # Format step produced standardized output
    formatted = next(
        (out for out in result.outputs if out.get("action") == "format_tools_output"), None
    )
    assert formatted is not None
    formatted_output = formatted["output"]
    assert formatted_output["tools_count"] == 2
    assert "tools" in formatted_output and isinstance(formatted_output["tools"], list)
    assert "known_tools" in formatted_output

    # Storage step persisted to cache and surfaced stored_count
    storage_out = next(
        (out for out in result.outputs if out.get("action") == "store_tools"), None
    )
    assert storage_out is not None
    assert storage_out["output"]["stored_count"] == 2
    assert cached_values  # cache.set was invoked


@pytest.mark.asyncio
async def test_unexecuted_tool_mentions_append_warning(monkeypatch):
    orch = Orchestrator(tools={"graph.query": lambda **_: {}})
    ctx = OrchestrationContext(goal="Goal without execution", vars={})
    result = OrchestrationResult(goal=ctx.goal)

    # Avoid LLM and tool execution by returning an empty plan
    async def fake_plan(goal, ctx, result=None):
        return []

    monkeypatch.setattr(orch, "plan", fake_plan)

    todos = [{"task": "Use graph.query and summarize", "status": "pending"}]

    await orch._execute_todo_with_steps(todos, ctx.goal, ctx, result)

    assert any("graph.query" in warn for warn in result.warnings)
