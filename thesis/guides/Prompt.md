## Thesis writing rules (strict)

First, read the entire of current thesis file:

/Users/armanfeili/Arman/Sapienza Courses/4-semester/Thesis/ILP-Thesis-2025/Cineca-Agentic-Platform/thesis/main/sapthesis-doc.tex

Then, Complete the thesis file based on the following rules:

X = Related works and background
Section to write = X

1. Read all (every single one of them) attached files fully, end to end, as complete as possible. Especially full-doc.tex and README.md files. take your time. Treat them as the source of truth for this prompt. Don’t invent details.

2. Write ONLY section X (and its subsections). Respect its page budget. No extra chapters.

3. Every paragraph must support at least one:

   * Problem (what fails / why it matters)
   * Solution (what I built / how it works at a high level)
   * Results (what I measured / verified)

4. Assume the reader knows nothing. Define terms on first use (CAP, tenant, run, step, job, MCP, NL→Cypher, RBAC, SSE) and keep naming consistent.

5. Stay method-level, not code-level. Do NOT mention filenames, repo structure, endpoint catalogs, schema dumps, queue names, or library internals. Put inventories/tables only in Appendix if needed.

6. Minimal replicability only: hardware + OS + major dependency versions (top-level only).

7. Bullets are rare. Use only for short previews (≤ 6 items) or a small mapping table. Otherwise write prose.

8. No fluff, no marketing. Prefer measurable/defensible claims. If something isn’t in the sources, say “not specified / not evaluated” or omit it.

9. Traceability rule (when identifiers exist in the provided sources):

   * If the sources define requirements R1…Rk and/or evaluation questions EQ1…EQj, then any claim of a guarantee, property, or “the system ensures…” statement MUST be explicitly tied to Rk and/or EQj (inline, e.g., “(R3)”, “(EQ2)”, or “(R3, EQ2)”).
   * If no Rk/EQj identifiers exist in the sources, do not claim guarantees. Use conditional wording (“designed to…”, “intended to…”) or mark as not evaluated.

10. Output format for section X:

* 3–6 line intro (what this section adds)
* main text
* 3–6 line summary + pointer to next section

After you did all steps, compile the file to PDF with now issue.