import asyncio
import json

import pytest

from src.services import get_orchestrator


class DummyLLM:
    def __init__(self, name):
        self.name = name

    async def complete(self, prompt: str, **kwargs):
        return json.dumps(
            {
                "steps": [
                    {"id": "s1", "action": "answer", "input": {"query": "First step"}, "meta": {"assignee": "workerA"}},
                    {
                        "id": "s2",
                        "action": "answer",
                        "input": {"query": "Second step"},
                        "meta": {"assignee": "workerB"},
                    },
                ]
            }
        )


@pytest.mark.asyncio
async def test_orchestrator_delegates_to_named_clients(monkeypatch):
    Orchestrator = get_orchestrator()

    # Create dummy clients
    workerA = DummyLLM("workerA")
    workerB = DummyLLM("workerB")
    planner = DummyLLM("planner")

    orch = Orchestrator(llm=planner, llm_clients={"planner": planner, "workerA": workerA, "workerB": workerB})

    # Plan and run
    res = await orch.run("Demo goal", session_id="test-session")
    assert res.ok
    data = res.data
    assert data and "steps" in data
    # outputs should contain two entries with assignee info
    outputs = data.get("outputs")
    assert any(o.get("output", {}).get("assignee") == "workerA" for o in outputs)
    assert any(o.get("output", {}).get("assignee") == "workerB" for o in outputs)
