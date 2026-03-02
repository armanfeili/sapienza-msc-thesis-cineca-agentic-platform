## A. High-level understanding (1–7)

1. **Give me a detailed high-level overview of this project:** what it does, who it’s for, and how all major components fit together, based only on the repository content.
2. **Identify the main architectural layers** (API, services, data, security, UIs, workers, etc.) and describe the responsibility of each layer.
3. **Describe the primary use cases** this platform enables for end users, administrators, and developers.
4. **Summarize all core domain concepts and entities** (agents, runs, sessions, steps, jobs, tools, tenants, providers, models, graph nodes/relations).
5. **Explain the typical lifecycle of an “agent run”** from HTTP request to final response, referencing the actual code paths.
6. **Explain the typical lifecycle of a background job** from creation to completion, including how workers and queues are used.
7. **Based on the code and docs, what assumptions does this project make** about its deployment environment and target organizations (e.g., multi-tenant, security requirements, infra expectations)?

---

## B. Architecture & design (8–15)

8. **Draw a mental architecture diagram** (described in text) of the system: show all major services, databases, and interconnections inferred from the code.
9. **Explain how the API layer is structured** (routers, dependencies, schemas) and how it interacts with the service layer and repositories.
10. **Describe the repository pattern used for PostgreSQL access:** which repositories exist, how they are organized, and how they enforce multi-tenancy.
11. **Explain how Redis is used across the system** (caching, queues, rate limiting, session state, idempotency, etc.) and point to the relevant modules.
12. **Explain the role of Memgraph in the architecture**: which modules interact with it, and for what types of operations.
13. **Describe the configuration system:** how settings are loaded (env, config modules) and how compute/runtime configuration is derived.
14. **Identify and explain all cross-cutting concerns** (logging, metrics, tracing, auth, rate limiting, PII scrubbing, error handling) and where they are implemented.
15. **Highlight the main architectural strengths and weaknesses** of the design as implemented (e.g., modularity, coupling, clarity, extensibility).

---

## C. Security, multi-tenancy & governance (16–22)

16. **Explain the full authentication flow** (OIDC/JWT, JWKS, issuer/audience checks) and where in the code this is enforced.
17. **Describe the authorization model (RBAC and scopes)**: how roles, scopes, and policies are defined, and how endpoints and tools enforce them.
18. **Explain how multi-tenancy is implemented** at the database and service level: how tenant IDs flow through the system and how tenant isolation is ensured.
19. **Describe all rate-limiting mechanisms** in the project: how they work, where they are enforced, and what is configurable.
20. **Identify how PII scrubbing and output guarding work**, including where sensitive data is detected and masked and how responses are sanitized.
21. **Describe the auditing approach**: which events are logged, where audit data is stored, and how it could be used for compliance.
22. **From a security perspective, list the main strengths and potential weaknesses** you see in the current implementation, based purely on the code.

---

## D. LLM providers, resilience & cost (23–28)

23. **Explain how LLM providers are modeled and configured** (providers, model instances, defaults, priorities) in the codebase.
24. **Describe the resilience framework for LLM calls**: provider pool, circuit breakers, cost tracking, and fallback behavior.
25. **Walk through a typical LLM call end-to-end**, showing how the orchestrator picks a provider, calls it, handles errors, and falls back if needed.
26. **Identify how token usage and costs are tracked** and how budgets are enforced for different providers.
27. **Compare the LLM resilience design in this project** with what you typically see in common LLM frameworks (e.g., single-provider + simple retries).
28. **List the main advantages and disadvantages of this multi-provider resilience strategy**, including complexity and operational trade-offs.

---

## E. Graph (Memgraph) + NL→Cypher (29–35)

29. **Describe the graph data model** (nodes, relationships, properties) as implemented for Memgraph, and explain the main use cases it supports.
30. **Explain the full NL→Cypher pipeline**: from natural language question to generated Cypher to safety checks to execution and summarization.
31. **Describe the “test mode” for NL→Cypher**: how prompts are mapped to expected Cypher, and how this is wired into the code for deterministic tests.
32. **Detail the safety checks applied to Cypher queries** (e.g., preventing destructive operations, enforcing tenant boundaries) and where they live in the code.
33. **From the code, identify the main advantages of the graph integration** compared to a typical RAG-only approach.
34. **Identify possible risks or weaknesses of the NL→Cypher approach** (e.g., complexity, maintainability, test burden, potential escape routes).
35. **Compare this graph integration with what is typically seen in SOTA agentic or RAG frameworks**, and summarize where this project is stronger or weaker.

---

## F. Agents, tools, jobs & background framework (36–41)

36. **Explain the internal structure of an “agent run”**: how runs, sessions, steps, TODOs, tool calls, and metrics are represented and persisted.
37. **Describe the MCP tool ecosystem**: which tool families exist (graph, cache, data, security, admin, utils), how they are defined, and how they are invoked.
38. **Explain how the jobs framework works** (job model, job store, event store, idempotency, status transitions, SSE events) using code references.
39. **Describe the worker architecture**: how workers dequeue jobs, interact with Postgres/Redis, handle cancellations, and manage heartbeats/shutdown.
40. **Explain the background/scheduler framework**: what periodic tasks exist (health checks, backups, cleanups) and how they are configured.
41. **From an operational viewpoint, list the main strengths and weaknesses of the way agents, jobs, and background tasks are designed.**

---

## G. Observability, testing & maintainability (42–46)

42. **Describe the observability stack**: which metrics are exposed, what tracing instrumentation exists, and how logging is structured.
43. **Explain how health checks are implemented** (liveness, readiness, startup, component health) and how they relate to infrastructure readiness.
44. **Summarize the testing strategy**: unit, integration, e2e, security, performance; highlight how Postgres/Redis/Memgraph are handled in tests.
45. **Evaluate maintainability and extensibility**: how easy is it (from the code) to add a new tool, LLM provider, graph domain, or endpoint?
46. **Identify any technical debt or design smells** visible in the current code: where complexity is high, abstractions leaky, or documentation lacking.

---

## H. UIs, UX & developer experience (47–50)

47. **Describe the Agent Chat UI architecture** (Next.js) and how it interacts with the backend (API endpoints, polling patterns, model selection).
48. **Describe the Control Panel UI architecture** (Streamlit) and how it uses the API to provide dashboards, jobs view, tool exploration, and graph/NL→Cypher testing.
49. **From a UX and developer-experience standpoint, list the key advantages and limitations** of having both a Next.js chat UI and a Streamlit control panel.
50. **Considering all the above code-level analysis, provide a consolidated list of the project’s main advantages and disadvantages**, and **compare them explicitly with current state-of-the-art agentic / orchestration systems** (e.g., LangChain, LlamaIndex, Semantic Kernel, OpenAI Assistants, AutoGen, crewAI), highlighting where this project is ahead, on par, or behind.