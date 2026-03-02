"""Utilities for normalizing agent run outputs.

Ensures that orchestration outputs stored in the database or emitted by
APIs always conform to the schema contract (dict/list/None) regardless of
how upstream components provide them.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any

from pydantic import BaseModel


def normalize_run_output(value: Any) -> dict | list | None:
    """Coerce arbitrary orchestrator output into schema-compliant structures."""
    if value is None:
        return None

    # Decode binary blobs first
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, bytearray):
        value = bytes(value)
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="ignore")

    if isinstance(value, (dict, list)):
        return value

    if is_dataclass(value):
        return asdict(value)

    if isinstance(value, BaseModel):
        return value.model_dump()

    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump()
            if isinstance(dumped, (dict, list)):
                return dumped
        except Exception:  # pragma: no cover - defensive fallback
            pass

    if isinstance(value, (tuple, set)):
        return [value_item for value_item in value]

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            parsed = None
        else:
            if isinstance(parsed, (dict, list)):
                return parsed
            if isinstance(parsed, str):
                return {"text": parsed}
            if isinstance(parsed, (int, float, bool)):
                return {"text": str(parsed)}
            if parsed is None:
                return None
        return {"text": stripped}

    if isinstance(value, (int, float, bool)):
        return {"text": str(value)}

    # Fallback for anything else (objects, Decimal, etc.)
    return {"text": str(value)}
