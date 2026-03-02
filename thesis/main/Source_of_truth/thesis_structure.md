# Final thesis structure (consolidated, professor-proof) — with page budget (target: **≤ 80 pages**)

---

## Front matter (**4–6 pages total**)

* Title page (author, supervisor(s), affiliation, date) (**1**)
* (Optional) Acknowledgements (**0–1**)
* Abstract + Keywords (**1**)
* Table of contents (**1–2**)
* (Optional, if template supports) List of Figures (**0–1**)
* (Optional, if template supports) List of Tables (**0–1**)
* List of acronyms / glossary *(reader-facing; define once: Tenant, Principal, Run, Step, Job, MCP, NL→Cypher, RBAC, SSE, etc.)* (**1–2**)

---

## 1. Introduction (**7–9 pages**)

**Goal:** Make “problem → solution → results” unmistakable, early, with minimal assumptions.

1.1 Context and motivation (“production gap”) (**1–2**)
1.2 Problem statement (what fails with naïve agent demos / chatbots in enterprise settings) (**1–2**)
1.3 Objectives and scope (explicit non-goals included) (**1**)
1.4 Proposed approach (1–2 paragraphs: what you built and why) (**1**)
1.5 Contributions (bullet list; each testable/measurable) (**0.5–1**)
1.6 Results preview (≤ 1 page: what you evaluated + 3–6 headline outcomes) (**1**)
1.7 Thesis roadmap (chapter map in plain language) (**0.5–1**)

---

## 2. Related works and background (**9–12 pages**)

**Goal:** Only the background needed to justify your design; end with the gap you address.

2.1 Agentic systems and tool-use (only what you need for framing) (**2–3**)
2.2 Orchestration/workflow engines vs agent frameworks (durability, infra scope, “library-only” limits) (**2–3**)
2.3 Tool ecosystems and governance (controlled extensibility; why registries matter) (**1–2**)
2.4 Natural-language interfaces to graphs (why NL→Cypher needs safety and isolation) (**2–3**)
2.5 Positioning and gap analysis (short, decisive synthesis: what existing systems don’t provide together) (**1–2**)

---

## 3. Proposed solution: The CINECA Agentic Platform (CAP) (**24–30 pages**)

**Goal:** One coherent “method/system” chapter at the right abstraction level (replicable, not code-trivia).

### 3.1 Requirements and design goals (**3–4 pages**)

* Stakeholders and core use cases (only those that drive the architecture)
* Functional + non-functional requirements (safety, multi-tenancy, durability, observability)
* **Stable identifiers:** label requirements as **R1, R2, …**
* **Traceability mini-table:** **Rk → EQj → §4.x / §5.x** (where it’s tested and where results appear)

### 3.2 System overview and core concepts (**3–4 pages**)

* One high-level architecture diagram + narrative (three-layer architecture + cross-cutting concerns)
* Core concepts (define once, reuse): tenant, principal, run, step, job, tool, audit, etc.

### 3.3 Execution model: dual workflows (core story) (**4–5 pages**)

* Workflow A: Agent Runs (synchronous path, lifecycle, guarantees, when used)
* Workflow B: Jobs (durable async path, progress streaming, cancellation, recovery)
* Why two workflows exist + trade-offs (latency vs durability, UX vs operability)

### 3.3.1 End-to-end request walkthrough (one representative scenario) (**2–3 pages**)

* User request → routing → run/steps **or** job
* Tool calls and/or NL→Cypher gates
* Persistence + audit trail
* Observability outputs (metrics/logs/traces)
  *(Single guided story to prevent reader confusion.)*

### 3.4 Orchestration engine (**2–3 pages**)

* Intent/routing at conceptual level (why routing exists)
* Plan → execute steps → persist trace (what is guaranteed and persisted conceptually)

### 3.5 MCP tool ecosystem (controlled action + governance) (**2–3 pages**)

* Registry + schema validation + authorization + auditing (conceptual)
* Tool categories overview (no full enumeration here; move complete list to Appendix)

### 3.6 NL→Cypher subsystem (graph mode) (**3–4 pages**)

