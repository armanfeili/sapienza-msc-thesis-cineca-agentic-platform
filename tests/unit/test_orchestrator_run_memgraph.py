import asyncio
import pytest

from src.services.orchestrator import OrchestrationContext, Orchestrator, Step


@pytest.mark.asyncio
async def test_run_trivial_fast_path_skips_todos():
    async def fake_query(payload=None, **kwargs):
        return {"ok": True, "rows": [{"count": 3}], "count": 3}

    orch = Orchestrator(tools={"graph.query": fake_query})
    goal = "How many :Film nodes are there?"
    params = {"category": "read_only", "todo_mode": "optional"}

    res = await orch.run(goal, params=params)
    assert res.ok is True
    data = res.data
    assert data["todos"][0]["status"] == "completed"
    assert any(step["action"] == "graph.query" for step in data["steps"])
    assert data["metrics"]["timeout_stage"] in (None, "none")


@pytest.mark.asyncio
async def test_run_memgraph_simple_mode_executes_generate_and_query(monkeypatch):
    async def fake_generate(payload=None, **kwargs):
        return {"cypher": "MATCH (n:Movie) RETURN n", "params": {}}

    async def fake_query(payload=None, **kwargs):
        return {"ok": True, "rows": [{"name": "Inception"}]}

    orch = Orchestrator(
        tools={
            "graph.generate_cypher": fake_generate,
            "graph.query": fake_query,
        }
    )

    params = {"category": "read_only", "todo_mode": "none", "memgraph_prompt_id": "p1"}
    res = await orch.run("List :Movie nodes", params=params)

    assert res.ok is True
    data = res.data
    # Simple mode suppresses public TODOs
    assert data["todos"] == []
    # Steps should include both generate and query actions
    actions = {step["action"] for step in data["steps"]}
    assert "graph.generate_cypher" in actions
    assert "graph.query" in actions


@pytest.mark.asyncio
async def test_run_memgraph_force_llm_uses_agentic_path(monkeypatch):
    class FakeLLM:
        async def complete(self, prompt=None, **kwargs):
            # Simple plan with one step
            return '{"steps": [{"id": "1", "action": "answer", "input": {"query": "done"}}]}'

    async def fake_answer_tool(payload=None, **kwargs):
        return {"ok": True, "text": "done"}

    orch = Orchestrator(llm=FakeLLM(), tools={"graph.generate_cypher": fake_answer_tool})

    # Avoid LLM during plan by overriding plan to a deterministic step
    async def fake_plan(goal, ctx, result=None):
        from src.services.orchestrator import Step

        return [Step(id="1", action="answer", input={"query": "done"})]

    monkeypatch.setattr(orch, "plan", fake_plan)

    params = {
        "category": "read_only",
        "todo_mode": "none",
        "memgraph_prompt_id": "p1",
        "memgraph_force_llm": True,
    }

    res = await orch.run("List :Movie nodes with reasoning", params=params)

    assert res.ok is True
    data = res.data
    assert data["todos"]  # Agentic path keeps TODOs
    assert data["metrics"]["timeout_stage"] in (None, "none")


@pytest.mark.asyncio
async def test_secure_query_autofills_last_cypher(monkeypatch):
    captured = {}

    async def fake_generate(payload=None, **kwargs):
        return {"cypher": "MATCH (n:Blast) RETURN n LIMIT $limit", "params": {"limit": 25}}

    async def fake_secure(payload=None, **kwargs):
        captured.update(payload or {})
        return {"ok": True, "rows": []}

    orch = Orchestrator(
        tools={
            "graph.generate_cypher": fake_generate,
            "graph.secure_query": fake_secure,
        }
    )
    ctx = OrchestrationContext(goal="Count :Blast nodes", tenant_id="tenant-1", principal={"id": "user-1"})

    step_gen = Step(id="gen", action="graph.generate_cypher", input={})
    step_secure = Step(id="secure", action="graph.secure_query", input={"action": "execute"})

    await orch._execute_step(step_gen, ctx)
    await orch._execute_step(step_secure, ctx)

    assert captured.get("cypher") == "MATCH (n:Blast) RETURN n LIMIT $limit"
    assert captured.get("params") == {"limit": 25}
    # principal should be normalized to an ID string for the tool
    assert captured.get("principal") in ("user-1", {"id": "user-1"})
