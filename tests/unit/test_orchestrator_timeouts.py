import asyncio
import pytest

from src.services.orchestrator import Orchestrator


@pytest.mark.asyncio
async def test_planning_timeout_sets_timeout_stage(monkeypatch):
    orch = Orchestrator()

    # Force very small timeout
    monkeypatch.setattr("src.services.orchestrator.STEP_TIMEOUT_SECONDS", 0.01)

    async def slow_create(goal, ctx, result=None):
        await asyncio.sleep(0.05)
        return []

    monkeypatch.setattr(orch, "_create_agent_todo_list", slow_create)

    res = await orch.run("Slow planning goal")

    assert res.ok is False
    data = res.data
    assert data["metrics"]["timeout_stage"] == "planning_todo_list"
    assert data["metrics"]["overall_ms"] > 0


@pytest.mark.asyncio
async def test_step_timeout_sets_metrics(monkeypatch):
    orch = Orchestrator()
    monkeypatch.setattr("src.services.orchestrator.STEP_TIMEOUT_SECONDS", 0.01)

    async def fake_plan(goal, ctx, result=None):
        from src.services.orchestrator import Step

        return [Step(id="s1", action="custom.sleep", input={})]

    async def slow_execute(step, ctx):
        await asyncio.sleep(0.05)
        return {}

    monkeypatch.setattr(orch, "plan", fake_plan)
    monkeypatch.setattr(orch, "_execute_step", slow_execute)

    res = await orch.run("Goal that times out")

    assert res.ok is False
    data = res.data
    assert "timeout_stage" in data["metrics"]
    assert "execute_todo" in data["metrics"]["timeout_stage"]
    assert data["metrics"]["overall_ms"] > 0
