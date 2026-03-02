Memgraph NL direct mode (read-only)
-----------------------------------

- When prompt hints mark `category=read_only` and `todo_mode=optional`, the orchestrator tags TODOs with `requires_llm_planning=false` and `meta.mode=memgraph_direct`.
- Exactly one TODO is forced to run the graph query path (via `graph.generate_cypher` then `graph.secure_query`/`graph.query`); summary TODOs reuse the count without extra LLM calls.
- The new TODO fields round-trip through the API (`requires_llm_planning`, `meta`), so clients can debug which steps ran without per-TODO planning.
- If `memgraph_force_llm` or non-read-only categories are used, the orchestrator falls back to the standard agentic planning path (per-TODO LLM allowed).
