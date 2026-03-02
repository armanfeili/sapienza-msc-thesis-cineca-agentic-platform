import asyncio

import pytest

from src.services.orchestrator import OrchestrationContext, OrchestrationResult, Orchestrator


def test_memgraph_count_extraction_prefers_count_field():
    """Ensure memgraph summary uses numeric count column instead of rowcount."""
    orch = Orchestrator()
    rows = [{"b_count": 39}]
    query_output = {"rows": rows, "rowcount": 1}

    count_val = orch._extract_memgraph_count(rows, query_output)
    assert count_val == 39

    summary_text = orch._format_memgraph_count_text(label="Blast", count=count_val)
    assert summary_text == "There are 39 :Blast nodes."


def test_unexecuted_tool_warning_promoted():
    """Mentioned tool without execution should land in result warnings."""
    orch = Orchestrator()
    orch.tools["graph.search"] = lambda **kwargs: {}
    result = OrchestrationResult(goal="warn")

    orch._append_unexecuted_tool_warnings(["Use graph.search to find nodes"], result)

    assert result.warnings, "Expected warning for unexecuted graph.search tool"
    assert "graph.search" in result.warnings[0]


@pytest.mark.asyncio
async def test_memgraph_direct_final_output_uses_summary_count():
    """Memgraph direct path should surface semantic count, not rowcount."""
    orch = Orchestrator()
    orch.register_tool(
        "graph.generate_cypher",
        lambda payload, **_: {"cypher": "MATCH (b:Blast) RETURN count(b) AS b_count", "params": {}},
    )
    orch.register_tool(
        "graph.secure_query",
        lambda payload, **_: {"ok": True, "rows": [{"b_count": 39}], "rowcount": 1},
    )

    ctx = OrchestrationContext(goal="Count :Blast nodes", vars={"backend_type": "graph:memgraph"})
    result = OrchestrationResult(goal=ctx.goal)
    todos = [
        {"task": "Summarize graph results", "meta": {"mode": "memgraph_direct", "memgraph_task": "summarize"}, "status": "completed"}
    ]

    await orch._execute_memgraph_direct_todo(
        todo_idx=0,
        todo=todos[0],
        goal=ctx.goal,
        ctx=ctx,
        result=result,
    )

    orch._append_final_output(todos, ctx, result)

    final_outputs = [out for out in result.outputs if out.get("step_id") == "final-output"]
    assert final_outputs, "Final output step should be appended"
    assert final_outputs[0]["output"]["text"] == "There are 39 :Blast nodes."

    summary_outputs = [out for out in result.outputs if out.get("action") == "memgraph.summary"]
    assert summary_outputs and summary_outputs[0]["output"]["count"] == 39

    aggregated = result.to_dict()["output"]
    assert aggregated.strip() == "There are 39 :Blast nodes."


def test_memgraph_direct_collapses_duplicate_summary_todos():
    """Duplicate summary tasks should be collapsed into one with metadata preserved."""
    orch = Orchestrator()
    ctx = OrchestrationContext(goal="How many :Blast nodes?", vars={"memgraph_prompt_expected_pattern": "(b:Blast)"})
    params = {"category": "read_only", "todo_mode": "optional", "memgraph_prompt_id": "p01"}
    todos = [
        {"task": "Generate and execute Cypher", "status": "pending"},
        {"task": "Summarize graph query results", "status": "pending"},
        {"task": "Summarize graph query results duplicate", "status": "pending"},
    ]

    optimized = orch._tag_memgraph_todos_for_direct_execution(todos, ctx.goal, ctx, params)

    summaries = [t for t in optimized if (t.get("meta") or {}).get("memgraph_task") == "summarize"]
    assert len(summaries) == 1, "Duplicate summarize tasks should be collapsed"
    collapsed = (summaries[0].get("meta") or {}).get("collapsed_summaries") or []
    assert collapsed and "duplicate" in collapsed[0].lower()


