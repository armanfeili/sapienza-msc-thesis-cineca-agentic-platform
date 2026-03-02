"""A tiny pytest fixture that provides a mock Memgraph client for CI.

Use by importing in tests and monkeypatching db.memgraph_client.get_memgraph
or by including the fixture in test modules.
"""
from typing import Any, Dict, List


class DummyResult:
    def __init__(self, rows: List[Dict[str, Any]]):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


class DummyMemgraph:
    def __init__(self, node_count: int = 0):
        self._node_count = node_count

    def execute_and_fetch(self, query: str):
        # support simple MATCH (n) RETURN count(n) AS c
        if "count(n)" in query:
            return [{"c": self._node_count}]
        return []


def make_dummy_memgraph(node_count: int = 0) -> DummyMemgraph:
    return DummyMemgraph(node_count=node_count)


# pytest fixture for tests to import
def get_mock_memgraph(node_count: int = 0):
    return make_dummy_memgraph(node_count)
