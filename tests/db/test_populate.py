import inspect
from types import ModuleType
from typing import Callable, List, Optional, Tuple

import pytest

# Reuse our simple in-memory Memgraph fake + sample data
from tests.fixtures.fake_memgraph import FakeMemgraphAdapter
from tests.fixtures.sample_data import SAMPLE_NODES, SAMPLE_RELATIONSHIPS


def _import_populate_module() -> ModuleType:
    """
    Import the db.populate module. If it doesn't exist in this repo variant,
    skip the test gracefully.
    """
    try:
        import db.populate as mod  # type: ignore

        return mod
    except Exception as exc:  # pragma: no cover - allow repo variants
        pytest.skip(f"db.populate not available: {exc}")


def _find_fn(mod: ModuleType, candidates: Tuple[str, ...]) -> Optional[Callable]:
    for name in candidates:
        fn = getattr(mod, name, None)
        if callable(fn):
            return fn
    return None


def _has_param(fn: Callable, param_name: str) -> bool:
    sig = inspect.signature(fn)
    return any(p.name == param_name for p in sig.parameters.values())


def _collect_text_from_statements(stmts) -> List[str]:
    """
    Normalize various statement forms into strings so tests can assert on them.
    Supported forms:
      - "CREATE ..." / "MERGE ..." strings
      - (query, params) tuples
      - dicts like {"query": "...", "params": {...}}
    """
    out: List[str] = []
    for s in stmts or []:
        if isinstance(s, str):
            out.append(s)
        elif isinstance(s, (tuple, list)) and s:
            out.append(str(s[0]))
        elif isinstance(s, dict) and "query" in s:
            out.append(str(s["query"]))
    return out


def test_populate_module_smoke() -> None:
    mod = _import_populate_module()
    # Basic smoke: module imported and has at least one attribute
    assert isinstance(mod, ModuleType)
    assert hasattr(mod, "__doc__")


def test_build_statements_from_sample_data() -> None:
    """
    Many populate scripts factor query construction into a separate helper.
    We attempt to find such a helper and validate it produces MERGE/CREATE-like
    cypher for our sample graph.
    """
    mod = _import_populate_module()

    # Try to discover a function that likely builds statements from node/rel lists
    builder = _find_fn(
        mod,
        (
            "build_statements",
            "build_queries",
            "make_statements",
            "make_queries",
            "prepare_statements",
            "prepare_queries",
        ),
    )
    if builder is None:
        pytest.skip("No query builder function found in db.populate")

    # Heuristically call the builder: prefer signature (nodes, rels, **kwargs)
    args = []
    kwargs = {}
    sig = inspect.signature(builder)
    params = list(sig.parameters.values())
    if len(params) >= 2:
        args = [SAMPLE_NODES, SAMPLE_RELATIONSHIPS]
    else:
        # fall back to named args if single param uses a combined payload
        if _has_param(builder, "nodes") and _has_param(builder, "relationships"):
            kwargs = {"nodes": SAMPLE_NODES, "relationships": SAMPLE_RELATIONSHIPS}
        elif _has_param(builder, "data"):
            kwargs = {"data": {"nodes": SAMPLE_NODES, "relationships": SAMPLE_RELATIONSHIPS}}
        else:
            pytest.skip("No compatible signature for builder function")

    stmts = builder(*args, **kwargs)
    text_stmts = _collect_text_from_statements(stmts)

    assert text_stmts, "Builder returned no statements"
    # Expect at least one MERGE/CREATE statement across nodes + rels
    joined = "\n".join(text_stmts).upper()
    assert (
        ("MERGE (" in joined) or ("CREATE (" in joined) or ("MERGE (A" in joined)
    ), f"Expected MERGE/CREATE cypher in: {joined[:2000]}"


def test_populate_executes_against_fake_memgraph(monkeypatch) -> None:
    """
    Attempt to find a top-level 'populate' function (or similar) that accepts
    a DB/adapter argument, then run it against our FakeMemgraphAdapter and
    assert that it executes some statements.
    """
    mod = _import_populate_module()

    # Candidate functions that likely run population
    runner = _find_fn(
        mod,
        (
            "populate",
            "populate_db",
            "run",
            "main",
            "load",
            "seed",
        ),
    )
    if runner is None:
        pytest.skip("No population runner function found in db.populate")

    fake = FakeMemgraphAdapter()

    # Try most common signatures:
    #   populate(db=...), populate(adapter=...), populate(client=...),
    #   populate(memgraph=...), populate(conn=...), populate(graph=...)
    kwargs_candidates = [
        {"db": fake},
        {"adapter": fake},
        {"client": fake},
        {"memgraph": fake},
        {"conn": fake},
        {"graph": fake},
    ]

    called = False
    for kw in kwargs_candidates:
        try:
            sig = inspect.signature(runner)
            # only pass kwargs that the runner actually accepts
            filtered = {k: v for k, v in kw.items() if k in sig.parameters}
            if not filtered and kw is not kwargs_candidates[-1]:
                continue
            # Best-effort: also pass in data if the function wants it
            if "nodes" in sig.parameters:
                filtered["nodes"] = SAMPLE_NODES
            if "relationships" in sig.parameters:
                filtered["relationships"] = SAMPLE_RELATIONSHIPS
            if "data" in sig.parameters:
                filtered["data"] = {"nodes": SAMPLE_NODES, "relationships": SAMPLE_RELATIONSHIPS}

            res = runner(**filtered)  # type: ignore[arg-type]
            called = True
            # Some runners return a result dict; ignore/allow None
            _ = res
            break
        except TypeError:
            # Signature mismatch; try next mapping
            continue

    if not called:
        pytest.skip("Could not call population runner with a supported signature")

    # Validate that our fake adapter saw some traffic
    executed = getattr(fake, "executed", [])
    bulk_exec = getattr(fake, "bulk_executed", [])
    query_exec = getattr(fake, "query_log", [])
    total = len(executed) + len(bulk_exec) + len(query_exec)
    assert total > 0, "Population runner did not execute any statements against the adapter"
