import pytest

from src.services.orchestrator import (
    Orchestrator,
    OrchestrationContext,
    OrchestrationResult,
)


@pytest.mark.asyncio
async def test_llm_call_count_tracks_planning(monkeypatch):
    """Planning calls (even with count_call=False) should increment llm_call_count."""
    orch = Orchestrator(default_model="test-model")
    orch.llm = object()

    async def fake_call_model(self, prompt: str, **kwargs):  # type: ignore[unused-argument]
        return {"text": "[\"do something\"]", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}

    orch.call_model = fake_call_model.__get__(orch, Orchestrator)  # type: ignore[assignment]

    result = OrchestrationResult(goal="planning-test")
    orch.llm_call_count = 0
    orch._llm_metrics = []

    await orch.call_model_with_metrics(
        "prompt",
        result=result,
        purpose="todo_list_creation",
        count_call=False,  # Explicitly disabled to verify metrics-based fallback
    )

    assert orch.llm_call_count == 1
    assert result.llm_call_count == 1
    assert len(orch._llm_metrics) == 1


@pytest.mark.asyncio
async def test_fast_planner_stub(monkeypatch):
    """When fast test flag is set, the planner should return a minimal graph-focused TODO list."""
    monkeypatch.setenv("CINECA_TEST_FAST_LLM", "true")

    orch = Orchestrator(llm_clients={"stub": object()}, default_model="phi3:mini")
    orch.main_llm_name = "stub"

    async def fake_get_main_llm(self, _tenant):
        return "stub"

    orch.get_main_llm = fake_get_main_llm.__get__(orch, Orchestrator)  # type: ignore[assignment]

    ctx = OrchestrationContext(
        goal="How many :Blast nodes are there?",
        user_id=None,
        session_id="sess",
        tenant_id="tenant",
        principal=None,
        force_full_agentic=False,
        vars={},
    )

    todos = await orch._create_agent_todo_list(ctx.goal, ctx, result=None)

    assert len(todos) == 3
    assert "graph.generate_cypher" in todos[0]["task"]
    assert todos[2].get("expect_evidence") is False
