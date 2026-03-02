from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(slots=True)
class StepResult:
    """Summary of a single orchestration step/tool call."""

    index: int
    name: str
    status: str
    duration_ms: int | None = None


@dataclass(slots=True)
class RunSummary:
    """Structured view of an agent run for the Q&A chart."""

    prompt: str = "<unknown>"
    llm_call_count: int = 0
    llm_calls_detail: List[str] = field(default_factory=list)
    llm_call_purposes: List[str] = field(default_factory=list)
    llm_bypass_reason: str | None = None
    agent_llm_calls: int | None = None
    healthcheck_llm_calls: int = 0
    model_instance: str = "<unknown>"
    model_id: str = "<unknown>"
    model_provider: str = "<unknown>"
    todo_count: int = 0
    todos_open: int = 0
    step_count: int = 0
    step_results: List[StepResult] = field(default_factory=list)
    final_status: str = "unknown"
    final_output_summary: str = ""
    final_result_details: str = ""
    total_duration_ms: int = 0
    tool_call_count: int = 0
    model_warmed_before_run: bool | None = None
    model_warmup_ms: int | None = None
    first_llm_call_ms: int | None = None
    mcp_tools_loaded_at_startup: bool | None = None


def _format_duration(ms: int | None) -> str:
    if ms is None:
        return "n/a"
    if ms >= 1000:
        seconds = ms / 1000
        return f"{seconds:.2f}s ({ms} ms)"
    return f"{ms} ms"


def _format_bool(value: bool | None, true_text: str, false_text: str) -> str:
    if value is True:
        return true_text
    if value is False:
        return false_text
    return "Unknown"


def render_run_summary_chart(summary: RunSummary, header: str | None = None) -> str:
    """Render a fixed-order Q&A chart summarizing an agent run."""

    header = header or "RUN SUMMARY"

    agent_llm_calls = (
        summary.agent_llm_calls
        if summary.agent_llm_calls is not None
        else summary.llm_call_count
    )

    # Prepare answers for each canonical question (order matters!).
    if agent_llm_calls == 0:
        if summary.llm_bypass_reason:
            llm_answer = f"No LLM calls in this run (reason: {summary.llm_bypass_reason})."
        else:
            llm_answer = "No LLM calls in this run."
    else:
        detail_answer = "; ".join(summary.llm_call_purposes or summary.llm_calls_detail)
        llm_answer = detail_answer or "LLM calls recorded, but purposes unavailable."

    step_answer = (
        "No steps recorded."
        if not summary.step_results
        else "; ".join(
            f"[{step.index}] {step.name} - {step.status}"
            + (f" ({_format_duration(step.duration_ms)})" if step.duration_ms is not None else "")
            for step in summary.step_results
        )
    )

    warmup_ms = summary.first_llm_call_ms if summary.first_llm_call_ms is not None else summary.model_warmup_ms
    if warmup_ms is None:
        warmup_answer = "No warmup metric recorded in this run."
    elif warmup_ms == 0:
        warmup_answer = "Warmup recorded before this run (0 ms first-call latency)."
    else:
        warmup_answer = f"First-call latency recorded in this run: {warmup_ms} ms."

    qa_pairs = [
        ("What prompt was executed?", summary.prompt or "Not available in run metadata"),
        ("How many LLM calls were made in this run?", str(agent_llm_calls)),
        ("For what purpose was the LLM called each time?", llm_answer),
        (
            "Which LLM model instance was used?",
            f"{summary.model_instance} (model={summary.model_id}, provider={summary.model_provider})",
        ),
        (
            "How many TODOs were created by the orchestrator?",
            f"{summary.todo_count} (open TODOs: {summary.todos_open})",
        ),
        ("How many execution steps/tasks were run in total?", str(summary.step_count)),
        ("What was the outcome of each step/task?", step_answer),
        (
            "What was the final status/result of the prompt?",
            f"{summary.final_status} ("
            + (
                (summary.final_output_summary or "no output summary")
                + (
                    f", result: {summary.final_result_details}"
                    if summary.final_result_details
                    else ""
                )
            )
            + ")",
        ),
        ("How long did the entire command/run take?", _format_duration(summary.total_duration_ms)),
        ("How many tool invocations were performed in this run?", str(summary.tool_call_count)),
        ("Warmup/first-call latency observed in this run?", warmup_answer),
        (
            "Were MCP tools loaded before this run, or discovered during this run?",
            _format_bool(
                summary.mcp_tools_loaded_at_startup,
                "Loaded at startup from manifest",
                "Loaded dynamically in this run",
            ),
        ),
    ]

    question_col_width = 62
    border = "=" * (question_col_width + 40)
    separator = "-" * question_col_width + "|" + "-" * 39

    lines = [border, f"{header:^{question_col_width + 40}}", border]
    lines.append(f"{'Question'.ljust(question_col_width)} | Answer")
    lines.append(separator)
    for question, answer in qa_pairs:
        lines.append(f"{question.ljust(question_col_width)} | {answer}")
    lines.append(border)
    return "\n".join(lines)
