import pytest

from src.services.orchestrator import OrchestrationContext, OrchestrationResult, Orchestrator


def test_trivial_graph_count_detects_label_when_allowed():
    orch = Orchestrator()
    params = {"category": "read_only", "todo_mode": "optional"}
    label = orch._is_trivial_graph_count("How many :Blast nodes are there?", params, force_full_agentic=False)
    assert label == "Blast"


def test_trivial_graph_count_skips_when_force_full_agentic():
    orch = Orchestrator()
    params = {"category": "read_only", "todo_mode": "optional", "force_full_agentic": True}
    label = orch._is_trivial_graph_count("How many :Blast nodes are there?", params, force_full_agentic=True)
    assert label is None


@pytest.mark.asyncio
async def test_execute_trivial_graph_count_populates_outputs_and_todos():
    async def fake_query(payload=None, **kwargs):
        return {"ok": True, "rows": [{"count": 7}], "count": 7}

    orch = Orchestrator(tools={"graph.query": fake_query})
    ctx = OrchestrationContext(goal="How many :Movie nodes are there?")
    result = OrchestrationResult(goal=ctx.goal)

    service_result = await orch._execute_trivial_graph_count("Movie", ctx, result)

    assert service_result.ok is True
    data = service_result.data
    assert data["todos"][0]["status"] == "completed"
    assert any(out.get("action") == "answer" for out in data["outputs"])
    assert data["steps"][0]["action"] == "graph.query"


@pytest.mark.asyncio
async def test_optional_graph_fallback_records_count_and_context():
    async def fake_query(payload=None, **kwargs):
        return {"ok": True, "rows": [{"count": 5}], "count": 5}

    orch = Orchestrator(tools={"graph.query": fake_query})
    ctx = OrchestrationContext(goal="How many :User nodes exist?", vars={})
    result = OrchestrationResult(goal=ctx.goal)

    success = await orch._run_optional_graph_fallback(ctx.goal, ctx, result)

    assert success is True
    assert result.outputs[-1]["output"]["count"] == 5
    assert ctx.vars.get("cypher_queries")
    assert ctx.vars.get("last_graph_count") == 5


@pytest.mark.asyncio
async def test_optional_graph_fallback_returns_false_on_tool_error():
    async def failing_query(payload=None, **kwargs):
        return {"ok": False, "error": "boom"}

    orch = Orchestrator(tools={"graph.query": failing_query})
    ctx = OrchestrationContext(goal="How many :User nodes exist?", vars={})
    result = OrchestrationResult(goal=ctx.goal)

    success = await orch._run_optional_graph_fallback(ctx.goal, ctx, result)

    assert success is False
