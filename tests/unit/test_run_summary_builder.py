from typing import Any, Dict, List

from tests.integration import test_agent_memgraph_nl_prompts_v2 as memgraph_module


def _build_builder(monkeypatch, snapshot: Dict[str, Any]):
    builder = memgraph_module.TestAgentMemgraphNLPrompts()
    monkeypatch.setattr(memgraph_module, "_collect_orchestrator_config_snapshot", lambda: snapshot)
    return builder


def test_build_run_summary_prefers_db_provider(monkeypatch):
    snapshot = {
        "db_instance_name": "phi3-mini",
        "db_provider_model_id": "phi3:mini",
        "db_provider_name": "ollama-local",
        "model_name": "phi3-mini",
        "env_provider_name": "env-provider",
        "config_source": "db_default",
    }
    builder = _build_builder(monkeypatch, snapshot)

    summary = builder._build_run_summary(  # type: ignore[attr-defined]
        prompt_entry={"text": "Prompt"},
        status_data={"status": "succeeded"},
        metrics={"overall_ms": 10},
        steps=[],
        todos=[],
        llm_metrics=[],
        tool_metrics=[],
        llm_call_count=1,
        start_time=0.0,
        end_time=0.01,
    )

    assert summary.model_provider == "ollama-local"
    assert summary.model_instance == "phi3-mini"
    assert summary.model_id == "phi3:mini"


def test_build_run_summary_counts_todos_and_result(monkeypatch):
    snapshot = {
        "db_instance_name": "phi3-mini",
        "db_provider_model_id": "phi3:mini",
        "db_provider_name": "ollama-local",
        "model_name": "phi3-mini",
        "env_provider_name": None,
        "config_source": "db_default",
    }
    builder = _build_builder(monkeypatch, snapshot)
    builder.llm_smoke_metadata = {"healthcheck_llm_calls": 1}

    steps: List[Dict[str, Any]] = [
        {
            "type": "output",
            "step_id": "create-todos",
            "output": {
                "todos": [
                    {
                        "task": "Generate query",
                        "status": "completed",
                        "meta": {"mode": "simple_memgraph"},
                    }
                ]
            },
        },
        {
            "type": "output",
            "step_id": "final",
            "output": {
                "ok": True,
                "rows": [{"b_count": 39}],
            },
        },
    ]

    summary = builder._build_run_summary(  # type: ignore[attr-defined]
        prompt_entry={"text": "Prompt"},
        status_data={"status": "succeeded", "output": None},
        metrics={"overall_ms": 24, "tool_calls": 2},
        steps=steps,
        todos=[],
        llm_metrics=[],
        tool_metrics=[],
        llm_call_count=0,
        start_time=0.0,
        end_time=0.24,
    )

    assert summary.todo_count == 1
    assert summary.todos_open == 0
    assert summary.final_result_details == "b_count=39"
    assert summary.llm_bypass_reason == "simple_memgraph fast-path"
    assert summary.healthcheck_llm_calls == 1