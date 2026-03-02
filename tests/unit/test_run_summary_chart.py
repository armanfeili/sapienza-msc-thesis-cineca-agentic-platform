from tests.utils.run_summary import RunSummary, StepResult, render_run_summary_chart


def test_render_run_summary_chart_contains_all_questions_with_results():
    summary = RunSummary(
        prompt="Count Blast nodes",
        llm_call_count=2,
        agent_llm_calls=2,
        llm_calls_detail=["#1: todo_list_creation (success, 120 ms)", "#2: execution (success, 95 ms)"],
        llm_call_purposes=["#1: todo_list_creation", "#2: execution"],
        model_instance="phi3-mini",
        model_id="phi3:mini",
        model_provider="ollama-local",
        todo_count=1,
        todos_open=0,
        step_count=2,
        step_results=[
            StepResult(index=1, name="Create TODO list", status="success", duration_ms=150),
            StepResult(index=2, name="graph.query", status="error", duration_ms=45),
        ],
        final_status="succeeded",
        final_output_summary="Output=NoneType",
        final_result_details="b_count=39",
        total_duration_ms=245,
        tool_call_count=2,
        model_warmed_before_run=True,
        model_warmup_ms=1200,
        first_llm_call_ms=None,
        mcp_tools_loaded_at_startup=False,
    )

    chart = render_run_summary_chart(summary, header="RUN SUMMARY (unit test)")

    questions = [
        "What prompt was executed?",
        "How many LLM calls were made in this run?",
        "For what purpose was the LLM called each time?",
        "Which LLM model instance was used?",
        "How many TODOs were created by the orchestrator?",
        "How many execution steps/tasks were run in total?",
        "What was the outcome of each step/task?",
        "What was the final status/result of the prompt?",
        "How long did the entire command/run take?",
        "How many tool invocations were performed in this run?",
        "Warmup/first-call latency observed in this run?",
        "Were MCP tools loaded before this run, or discovered during this run?",
    ]

    for question in questions:
        assert chart.count(question) == 1

    assert "Count Blast nodes" in chart
    assert "#1: todo_list_creation" in chart
    assert "Create TODO list" in chart
    assert "result: b_count=39" in chart
    assert "Loaded dynamically in this run" in chart


def test_render_run_summary_chart_simple_memgraph_fast_path():
    summary = RunSummary(
        prompt="How many Blast nodes?",
        llm_call_count=0,
        agent_llm_calls=0,
        llm_bypass_reason="simple_memgraph fast-path",
        model_instance="phi3-mini",
        model_id="phi3:mini",
        model_provider="ollama-local",
        todo_count=1,
        todos_open=0,
        step_count=6,
        step_results=[
            StepResult(index=1, name="Create TODO list", status="success", duration_ms=0),
            StepResult(index=2, name="graph.generate_cypher", status="success", duration_ms=10),
        ],
        final_status="succeeded",
        final_output_summary="Output=NoneType",
        total_duration_ms=24,
        tool_call_count=2,
        model_warmed_before_run=True,
        model_warmup_ms=0,
        first_llm_call_ms=0,
        mcp_tools_loaded_at_startup=True,
    )

    chart = render_run_summary_chart(summary)

    assert "provider=ollama-local" in chart
    assert "1 (open TODOs: 0)" in chart
    assert "How many tool invocations were performed in this run?          | 2" in chart
    assert "How many LLM calls were made in this run?                      | 0" in chart
    assert "reason: simple_memgraph fast-path" in chart
