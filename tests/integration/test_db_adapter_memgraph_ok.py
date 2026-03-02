import pytest

from tests.fixtures.fake_memgraph import FakeMemgraphAdapter


@pytest.mark.asyncio
async def test_fake_memgraph_adapter_behaves_like_real_ok():
    """
    Sanity test that our Memgraph adapter contract is satisfied in the 'OK' case
    using the in-memory FakeMemgraphAdapter. This exercises the core methods the
    real adapter must expose: ping, execute, execute_and_fetch, bulk_execute, info.
    """
    db = FakeMemgraphAdapter()

    # Should report alive
    assert db.ping() is True

    # Initially empty
    info0 = db.info()
    assert info0.get("nodes") == 0
    assert info0.get("relationships") == 0

    # Create two nodes via bulk MERGE statements (mirrors ETL usage)
    stmts = [
        ("MERGE (n:`User` {orig_id:$orig_id}) SET n += $props", {"orig_id": "u1", "props": {"name": "Alice"}}),
        ("MERGE (n:`User` {orig_id:$orig_id}) SET n += $props", {"orig_id": "u2", "props": {"name": "Bob"}}),
    ]
    db.bulk_execute(stmts)

    # Create a relationship
    q_rel = "MATCH (a {orig_id:$a}), (b {orig_id:$b}) " "MERGE (a)-[rel:`KNOWS`]->(b) SET rel += $props"
    db.execute(q_rel, {"a": "u1", "b": "u2", "props": {"since": 2024}})

    # Verify counts through Cypher-like queries used by ETL
    nodes = list(db.execute_and_fetch("MATCH (n) RETURN labels(n) AS labels, properties(n) AS properties"))
    assert len(nodes) == 2
    labels_sets = [tuple(x["labels"]) for x in nodes]
    assert ("User",) in labels_sets

    rels = list(
        db.execute_and_fetch(
            "MATCH (a)-[r]->(b) "
            "RETURN type(r) AS type, a.orig_id AS start, b.orig_id AS end, properties(r) AS properties"
        )
    )
    assert len(rels) == 1
    assert rels[0]["type"] == "KNOWS"
    assert {rels[0]["start"], rels[0]["end"]} == {"u1", "u2"}

    # info() should reflect current state
    info1 = db.info()
    assert info1.get("nodes") == 2
    assert info1.get("relationships") == 1

    # Update a node and ensure properties merge
    db.execute("MERGE (n:`User` {orig_id:$orig_id}) SET n += $props", {"orig_id": "u1", "props": {"city": "Paris"}})
    props_u1 = next(
        x["properties"] for x in db.execute_and_fetch("MATCH (n {orig_id:'u1'}) RETURN properties(n) AS properties")
    )
    assert props_u1["name"] == "Alice" and props_u1["city"] == "Paris"
