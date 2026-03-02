"""Memgraph NL test-mode helpers for orchestrator hints."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import structlog

log = structlog.get_logger(__name__)

_TEST_MODE_ENV = "LLM_MEMGRAPH_NL_TEST_MODE"
_PROMPT_PATH_ENV = "LLM_MEMGRAPH_NL_PROMPTS_PATH"
_DEFAULT_PROMPTS_REL = Path("tests/integration/resources/memgraph_nl_prompts.json")


def _is_enabled() -> bool:
    value = os.getenv(_TEST_MODE_ENV)
    if value is None:
        # Default to enabled so integration prompts work out of the box.
        return True
    value = value.strip().lower()
    return value in {"1", "true", "yes", "on"}


def _default_prompt_path() -> Path:
    # Resolve repo root by walking up from this file (src/memgraph/test_mode.py)
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / _DEFAULT_PROMPTS_REL


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(text.strip().lower().split())


@lru_cache(maxsize=1)
def _load_prompt_index(path: str) -> dict[str, Dict[str, Any]]:
    prompt_path = Path(path)
    if not prompt_path.exists():
        log.warning(
            "memgraph.prompts.missing",
            path=str(prompt_path),
            message="Prompt metadata file not found - simple mode hints disabled",
        )
        return {}

    try:
        with prompt_path.open("r", encoding="utf-8") as fp:
            payload = json.load(fp)
    except Exception as exc:  # pragma: no cover - defensive guard
        log.error(
            "memgraph.prompts.load_failed",
            path=str(prompt_path),
            error=str(exc),
        )
        return {}

    index: dict[str, Dict[str, Any]] = {}
    if isinstance(payload, list):
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            normalized = _normalize(entry.get("text"))
            if normalized:
                index[normalized] = entry
    else:
        log.warning(
            "memgraph.prompts.invalid_format",
            path=str(prompt_path),
            message="Expected list of prompt entries",
        )
    return index


def reset_prompt_cache() -> None:
    """Reset cached prompt metadata (used in tests)."""

    _load_prompt_index.cache_clear()


def get_prompt_hints(prompt: str | None) -> Optional[Dict[str, Any]]:
    """Return prompt metadata when NL test mode is enabled."""

    if not _is_enabled() or not prompt:
        return None

    prompt_path = os.getenv(_PROMPT_PATH_ENV)
    if not prompt_path:
        prompt_path = str(_default_prompt_path())

    index = _load_prompt_index(prompt_path)
    if not index:
        return None

    normalized = _normalize(prompt)
    if not normalized:
        return None

    entry = index.get(normalized)
    if entry:
        log.debug(
            "memgraph.prompts.match",
            prompt_preview=prompt[:80],
            prompt_id=entry.get("id"),
            todo_mode=entry.get("todo_mode"),
            category=entry.get("category"),
        )
    else:
        log.debug(
            "memgraph.prompts.no_match",
            prompt_preview=prompt[:80],
        )
    return entry