@pytest.mark.asyncio
async def test_memgraph_summary_step_recorded_when_suppressed():
    """Even suppressed summaries should produce a recorded step for observability."""
    orch = Orchestrator()
    ctx = OrchestrationContext(goal="Count :Blast nodes", vars={"last_graph_count": 7})
    result = OrchestrationResult(goal=ctx.goal)
    todo = {
        "task": "Summarize graph results silently",
        "meta": {"mode": "memgraph_direct", "memgraph_task": "summarize", "suppress_output": True},
        "status": "completed",
    }

    handled = await orch._execute_memgraph_direct_todo(
        todo_idx=1,
        todo=todo,
        goal=ctx.goal,
        ctx=ctx,
        result=result,
    )

    assert handled is True
    assert any(step.action == "memgraph.summary" for step in result.steps)
    outputs = [out for out in result.outputs if out.get("action") == "memgraph.summary"]
    assert outputs and outputs[0]["output"].get("suppressed") is True


def test_random_rewrite_adds_order_by_rand_with_limit():
    """Sampling rewrite should inject ORDER BY rand() and enforce LIMIT."""
    orch = Orchestrator()
    rewritten = orch._rewrite_random_memgraph_query("MATCH (b:Blast) RETURN b", 10)
    assert "ORDER BY rand()" in rewritten
    assert rewritten.strip().upper().endswith("LIMIT 10")


@pytest.mark.asyncio
async def test_memgraph_response_builder_respects_env_minimal(monkeypatch):
    """MEMGRAPH_NL_VERBOSE_ANSWER=false should yield deterministic response without LLM."""
    orch = Orchestrator()
    monkeypatch.setenv("MEMGRAPH_NL_VERBOSE_ANSWER", "false")
    ctx = OrchestrationContext(goal="Show 10 random :Blast nodes", vars={"backend_type": "graph:memgraph", "memgraph_prompt_id": "p03"})
    result = OrchestrationResult(goal=ctx.goal)

    rows = [{"b": {"dbname": "NBFC_DB", "blasttype": "blastn", "status": "Complete", "blast_version": "2.15"}}]
    result.outputs.append(
        {
            "step_id": "todo-0-direct-query",
            "action": "graph.secure_query",
            "output": {
                "ok": True,
                "rows": rows,
                "rowcount": 1,
                "cypher": "MATCH (b:Blast) RETURN b LIMIT 10",
            },
            "started_at": "now",
            "finished_at": "now",
        }
    )

    todos = [
        {
            "task": "Generate and execute Cypher",
            "status": "completed",
            "evidence": ["graph.generate_cypher", "graph.secure_query"],
        }
    ]

    response = await orch._maybe_build_memgraph_response(goal=ctx.goal, ctx=ctx, result=result, todos=todos)

    assert response, "Response builder should return text"
    assert "Query used" in response
    assert "Blast" in response
    assert "NBFC_DB" in response
    assert ctx.vars.get("memgraph_response_verbose") is False


@pytest.mark.asyncio
async def test_memgraph_response_builder_uses_llm_when_available(monkeypatch):
    """LLM builder path should not raise NameError and should surface LLM text."""
    orch = Orchestrator()
    ctx = OrchestrationContext(goal="Show 10 random :Blast nodes", vars={"backend_type": "graph:memgraph", "memgraph_prompt_id": "p03"})
    result = OrchestrationResult(goal=ctx.goal)

    rows = [{"b": {"dbname": "DB_A", "blasttype": "blastn", "status": "Complete"}}]
    result.outputs.append(
        {
            "step_id": "todo-0-direct-query",
            "action": "graph.secure_query",
            "output": {
                "ok": True,
                "rows": rows,
                "rowcount": 1,
                "cypher": "MATCH (b:Blast) RETURN b ORDER BY rand() LIMIT 10",
            },
        }
    )

    todos = [
        {"task": "Generate and execute Cypher", "status": "completed", "evidence": ["graph.generate_cypher", "graph.secure_query"]}
    ]

    async def fake_llm(prompt_text, **_):
        return "LLM summary with dbname=DB_A and blasttype=blastn"

    monkeypatch.setattr(orch, "call_model_with_metrics", fake_llm)
    orch.llm = object()  # mark LLM available

    response = await orch._maybe_build_memgraph_response(goal=ctx.goal, ctx=ctx, result=result, todos=todos)

    assert response and ("LLM summary" in response or "dbname" in response)
    assert "DB_A" in response or "blasttype" in response
    assert not result.warnings, "LLM builder should not emit warnings on success"


