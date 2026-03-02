import os

import pytest

from src.memgraph.test_mode import get_prompt_hints, reset_prompt_cache


@pytest.fixture(autouse=True)
def clear_cache():
    reset_prompt_cache()
    yield
    reset_prompt_cache()


def test_get_prompt_hints_disabled(monkeypatch):
    monkeypatch.setenv("LLM_MEMGRAPH_NL_TEST_MODE", "false")
    assert get_prompt_hints("Any prompt") is None


def test_get_prompt_hints_matches_prompt(tmp_path, monkeypatch):
    prompts_file = tmp_path / "prompts.json"
    prompts_file.write_text(
        """
        [
            {"id": "p01", "text": "How many nodes?", "todo_mode": "none", "category": "read_only"}
        ]
        """.strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("LLM_MEMGRAPH_NL_TEST_MODE", "true")
    monkeypatch.setenv("LLM_MEMGRAPH_NL_PROMPTS_PATH", str(prompts_file))

    hints = get_prompt_hints(" How many  nodes?  ")
    assert hints is not None
    assert hints["id"] == "p01"
    assert hints["todo_mode"] == "none"


def test_get_prompt_hints_no_match(tmp_path, monkeypatch):
    prompts_file = tmp_path / "prompts.json"
    prompts_file.write_text("[]", encoding="utf-8")

    monkeypatch.setenv("LLM_MEMGRAPH_NL_TEST_MODE", "true")
    monkeypatch.setenv("LLM_MEMGRAPH_NL_PROMPTS_PATH", str(prompts_file))

    assert get_prompt_hints("unknown prompt") is None
