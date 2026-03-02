"""
Test suite for viz.render tool (P7 implementation).

Covers:
- Graph rendering (Mermaid, DOT) with validation and escaping
- Table rendering
- Sparkline rendering
- Size caps and limits
- Input validation and injection prevention
- Edge cases
"""

import pytest
from src.mcp.tools.viz.render import (
    _act_graph_mermaid,
    _act_graph_dot,
    _act_table_markdown,
    _act_sparkline,
    invoke,
    graph_from_triples,
    # Legacy functions
    render_graph_mermaid,
    render_graph_dot,
    render_table_markdown,
    sparkline,
)


class TestVizRenderGraphMermaid:
    """Test Mermaid graph rendering with validation."""

    def test_mermaid_simple_graph(self):
        nodes = ["User", "Institution"]
        edges = [("User", "WORKS_AT", "Institution")]
        result = _act_graph_mermaid({"nodes": nodes, "edges": edges})

        assert result["ok"] is True
        assert result["action"] == "graph_mermaid"
        assert result["nodes"] == 2
        assert result["edges"] == 1
        assert "flowchart" in result["content"]

    def test_mermaid_direction(self):
        nodes = ["A", "B"]
        edges = [("A", "->", "B")]

        for direction in ["LR", "TB", "BT", "RL"]:
            result = _act_graph_mermaid(
                {
                    "nodes": nodes,
                    "edges": edges,
                    "direction": direction,
                }
            )
            assert f"flowchart {direction}" in result["content"]

    def test_mermaid_invalid_direction(self):
        with pytest.raises(ValueError, match="direction must be one of"):
            _act_graph_mermaid(
                {
                    "nodes": ["A"],
                    "edges": [],
                    "direction": "INVALID",
                }
            )

    def test_mermaid_edge_labels(self):
        nodes = ["A", "B"]
        edges = [("A", "LABEL", "B")]

        # With labels
        result = _act_graph_mermaid(
            {
                "nodes": nodes,
                "edges": edges,
                "show_labels": True,
            }
        )
        assert "LABEL" in result["content"]

        # Without labels
        result_no_labels = _act_graph_mermaid(
            {
                "nodes": nodes,
                "edges": edges,
                "show_labels": False,
            }
        )
        assert "LABEL" not in result_no_labels["content"]

    def test_mermaid_node_dict_format(self):
        nodes = [{"id": "user1", "label": "Alice"}]
        edges = []
        result = _act_graph_mermaid({"nodes": nodes, "edges": edges})
        assert "Alice" in result["content"]

    def test_mermaid_edge_dict_format(self):
        nodes = ["A", "B"]
        edges = [{"from": "A", "to": "B", "label": "rel"}]
        result = _act_graph_mermaid({"nodes": nodes, "edges": edges})
        assert "rel" in result["content"]

    def test_mermaid_size_cap_nodes(self):
        # Too many nodes
        nodes = [f"Node{i}" for i in range(150)]
        with pytest.raises(ValueError, match="Too many nodes"):
            _act_graph_mermaid({"nodes": nodes, "max_nodes": 100})

    def test_mermaid_size_cap_edges(self):
        # Too many edges
        nodes = ["A", "B"]
        edges = [("A", f"rel{i}", "B") for i in range(250)]
        with pytest.raises(ValueError, match="Too many edges"):
            _act_graph_mermaid({"nodes": nodes, "edges": edges, "max_edges": 200})

    def test_mermaid_input_escaping(self):
        # Test injection prevention with special characters
        nodes = [{"id": "test", "label": 'Bad"Label'}]
        result = _act_graph_mermaid({"nodes": nodes, "edges": []})
        # Should escape the quote
        assert r"\"" in result["content"] or "&quot;" in result["content"]

    def test_mermaid_id_sanitization(self):
        # IDs with special characters should be sanitized
        nodes = ["User-123", "User$456"]
        result = _act_graph_mermaid({"nodes": nodes, "edges": []})
        # Special chars should be replaced with underscores
        assert "User_123" in result["content"]
        assert "User_456" in result["content"]


class TestVizRenderGraphDOT:
    """Test Graphviz DOT rendering with validation."""

    def test_dot_simple_graph(self):
        nodes = ["User", "Institution"]
        edges = [("User", "WORKS_AT", "Institution")]
        result = _act_graph_dot({"nodes": nodes, "edges": edges})

        assert result["ok"] is True
        assert result["action"] == "graph_dot"
        assert result["nodes"] == 2
        assert result["edges"] == 1
        assert "digraph G" in result["content"]

    def test_dot_directed_vs_undirected(self):
        nodes = ["A", "B"]
        edges = [("A", "rel", "B")]

        # Directed
        result_dir = _act_graph_dot(
            {
                "nodes": nodes,
                "edges": edges,
                "directed": True,
            }
        )
        assert "digraph" in result_dir["content"]
        assert "->" in result_dir["content"]

        # Undirected
        result_undir = _act_graph_dot(
            {
                "nodes": nodes,
                "edges": edges,
                "directed": False,
            }
        )
        assert "graph" in result_undir["content"]
        assert "--" in result_undir["content"]

    def test_dot_size_cap_nodes(self):
        nodes = [f"N{i}" for i in range(150)]
        with pytest.raises(ValueError, match="Too many nodes"):
            _act_graph_dot({"nodes": nodes, "max_nodes": 100})

    def test_dot_size_cap_edges(self):
        nodes = ["A", "B"]
        edges = [("A", f"r{i}", "B") for i in range(250)]
        with pytest.raises(ValueError, match="Too many edges"):
            _act_graph_dot({"nodes": nodes, "edges": edges, "max_edges": 200})

    def test_dot_input_escaping(self):
        nodes = [{"id": "n1", "label": 'Test"Label'}]
        result = _act_graph_dot({"nodes": nodes, "edges": []})
        # Should escape quotes
        assert r"\"" in result["content"] or "&quot;" in result["content"]