* Pipeline stages and what each achieves (method-level)
* Safety validation rationale (read-only enforcement, tenant boundaries, complexity/timeout guards)

### 3.7 Data and state (only what’s needed to understand behavior) (**2–3 pages**)

* Control plane vs data plane rationale
* What is stored where, conceptually (e.g., durability vs caching vs graph facts)
* **Boundary rule:** no schema dumps, queue names, endpoint tables, or file-level narration here (those go to Appendices)

### 3.8 Security, multi-tenancy, and governance (first-class constraints) (**3–4 pages**)

* Identity/auth, RBAC/scopes, tenant isolation, audit trail (high-level)
* Threat model summary (assumptions, assets, attacker model; what CAP defends against vs doesn’t)

### 3.9 Observability and operational readiness (**2–3 pages**)

* What is measured and why (metrics/logging/tracing as requirements, not “nice-to-have”)

### 3.10 Design trade-offs summary (**1–2 pages**)

* Safety vs flexibility; latency vs durability; extensibility vs governance (1–2 pages, synthesis)

---

## 4. Tests (Evaluation Methodology) (**9–12 pages**)

**Goal:** Only “how you evaluated” (methodology), clearly mapped to requirements.

### 4.1 Experimental setup and reproducibility (**3–4 pages**)

* Hardware/OS (only what matters)
* Major versions (only key dependencies)
* Workloads/scenarios definition
* Reproducibility contract: what is needed to rerun; what cannot be reproduced (if any)
* Workloads/prompts/datasets used (and selection rationale)
* **Rigor commitment:** number of runs, warm-up procedure, reporting percentiles (p50/p95/p99) and variance/CI where applicable

### 4.2 Evaluation questions (mapped to §3.1 requirements) (**1–2 pages**)

* **Stable identifiers:** label evaluation questions as **EQ1, EQ2, …**
* Explicit mapping back to the traceability table (**Rk → EQj → §4.x / §5.x**)

### 4.3 Metrics (**1–2 pages**)

* Precise definitions; what each metric demonstrates

### 4.4 Test protocols (**2–3 pages**)

* Functional validation
* Security validation (explicitly tied to threat model in §3.8)
* Reliability/degradation tests (restarts, backlog, provider failures)
* Performance/load tests (representative workloads)

### 4.5 Baselines and comparison design (**1–2 pages**)

* What you compare against and why it’s fair

---

## 5. Results and discussion (**14–18 pages**)

**Goal:** Evidence first, interpretation second, grouped cleanly.

5.1 Functional results (**3–4**)
5.2 Performance results (include variability/percentiles) (**3–5**)
5.3 Reliability results (durability, cancellation, recovery) (**2–3**)
5.4 Security results (what was verified; edge cases) (**2–3**)
5.5 Comparative results vs baselines (**2–3**)
5.6 Limitations and threats to validity (grouped, concrete) (**2**)

---

## 6. Conclusions (**3–4 pages**)

* Tight recap: problem → CAP → key results (**2–3**)
* Final takeaways (3–5 clear statements) (**1**)

---

## 7. Future work (**2–3 pages**)

* Concrete next steps (evaluation depth, new tools, stronger benchmarks, deployment hardening, broader providers/tenancy) (**2–3**)

---

## Appendices (single chapter) (**0–8 pages**)

**Goal:** Reference/inventory material only (keep main narrative method-level) and **avoid duplication**.

* A. Full tool inventory (complete list; schemas summary if useful) (**0–3**)
* B. API catalog / endpoint tables (only if included) (**0–2**)
* C. Extra diagrams (full workflows, state machines) (**0–2**)
* D. Extended tables/plots (**extra results artifacts only**: additional metrics, long tables, overflow plots) (**0–2**)
* E. Reproducibility notes (**how to rerun only**: configs/templates/how to run, as reference) (**0–2**)

*(You will not include all of these at max size; the total appendix budget stays within 0–8.)*

---

## Bibliography (**2–4 pages**)

---

### Total target (with this budget)

Typically lands around **76–80 pages** if you keep appendices tight and don’t expand Chapter 3 into implementation details.
