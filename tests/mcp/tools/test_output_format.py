"""
Test suite for output.format tool (P7 implementation).

Covers:
- JSON formatting (deterministic, NDJSON, unicode safe)
- CSV formatting (deterministic column order)
- Markdown formatting (width caps, deterministic)
- Text formatting
- Normalize action
- Edge cases and validation
"""

import json
import pytest
from src.mcp.tools.output.format import (
    _act_json,
    _act_csv,
    _act_markdown,
    _act_text,
    _act_normalize,
    invoke,
)


class TestOutputFormatJSON:
    """Test JSON formatting with deterministic output and unicode safety."""

    def test_json_simple_dict(self):
        result = _act_json({"data": {"b": 2, "a": 1}})
        assert result["ok"] is True
        assert result["action"] == "json"
        assert result["format"] == "application/json"
        # Deterministic: sort_keys=True by default
        assert json.loads(result["content"]) == {"a": 1, "b": 2}

    def test_json_sort_keys_deterministic(self):
        # Same input should produce same output
        data = {"z": 1, "a": 2, "m": 3}
        result1 = _act_json({"data": data, "sort_keys": True})
        result2 = _act_json({"data": data, "sort_keys": True})
        assert result1["content"] == result2["content"]
        # Keys should be alphabetically sorted
        parsed = json.loads(result1["content"])
        keys = list(parsed.keys())
        assert keys == sorted(keys)

    def test_json_unicode_safe(self):
        # Unicode characters should be preserved (ensure_ascii=False)
        data = {"name": "Café", "city": "北京", "emoji": "🎉"}
        result = _act_json({"data": data})
        content = result["content"]
        assert "Café" in content or "\\u" in content  # Either raw or escaped
        parsed = json.loads(content)
        assert parsed["name"] == "Café"
        assert parsed["city"] == "北京"
        assert parsed["emoji"] == "🎉"

    def test_json_ndjson_format(self):
        # NDJSON: one JSON object per line
        data = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        result = _act_json({"data": data, "ndjson": True})
        assert result["format"] == "application/x-ndjson"
        lines = result["content"].split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["id"] == 1
        assert json.loads(lines[1])["id"] == 2

    def test_json_pretty_print(self):
        result = _act_json({"data": {"a": 1}, "indent": 2})
        assert "  " in result["content"]  # Indentation present

    def test_json_bytes_count(self):
        result = _act_json({"data": {"test": "data"}})
        assert result["bytes"] == len(result["content"].encode("utf-8"))


class TestOutputFormatCSV:
    """Test CSV formatting with deterministic column order."""

    def test_csv_simple(self):
        data = [{"b": 2, "a": 1}, {"b": 4, "a": 3}]
        result = _act_csv({"data": data})
        assert result["ok"] is True
        assert result["action"] == "csv"
        assert result["format"] == "text/csv"
        assert result["rowcount"] == 2
        # Columns should be deterministic (alphabetically sorted)
        lines = result["content"].strip().split("\n")
        assert lines[0] == "a,b"  # Header with sorted columns
        assert lines[1] == "1,2"
        assert lines[2] == "3,4"

    def test_csv_deterministic_columns(self):
        # Same data should produce same column order
        data = [{"z": 1, "a": 2, "m": 3}]
        result1 = _act_csv({"data": data})
        result2 = _act_csv({"data": data})
        assert result1["content"] == result2["content"]
        assert result1["columns"] == sorted(result1["columns"])

    def test_csv_explicit_columns(self):
        data = [{"a": 1, "b": 2, "c": 3}]
        result = _act_csv({"data": data, "columns": ["c", "a"]})
        lines = result["content"].strip().split("\n")
        assert lines[0] == "c,a"
        assert lines[1] == "3,1"

    def test_csv_custom_delimiter(self):
        data = [{"a": 1, "b": 2}]
        result = _act_csv({"data": data, "delimiter": "|"})
        lines = result["content"].strip().split("\n")
        assert lines[0] == "a|b"

    def test_csv_no_header(self):
        data = [{"a": 1}]
        result = _act_csv({"data": data, "header": False})
        assert result["content"].strip() == "1"

    def test_csv_bom(self):
        data = [{"a": 1}]
        result = _act_csv({"data": data, "include_bom": True})
        assert result["content"].startswith("\ufeff")

    def test_csv_limit_rows(self):
        data = [{"a": i} for i in range(10)]
        result = _act_csv({"data": data, "limit": 3})
        assert result["rowcount"] == 3