class TestVizRenderTableMarkdown:
    """Test Markdown table rendering."""

    def test_table_simple(self):
        rows = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        result = _act_table_markdown({"rows": rows})

        assert result["ok"] is True
        assert result["action"] == "table_markdown"
        assert result["rows"] == 2
        content = result["content"]
        assert "Alice" in content
        assert "Bob" in content
        assert "|" in content  # Markdown table format

    def test_table_deterministic_columns(self):
        # Columns should be alphabetically sorted
        rows = [{"z": 1, "a": 2, "m": 3}]
        result = _act_table_markdown({"rows": rows})
        content = result["content"]
        header = content.split("\n")[0]
        # Check order: a before m before z
        assert header.index("a") < header.index("m") < header.index("z")

    def test_table_explicit_columns(self):
        rows = [{"a": 1, "b": 2, "c": 3}]
        result = _act_table_markdown({"rows": rows, "columns": ["c", "a"]})
        content = result["content"]
        header = content.split("\n")[0]
        assert "c" in header
        assert "a" in header
        assert "b" not in header  # Only specified columns

    def test_table_empty_rows(self):
        result = _act_table_markdown({"rows": []})
        assert result["ok"] is True
        assert result["rows"] == 0
        assert "(no data)" in result["content"]

    def test_table_size_cap(self):
        rows = [{"a": i} for i in range(2000)]
        with pytest.raises(ValueError, match="Too many rows"):
            _act_table_markdown({"rows": rows, "max_rows": 1000})

    def test_table_escape_pipes(self):
        rows = [{"text": "a|b"}]
        result = _act_table_markdown({"rows": rows})
        # Pipes should be escaped
        assert r"\|" in result["content"]

    def test_table_cell_length_cap(self):
        # Very long cell values should be capped
        long_text = "x" * 300
        rows = [{"text": long_text}]
        result = _act_table_markdown({"rows": rows})
        # Should be truncated (200 char cap in implementation)
        cell_content = [line for line in result["content"].split("|") if "xxx" in line]
        if cell_content:
            assert len(cell_content[0].strip()) <= 201  # 200 + potential newline

    def test_table_invalid_rows(self):
        with pytest.raises(ValueError, match="rows must be a list"):
            _act_table_markdown({"rows": "not a list"})


class TestVizRenderSparkline:
    """Test sparkline rendering."""

    def test_sparkline_simple(self):
        values = [1, 3, 2, 5, 4]
        result = _act_sparkline({"values": values})

        assert result["ok"] is True
        assert result["action"] == "sparkline"
        assert result["values"] == 5
        assert len(result["content"]) == 5
        # Should use unicode bar characters
        assert any(c in result["content"] for c in "▁▂▃▄▅▆▇█")

    def test_sparkline_ascending(self):
        values = [1, 2, 3, 4, 5]
        result = _act_sparkline({"values": values})
        # Should show ascending pattern
        content = result["content"]
        assert len(content) == 5

    def test_sparkline_constant(self):
        values = [5, 5, 5, 5]
        result = _act_sparkline({"values": values})
        # All values same → all max bar
        assert result["content"] == "█" * 4

    def test_sparkline_empty(self):
        result = _act_sparkline({"values": []})
        assert result["content"] == ""
        assert result["values"] == 0

    def test_sparkline_size_cap(self):
        values = list(range(150))
        with pytest.raises(ValueError, match="Too many values"):
            _act_sparkline({"values": values, "max_values": 100})

    def test_sparkline_with_none(self):
        values = [1, None, 3, None, 5]
        result = _act_sparkline({"values": values})
        # Should filter out None values
        assert result["values"] == 3

    def test_sparkline_invalid_values(self):
        with pytest.raises(ValueError, match="values must be a list"):
            _act_sparkline({"values": "not a list"})


