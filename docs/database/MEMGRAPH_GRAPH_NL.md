# Memgraph Graph NL Path

This page documents the fast paths and safeguards for Memgraph natural‑language requests.

## Trivial count fast‑path
- Triggered when the goal looks like `How many :Label nodes ...` and `category=read_only`, `todo_mode` is empty/`optional`, and `force_full_agentic` is **false**.
- Runs a direct `MATCH (n:Label) RETURN count(n)` and returns immediately with a single TODO marked completed.

## Simple Memgraph mode
- Enabled when `category=read_only` and `todo_mode=none`, or via `MEMGRAPH_NL_SIMPLE_MODE=true`.
- Disabled when `memgraph_force_llm=true` or `FORCE_LLM_MEMGRAPH_TESTS` is set.
- Skips TODO planning and executes `graph.generate_cypher` + `graph.query` directly.
- Public TODOs are suppressed in this mode to avoid leaking internals.

## Label inference for `graph.generate_cypher`
- When both `query` and `label` are missing, the orchestrator tries to infer a label from the goal (e.g., `:Movie` → `Movie`).
- If inference fails, a clear `ValueError` is raised: `Missing label/query and unable to infer label from goal`.

## Tool discovery flow
- Tool‑discovery goals short‑circuit TODO planning and use a fixed TODO list: discover → format → (optional) store.
- Repeated discovery within the same run is skipped with a synthetic zero‑latency step and reuse markers.
- Formatting produces a standardized payload: `tools_count`, `tools`, `source_groups`, `known_tools`, `timestamp`.

## Timeouts and metrics
- `overall_ms` is tracked on the result and mirrored into `metrics["overall_ms"]`.
- `timeout_stage` is written both to the dataclass and metrics dictionary (e.g., `planning_todo_list`, `execute_todo[0]_step[0]`).
- Tool/LLM metrics roll up from per‑call records; `total_llm_calls` is derived from the metric list length.
