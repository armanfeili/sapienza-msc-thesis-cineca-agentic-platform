import pytest

from src.services.orchestrator import OrchestrationContext, Orchestrator, Step


def test_infer_label_from_goal_variants():
    orch = Orchestrator(tools={})
    assert orch._infer_label_from_goal("How many :Movie nodes?") == "Movie"
    assert orch._infer_label_from_goal("Inspect :UserProfile123 relationships") == "UserProfile123"
    assert orch._infer_label_from_goal("No label here") is None


@pytest.mark.asyncio
async def test_generate_cypher_uses_explicit_query_without_inference():
    captured = {}

    async def fake_generate(payload=None, **kwargs):
        captured.update(payload or {})
        return {"ok": True}

    orch = Orchestrator(tools={"graph.generate_cypher": fake_generate})
    ctx = OrchestrationContext(goal="Count :Movie nodes")
    step = Step(id="s1", action="graph.generate_cypher", input={"query": "MATCH (n) RETURN n"})

    await orch._execute_step(step, ctx)

    assert captured["query"] == "MATCH (n) RETURN n"
    assert "label" not in captured


@pytest.mark.asyncio
async def test_generate_cypher_honors_explicit_label():
    captured = {}

    async def fake_generate(payload=None, **kwargs):
        captured.update(payload or {})
        return {"ok": True}

    orch = Orchestrator(tools={"graph.generate_cypher": fake_generate})
    ctx = OrchestrationContext(goal="List :Movie nodes")
    step = Step(id="s2", action="graph.generate_cypher", input={"label": "Movie"})

    await orch._execute_step(step, ctx)

    assert captured["label"] == "Movie"
    assert captured.get("query") is None


@pytest.mark.asyncio
async def test_generate_cypher_infers_label_from_goal():
    captured = {}

    async def fake_generate(payload=None, **kwargs):
        captured.update(payload or {})
        return {"ok": True}

    orch = Orchestrator(tools={"graph.generate_cypher": fake_generate})
    ctx = OrchestrationContext(goal="How many :Actor nodes exist?")
    step = Step(id="s3", action="graph.generate_cypher", input={})

    await orch._execute_step(step, ctx)

    assert captured["label"] == "Actor"
    # goal should be forwarded so downstream tools can use it
    assert captured["goal"] == ctx.goal


@pytest.mark.asyncio
async def test_generate_cypher_raises_clear_error_when_inference_fails():
    async def fake_generate(payload=None, **kwargs):
        return {"ok": True}

    orch = Orchestrator(tools={"graph.generate_cypher": fake_generate})
    ctx = OrchestrationContext(goal="List all nodes without labels")
    step = Step(id="s4", action="graph.generate_cypher", input={})

    with pytest.raises(ValueError):
        await orch._execute_step(step, ctx)


def test_generate_cypher_invoke_infers_label_from_goal():
    from src.mcp.tools.graph import generate_cypher

    result = generate_cypher.invoke(
        payload={"action": "select", "goal": "How many :Blast nodes are there?", "principal": "tester"}
    )

    assert result["ok"] is True
    assert result["read_only"] is True
    assert "MATCH (n:`Blast`)" in result["cypher"]
    assert result["params"]["limit"] == 25


def test_generate_cypher_invoke_respects_explicit_label_defaults():
    from src.mcp.tools.graph import generate_cypher

    result = generate_cypher.invoke(payload={"action": "select", "label": "Gene", "principal": "tester"})

    assert result["read_only"] is True
    assert result["cypher"].startswith("MATCH (n:`Gene`)")
    assert result["params"]["limit"] == 25