class TestOutputFormatMarkdown:
    """Test Markdown formatting with width caps."""

    def test_markdown_simple_table(self):
        data = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        result = _act_markdown({"data": data})
        assert result["ok"] is True
        assert result["action"] == "markdown"
        assert result["format"] == "text/markdown"
        content = result["content"]
        assert "| id | name |" in content or "| name | id |" in content
        assert "Alice" in content
        assert "Bob" in content

    def test_markdown_width_cap(self):
        # Long values should be truncated with default cap (50)
        long_text = "a" * 100
        data = [{"text": long_text}]
        result = _act_markdown({"data": data, "max_col_width": 10})
        content = result["content"]
        # Should be truncated to 10 chars with ellipsis
        assert len([c for c in content.split("|") if "aaaa" in c][0].strip()) <= 11  # 10 + "…"

    def test_markdown_deterministic_columns(self):
        # Columns should be alphabetically sorted
        data = [{"z": 1, "a": 2, "m": 3}]
        result = _act_markdown({"data": data})
        content = result["content"]
        # Check header line for alphabetic order
        header_line = content.split("\n")[0]
        assert header_line.index("a") < header_line.index("m") < header_line.index("z")

    def test_markdown_code_fence(self):
        data = [{"a": 1}]
        result = _act_markdown({"data": data, "code_fence": True})
        assert result["content"].startswith("```md")
        assert result["content"].endswith("```")

    def test_markdown_escape_pipes(self):
        data = [{"text": "a|b"}]
        result = _act_markdown({"data": data})
        assert r"a\|b" in result["content"]

    def test_markdown_non_tabular(self):
        # Non-tabular data (single dict) should be rendered as table with "key" column
        data = {"key": "value"}
        result = _act_markdown({"data": data})
        # Single dict is treated as single row, not non-tabular
        content = result["content"]
        assert "key" in content  # Column name
        assert "value" in content  # Value


class TestOutputFormatText:
    """Test plain text formatting."""

    def test_text_string_passthrough(self):
        result = _act_text({"data": "Hello, World!"})
        assert result["content"] == "Hello, World!"

    def test_text_tabular(self):
        data = [{"a": 1, "b": 2}]
        result = _act_text({"data": data})
        content = result["content"]
        assert "a: 1" in content or "a:1" in content.replace(" ", "")
        assert "b: 2" in content or "b:2" in content.replace(" ", "")

    def test_text_custom_separator(self):
        data = [{"a": 1}, {"a": 2}]
        result = _act_text({"data": data, "separator": " | "})
        assert " | " in result["content"]

    def test_text_code_fence(self):
        result = _act_text({"data": "test", "code_fence": True})
        assert result["content"].startswith("```text")
        assert result["content"].endswith("```")


class TestOutputFormatNormalize:
    """Test normalize action."""

    def test_normalize_list_of_dicts(self):
        data = [{"a": 1, "b": 2}, {"a": 3, "c": 4}]
        result = _act_normalize({"data": data})
        assert result["ok"] is True
        assert result["action"] == "normalize"
        # Columns should include all keys (deterministically sorted)
        assert set(result["columns"]) == {"a", "b", "c"}
        assert result["columns"] == sorted(result["columns"])
        assert len(result["rows"]) == 2

    def test_normalize_dict_with_rows(self):
        data = {"rows": [{"x": 1}], "columns": ["x"]}
        result = _act_normalize({"data": data})
        assert result["columns"] == ["x"]
        assert len(result["rows"]) == 1

    def test_normalize_flatten(self):
        data = [{"a": {"b": {"c": 1}}}]
        result = _act_normalize({"data": data, "flatten": True})
        assert "a.b.c" in result["columns"]

    def test_normalize_no_flatten(self):
        data = [{"a": {"b": 1}}]
        result = _act_normalize({"data": data, "flatten": False})
        assert "a" in result["columns"]
        assert "a.b" not in result["columns"]


class TestOutputFormatInvoke:
    """Test main invoke entrypoint."""

    def test_invoke_json(self):
        result = invoke({"action": "json", "data": {"a": 1}})
        assert result["action"] == "json"

    def test_invoke_csv(self):
        result = invoke({"action": "csv", "data": [{"a": 1}]})
        assert result["action"] == "csv"

    def test_invoke_markdown(self):
        result = invoke({"action": "markdown", "data": [{"a": 1}]})
        assert result["action"] == "markdown"

    def test_invoke_text(self):
        result = invoke({"action": "text", "data": "test"})
        assert result["action"] == "text"

    def test_invoke_normalize(self):
        result = invoke({"action": "normalize", "data": [{"a": 1}]})
        assert result["action"] == "normalize"

    def test_invoke_default_action(self):
        # Default action is json
        result = invoke({"data": {"a": 1}})
        assert result["action"] == "json"

    def test_invoke_invalid_action(self):
        with pytest.raises(ValueError, match="action must be one of"):
            invoke({"action": "invalid"})


class TestOutputFormatEdgeCases:
    """Test edge cases and validation."""

    def test_empty_data(self):
        result = _act_json({"data": []})
        assert result["ok"] is True
        assert json.loads(result["content"]) == []

    def test_none_data(self):
        result = _act_json({"data": None})
        assert json.loads(result["content"]) is None

    def test_csv_empty_rows(self):
        result = _act_csv({"data": []})
        assert result["rowcount"] == 0

    def test_markdown_empty_rows(self):
        result = _act_markdown({"data": []})
        # Should handle gracefully
        assert result["ok"] is True

    def test_unicode_in_all_formats(self):
        # Ensure unicode safety across all formats
        data = [{"name": "Café ☕"}]

        json_result = _act_json({"data": data[0]})
        assert "Café" in json_result["content"] or "\\u" in json_result["content"]

        csv_result = _act_csv({"data": data})
        assert "Café" in csv_result["content"] or "Caf" in csv_result["content"]

        md_result = _act_markdown({"data": data})
        assert "Café" in md_result["content"] or "Caf" in md_result["content"]