@pytest.mark.asyncio
async def test_memgraph_response_builder_fallback_includes_properties(monkeypatch):
    """Fallback path should still expose properties when LLM fails."""
    orch = Orchestrator()
    ctx = OrchestrationContext(goal="Show 10 random :Blast nodes", vars={"backend_type": "graph:memgraph", "memgraph_prompt_id": "p03"})
    result = OrchestrationResult(goal=ctx.goal)

    rows = [{"b": {"dbname": "DB_B", "blast_version": "2.15", "status": "Complete"}}]
    result.outputs.append(
        {
            "step_id": "todo-0-direct-query",
            "action": "graph.secure_query",
            "output": {
                "ok": True,
                "rows": rows,
                "rowcount": 1,
                "cypher": "MATCH (b:Blast) RETURN b ORDER BY rand() LIMIT 10",
            },
        }
    )
    todos = [{"task": "Generate and execute Cypher", "status": "completed", "evidence": ["graph.secure_query"]}]

    async def failing_llm(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(orch, "call_model_with_metrics", failing_llm)
    orch.llm = object()

    response = await orch._maybe_build_memgraph_response(goal=ctx.goal, ctx=ctx, result=result, todos=todos)

    assert response, "Fallback should still return text"
    assert "DB_B" in response and "2.15" in response, response
    assert "<value>" not in response
    assert result.warnings, "Builder failure should be surfaced as warning"


@pytest.mark.asyncio
async def test_memgraph_response_builder_includes_real_values(monkeypatch):
    """Examples in the Memgraph response should use real values, not <value> placeholders."""
    orch = Orchestrator()
    ctx = OrchestrationContext(goal="Show 10 random :Blast nodes", vars={"backend_type": "graph:memgraph", "memgraph_prompt_id": "p03"})
    result = OrchestrationResult(goal=ctx.goal)

    rows = [
        {
            "n": {
                "dbname": "Real_DB",
                "blasttype": "blastn",
                "status": "Complete",
                "blast_version": "2.15",
                "output_result": "demo_run",
            }
        }
    ]
    result.outputs.append(
        {
            "step_id": "todo-0-direct-query",
            "action": "graph.secure_query",
            "output": {"ok": True, "rows": rows, "rowcount": 1, "cypher": "MATCH (n:Blast) RETURN n LIMIT 10"},
        }
    )
    todos = [{"task": "Generate and execute Cypher", "status": "completed", "evidence": ["graph.secure_query"]}]

    monkeypatch.setenv("RUN_LLM_SMOKE", "false")  # force template path for determinism
    response = await orch._maybe_build_memgraph_response(goal=ctx.goal, ctx=ctx, result=result, todos=todos)

    assert "Real_DB" in response and "demo_run" in response
    assert "<value>" not in response


@pytest.mark.asyncio
async def test_memgraph_response_step_latency_recorded(monkeypatch):
    """memgraph-response step should report non-zero latency and mirror builder timing."""
    orch = Orchestrator()
    ctx = OrchestrationContext(goal="Show 10 random :Blast nodes", vars={"backend_type": "graph:memgraph", "memgraph_prompt_id": "p03"})
    result = OrchestrationResult(goal=ctx.goal)

    rows = [{"n": {"dbname": "Slow_DB", "status": "Pending"}}]
    result.outputs.append(
        {
            "step_id": "todo-0-direct-query",
            "action": "graph.secure_query",
            "output": {"ok": True, "rows": rows, "rowcount": 1, "cypher": "MATCH (n:Blast) RETURN n LIMIT 10"},
        }
    )
    todos = [{"task": "Generate and execute Cypher", "status": "completed", "evidence": ["graph.secure_query"]}]

    async def slow_llm(*args, **kwargs):
        await asyncio.sleep(0.01)
        return "LLM summary with real data"

    monkeypatch.setattr(orch, "call_model_with_metrics", slow_llm)
    orch.llm = object()

    response = await orch._maybe_build_memgraph_response(goal=ctx.goal, ctx=ctx, result=result, todos=todos)
    assert response

    step = next((s for s in result.steps if getattr(s, "id", None) == "memgraph-response"), None)
    assert step and step.latency_ms and step.latency_ms > 0
    output_step = next((out for out in result.outputs if out.get("step_id") == "memgraph-response"), None)
    assert output_step and output_step.get("latency_ms", 0) == step.latency_ms
