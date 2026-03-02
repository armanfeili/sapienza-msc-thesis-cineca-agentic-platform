### 1. Prompt p19 (index 9) JSON block

1. **Run status vs TODO status and error**

   * Top-level `"status": "succeeded"`.
   * The only TODO in `steps[1].output.todos[0]` has `"status": "failed"`.
   * `steps[2].output.error` says `"TODO #1 planning exceeded 300s timeout"`.
   * Top-level `"output": null`, `"cypher_queries": []`, `"tools": []`.

   These elements together describe a failed planning attempt, but the run is recorded as `"succeeded"`.

2. **LLM metrics vs timeout error**

   * Second LLM entry in `metrics.llm`:

     ```json
     {
       "model": "phi3:mini",
       "latency_ms": 300011,
       "success": true,
       "purpose": null,
       "error": null
     }
     ```

   * At the same time, there is a step with `"error": "TODO #1 planning exceeded 300s timeout"`.

   The LLM metrics mark this long call as `success: true` with `error: null`, while a timeout error is recorded at the step level.

3. **model_warmup_ms vs actual use**

   * `"model_warmup_ms": 226549` matches the first LLM call’s latency and that call has `purpose: "todo_list_creation"` (a real task), not a separate warmup-only ping.
   * So the warmup metric is being attributed to an LLM call that is simultaneously counted as productive work.

4. **Top-level warnings/errors vs step-level error**

   * `"warnings": []` and `"errors": null` at the top level.
   * Step `"todo-0-error"` contains a planning timeout error message.

   The error exists only inside a step’s output, while the top-level `warnings`/`errors` are empty.

---

### 2. PROMPT 1 / p02 (“How many :Blast nodes are there?”)

5. **TODOs header vs actual TODO content**

   * The “TODOs (0)” section is printed, but `Step 4` clearly contains one TODO in `output.todos[0]` with `status: "completed"`.

   So the explicit `TODOs (0)` label is inconsistent with the presence of one TODO in the step output.

6. **Output section vs actual query result**

   * The “OUTPUT” section says `(No output)` and the summary line says `Output=NoneType, result: b_count=39`.
   * The actual answer `b_count = 39` exists only inside `Step 6.output.rows[0].b_count`.

   There is a discrepancy between “No output” and the existence of a concrete result in the steps.

7. **LLM configuration smoke test provider inconsistency**

   * Orchestrator configuration section lists:

     ```text
     Provider Name:         ollama-local
     Base URL:              http://ollama:11434/v1
     ```

   * The later “LLM CONFIGURATION SMOKE TEST” block reports:

     ```text
     Provider: unknown
     ```

   That is an inconsistent provider identity for the same instance/model.

---

### 3. PROMPT 2 / p03 (“Show 10 random :Blast nodes with a couple of properties.”)

8. **TODOs header vs TODO content**

   * Again: “TODOs (0)” section appears even though `Step 4.output.todos` contains one TODO with `status: "completed"`.

9. **Output section vs actual rows**

   * “OUTPUT” shows `(No output)`, whereas `Step 6.output.rows` contains 10 rows with full node payloads.

10. **LLM configuration smoke test provider inconsistency**

    * Same pattern as p02: orchestration config shows `Provider Name: ollama-local`, but the smoke test summary block says `Provider: unknown`.

---

### 4. PROMPT 4 / p06 (“Sample 5 :Blast → :File|:BlastDb|:BlastedSeq via :OUTPUT edges.”)

11. **Cypher mismatch and error message**

    * `Step 3.input.query`:

      ```cypher
      MATCH (b:Blast)-[r:OUTPUT]->(target:File|BlastDb|BlastedSeq)
      RETURN b, target LIMIT $limit
      ```

    * `Step 5.output.cypher`:

      ```cypher
      MATCH (n:`Blast`) RETURN n LIMIT $limit
      ```

    * `Step 6.output.message`:

      ```text
      Internal error: Memgraph query failed: line 1:41 mismatched input '|' expecting {')', '{', '$'}
      ```

    The error message clearly refers to the `|` in `File|BlastDb|BlastedSeq` (Step 3), while Step 5’s cypher has no `|`. So the cypher stored in the `graph.generate_cypher` output is not aligned with the query that actually failed.

12. **Step result vs run final status**

    * `Step 6.output.ok` is `false` with error code `E_INTERNAL`.
    * Overall “Status” for this prompt is reported as `succeeded`.
    * The run summary row says: `What was the final status/result of the prompt? | succeeded (Output=NoneType)`.

    There is a conflict between a failing final tool step and an overall `succeeded` status.

13. **Tool metrics vs step-level error**

    * In the metrics:

      ```json
      "tools": [
        {
          "name": "graph.generate_cypher",
          "latency_ms": 7,
          "success": true
        },
        {
          "name": "graph.query",
          "latency_ms": 40,
          "success": true
        }
      ],
      "tool_calls": 2,
      "tool_errors": 0
      ```

    * But `Step 6.output.ok` is `false` with an internal error.

    Tool-level metrics mark `graph.query` as `success: true` and `tool_errors: 0` despite the reported Memgraph query failure.

14. **TODOs header vs actual TODO**

    * As with p02/p03, the “TODOs (0)” section is printed, while `Step 4.output.todos` contains a TODO with `status: "completed"`.

15. **Output section vs error state**

    * “OUTPUT” shows `(No output)`.
    * The only “result” for this prompt is an internal error message in `Step 6.output.message`.

---

### 5. LLM call accounting

16. **Smoke test provider inconsistency across summaries**

    * In all three “LLM CONFIGURATION SMOKE TEST” sections, the provider is shown as `unknown` even though each prompt’s orchestrator configuration block specifies `Provider Name: ollama-local`.

17. **Health-check vs per-run metrics separation**

    * For each prompt, the per-run metrics show:

      ```json
      "llm": [],
      "total_llm_calls": 0,
      "llm_call_count": 0
      ```

    * Yet each “LLM CALL BREAKDOWN” section states:

      ```text
      Health-check (smoke test): 1
      Agent run:                0
      ```
