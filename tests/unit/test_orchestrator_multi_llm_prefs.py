import pytest
import asyncio
from src.services.orchestrator import Orchestrator, OrchestrationContext, Step


class DummyLLM:
    def __init__(self, name: str):
        self.name = name
        self.last_prompt = None

    async def complete(self, prompt: str, **kwargs):
        # record and echo back the prompt so tests can assert
        self.last_prompt = prompt
        return f"{self.name}:{prompt}"


@pytest.mark.asyncio
async def test_resolve_client_priority():
    planner = DummyLLM("planner")
    workerA = DummyLLM("workerA")
    orch = Orchestrator(llm=None, llm_clients={"planner": planner, "workerA": workerA}, default_model="demo")
    orch.main_llm_name = "planner"
    # global preference
    orch.tool_preferences = {"search": "workerA"}

    # explicit assignee should win
    step = Step(id="1", action="answer", input={}, meta={"assignee": "workerA"})
    ctx = OrchestrationContext(goal="g")
    assert orch.resolve_client_for_step(step, ctx) == "workerA"

    # session prefs override
    step2 = Step(id="2", action="search", input={}, meta={})
    ctx2 = OrchestrationContext(goal="g", vars={"llm_preferences": {"search": "planner"}})
    assert orch.resolve_client_for_step(step2, ctx2) == "planner"

    # global prefs used when no session override
    ctx3 = OrchestrationContext(goal="g")
    assert orch.resolve_client_for_step(step2, ctx3) == "workerA"

    # default main used if no prefs
    step3 = Step(id="3", action="other", input={}, meta={})
    assert orch.resolve_client_for_step(step3, OrchestrationContext(goal="g")) == "planner"


@pytest.mark.asyncio
async def test_call_model_on_fallback_to_main():
    planner = DummyLLM("planner")
    orch = Orchestrator(llm=None, llm_clients={"planner": planner}, default_model="demo")
    orch.main_llm_name = "planner"

    # requesting a missing client should fallback to main
    res = await orch.call_model_on("missing", "hello world")
    assert res.startswith("planner:")


@pytest.mark.asyncio
async def test_agent_role_prefix_applied():
    planner = DummyLLM("planner")
    orch = Orchestrator(llm=None, llm_clients={"planner": planner}, default_model="demo")
    orch.main_llm_name = "planner"
    orch.agent_roles = {"researcher": "You are a careful researcher: cite sources when possible."}

    step = Step(id="r1", action="answer", input={"query": "Summarize X"}, meta={})
    ctx = OrchestrationContext(goal="Summarize X", vars={"agent_role": "researcher"})

    out = await orch._execute_step(step, ctx)
    assert "researcher" in planner.last_prompt.lower() or "cite" in planner.last_prompt.lower()
    assert out.get("assignee") == "planner"
    assert out.get("text", "").startswith("planner:")
