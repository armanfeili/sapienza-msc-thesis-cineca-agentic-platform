import pytest

from src.services.orchestrator import Orchestrator, OrchestrationContext, OrchestrationResult


@pytest.mark.asyncio
async def test_simple_memgraph_todo_propagates_principal_context():
    captured_payloads: dict[str, dict] = {}

    async def fake_generate(payload=None, **kwargs):
        captured_payloads["graph.generate_cypher"] = payload or {}
        return {"cypher": "MATCH (b:Blast) RETURN b", "params": {}}

    async def fake_query(payload=None, **kwargs):
        captured_payloads["graph.query"] = payload or {}
        return {"rows": [{"name": "Example"}]}

    orch = Orchestrator(
        tools={
            "graph.generate_cypher": fake_generate,
            "graph.query": fake_query,
        }
    )

    ctx = OrchestrationContext(
        goal="List :Blast nodes with a limit",
        user_id="user-123",
        session_id="session-abc",
        tenant_id="tenant-xyz",
        principal={
            "id": "auth0|user-123",
            "sub": "auth0|user-123",
            "permissions": ["tools:memgraph"],
            "tenant_id": "tenant-xyz",
        },
        vars={
            "memgraph_prompt_id": "prompt-1",
            "memgraph_prompt_expected_pattern": "(n:Blast)",
            "memgraph_prompt_expected_contains": ["limit"],
        },
    )

    todo = {"task": "Generate Cypher", "status": "pending"}
    result = OrchestrationResult(goal=ctx.goal)

    handled = await orch._handle_simple_memgraph_todo(
        todo_idx=0,
        todo=todo,
        goal=ctx.goal,
        ctx=ctx,
        result=result,
    )

    assert handled, "Simple Memgraph path should complete successfully"
    assert captured_payloads["graph.generate_cypher"]["principal"] in (
        ctx.principal,
        ctx.principal.get("id"),
        ctx.principal.get("sub"),
    )
    assert captured_payloads["graph.generate_cypher"]["tenant"] == ctx.tenant_id
    assert captured_payloads["graph.query"]["principal"] in (
        ctx.principal,
        ctx.principal.get("id"),
        ctx.principal.get("sub"),
    )
    assert captured_payloads["graph.query"]["tenant"] == ctx.tenant_id
    assert captured_payloads["graph.query"]["cypher"] == captured_payloads["graph.query"]["query"]


def test_simple_memgraph_builder_handles_output_sampling():
    orch = Orchestrator(tools={})

    query_info = orch._build_simple_memgraph_query(
        base_cypher=None,
        base_params=None,
        label="Blast",
        alias="b",
        goal="Sample 5 :Blast → :File|:BlastDb|:BlastedSeq via :OUTPUT edges.",
        limit_hint=5,
        expected_contains=["LIMIT"],
        expected_pattern="MATCH (b:Blast)-[:OUTPUT]",
    )

    assert query_info is not None
    assert "-[r:OUTPUT]->" in query_info["query"]
    assert "RETURN b, target" in query_info["query"]
    assert query_info["params"]["limit"] == 5


def test_simple_memgraph_builder_relationship_types():
    orch = Orchestrator(tools={})

    query_info = orch._build_simple_memgraph_query(
        base_cypher=None,
        base_params=None,
        label="Blast",
        alias="b",
        goal="What distinct relationship types exist from :Blast?",
        limit_hint=10,
        expected_contains=[],
        expected_pattern="MATCH (b:Blast)-[:OUTPUT]",
    )

    assert query_info is not None
    assert "DISTINCT type" in query_info["query"]
    assert "-[r:OUTPUT]->" in query_info["query"]
    assert query_info["params"]["limit"] == 10


def test_should_force_simple_mode_for_relationship_type_prompt():
    orch = Orchestrator(tools={})

    enabled, reason = orch._should_force_memgraph_simple_mode(
        goal="What distinct relationship types exist from :Blast?",
        todo_mode_hint="optional",
        category_hint="read_only",
        params={"memgraph_prompt_id": "p04"},
    )

    assert enabled is True
    assert reason == "memgraph_hint:relationship_types"


def test_should_use_simple_mode_from_env(monkeypatch):
    monkeypatch.setenv("MEMGRAPH_NL_SIMPLE_MODE", "true")
    orch = Orchestrator(tools={})

    enable, reason, override = orch._should_use_simple_memgraph_mode(
        goal="Show :Blast nodes",
        params={"category": "read_only", "todo_mode": "optional"},
        force_llm_for_memgraph_tests=False,
    )

    assert enable is True
    assert reason == "env_MEMGRAPH_NL_SIMPLE_MODE"
    assert override is None


def test_simple_mode_can_be_overridden_by_force_llm(monkeypatch):
    monkeypatch.delenv("MEMGRAPH_NL_SIMPLE_MODE", raising=False)
    orch = Orchestrator(tools={})

    enable, reason, override = orch._should_use_simple_memgraph_mode(
        goal="Show :Blast nodes",
        params={"category": "read_only", "todo_mode": "none", "memgraph_force_llm": True},
        force_llm_for_memgraph_tests=False,
    )

    assert enable is False
    assert override == "memgraph_force_llm"


@pytest.mark.asyncio
async def test_handle_simple_memgraph_todo_executes_generate_and_query():
    calls = []

    async def fake_generate(payload=None, **kwargs):
        calls.append("generate")
        return {"cypher": "MATCH (n:Movie) RETURN n", "params": {}}

    async def fake_query(payload=None, **kwargs):
        calls.append("query")
        return {"ok": True, "rows": [{"name": "Inception"}]}

    orch = Orchestrator(
        tools={
            "graph.generate_cypher": fake_generate,
            "graph.query": fake_query,
        }
    )
    ctx = OrchestrationContext(goal="List :Movie nodes", vars={"memgraph_prompt_id": "p1"})
    result = OrchestrationResult(goal=ctx.goal)

    todo = {"task": "Generate Cypher", "status": "pending", "meta": {"mode": "simple_memgraph"}}

    handled = await orch._handle_simple_memgraph_todo(
        todo_idx=0,
        todo=todo,
        goal=ctx.goal,
        ctx=ctx,
        result=result,
    )

    assert handled is True
    assert calls == ["generate", "query"]
    assert any(step.action == "graph.generate_cypher" for step in result.steps)
    assert any(step.action == "graph.query" for step in result.steps)