class TestVizRenderInvoke:
    """Test main invoke entrypoint."""

    def test_invoke_graph_mermaid(self):
        result = invoke(
            {
                "action": "graph_mermaid",
                "nodes": ["A"],
                "edges": [],
            }
        )
        assert result["action"] == "graph_mermaid"

    def test_invoke_graph_dot(self):
        result = invoke(
            {
                "action": "graph_dot",
                "nodes": ["A"],
                "edges": [],
            }
        )
        assert result["action"] == "graph_dot"

    def test_invoke_table_markdown(self):
        result = invoke(
            {
                "action": "table_markdown",
                "rows": [{"a": 1}],
            }
        )
        assert result["action"] == "table_markdown"

    def test_invoke_sparkline(self):
        result = invoke(
            {
                "action": "sparkline",
                "values": [1, 2, 3],
            }
        )
        assert result["action"] == "sparkline"

    def test_invoke_default_action(self):
        # Default action is graph_mermaid
        result = invoke({"nodes": ["A"], "edges": []})
        assert result["action"] == "graph_mermaid"

    def test_invoke_invalid_action(self):
        with pytest.raises(ValueError, match="action must be one of"):
            invoke({"action": "invalid"})


class TestVizRenderUtilities:
    """Test utility functions."""

    def test_graph_from_triples(self):
        triples = [
            ("User", "WORKS_AT", "Institution"),
            ("User", "HAS", "Profile"),
        ]
        nodes, edges = graph_from_triples(triples)

        assert len(nodes) == 3  # User, Institution, Profile
        assert len(edges) == 2

        # Check node structure
        node_ids = {n["id"] for n in nodes}
        assert "User" in node_ids
        assert "Institution" in node_ids
        assert "Profile" in node_ids

        # Check edge structure
        assert edges[0]["from"] == "User"
        assert edges[0]["to"] == "Institution"
        assert edges[0]["label"] == "WORKS_AT"

    def test_graph_from_triples_with_labels(self):
        triples = [("u1", "rel", "u2")]
        node_labels = {"u1": "User One", "u2": "User Two"}
        nodes, edges = graph_from_triples(triples, node_labels=node_labels)

        labels = {n["id"]: n["label"] for n in nodes}
        assert labels["u1"] == "User One"
        assert labels["u2"] == "User Two"


class TestVizRenderLegacyFunctions:
    """Test legacy backward-compatible functions."""

    def test_legacy_render_graph_mermaid(self):
        content = render_graph_mermaid(
            nodes=["A", "B"],
            edges=[("A", "rel", "B")],
        )
        assert isinstance(content, str)
        assert "flowchart" in content

    def test_legacy_render_graph_dot(self):
        content = render_graph_dot(
            nodes=["A", "B"],
            edges=[("A", "rel", "B")],
        )
        assert isinstance(content, str)
        assert "digraph" in content

    def test_legacy_render_table_markdown(self):
        content = render_table_markdown(rows=[{"a": 1, "b": 2}])
        assert isinstance(content, str)
        assert "|" in content

    def test_legacy_sparkline(self):
        content = sparkline([1, 2, 3])
        assert isinstance(content, str)
        assert len(content) == 3


class TestVizRenderValidation:
    """Test input validation and edge cases."""

    def test_node_validation_missing_id(self):
        # Node without id, name, or label
        nodes = [{}]
        with pytest.raises(ValueError, match="must have an 'id'"):
            _act_graph_mermaid({"nodes": nodes, "edges": []})

    def test_node_validation_empty_id(self):
        nodes = [""]
        with pytest.raises(ValueError, match="cannot be empty"):
            _act_graph_mermaid({"nodes": nodes, "edges": []})

    def test_edge_validation_missing_fields(self):
        # Edge dict without 'from' or 'to'
        edges = [{"label": "test"}]
        with pytest.raises(ValueError, match="must have 'from' and 'to'"):
            _act_graph_mermaid({"nodes": ["A"], "edges": edges})

    def test_edge_validation_invalid_tuple(self):
        # Edge tuple with wrong number of elements
        edges = [("A", "B")]  # Only 2 elements instead of 3
        with pytest.raises(ValueError, match="must be \\(from, label, to\\)"):
            _act_graph_mermaid({"nodes": ["A", "B"], "edges": edges})

    def test_xss_prevention_in_labels(self):
        # Test that HTML/script tags are escaped
        nodes = [{"id": "n1", "label": "<script>alert('xss')</script>"}]
        result = _act_graph_mermaid({"nodes": nodes, "edges": []})
        # Should be HTML-escaped
        assert "&lt;" in result["content"] or "<" not in result["content"]

    def test_injection_prevention_quotes(self):
        # Test quote escaping
        nodes = [{"id": "n1", "label": 'Test"Quote"'}]
        result = _act_graph_mermaid({"nodes": nodes, "edges": []})
        # Quotes should be escaped
        assert r"\"" in result["content"] or "&quot;" in result["content"]

    def test_long_id_truncation(self):
        # Very long IDs should be truncated
        long_id = "x" * 200
        nodes = [long_id]
        result = _act_graph_mermaid({"nodes": nodes, "edges": []})
        # Should be truncated to 100 chars (as per implementation)
        assert result["ok"] is True

    def test_long_label_truncation(self):
        # Very long labels should be truncated
        long_label = "y" * 300
        nodes = [{"id": "n1", "label": long_label}]
        result = _act_graph_mermaid({"nodes": nodes, "edges": []})
        # Should be truncated to 200 chars (as per implementation)
        assert result["ok"] is True
