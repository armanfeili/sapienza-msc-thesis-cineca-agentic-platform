import pytest

from db.memgraph_domain import memgraph_client


def _memgraph_available():
    try:
        mg = memgraph_client.get_memgraph()
        # run a harmless query
        list(mg.execute_and_fetch("RETURN 1"))
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _memgraph_available(), reason="Memgraph not available")
def test_create_and_populate_smoke():
    from db.populate import create_from_original_and_populate

    # Run with a small synthetic workload
    create_from_original_and_populate("db/original-dataset", wipe=True, users=10)
    mg = memgraph_client.get_memgraph()
    res = list(mg.execute_and_fetch("MATCH (n) RETURN count(n) AS c"))
    assert res and int(res[0]["c"]) > 0
