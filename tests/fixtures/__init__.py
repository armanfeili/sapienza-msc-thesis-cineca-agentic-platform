"""
Shared test fixtures package.

This module re-exports common helpers and provides tiny utilities that are handy
across tests. It deliberately has **no external dependencies** beyond the stdlib,
so import cost is minimal.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

# Re-export the lightweight Memgraph test double
try:
    from .fake_memgraph import FakeMemgraphAdapter  # noqa: F401
except Exception:  # pragma: no cover - available in the repo, but keep tests robust
    FakeMemgraphAdapter = object  # type: ignore


# Optional sample data re-exports (present in this repo)
try:  # pragma: no cover - wiring only
    from .sample_data import (  # noqa: F401
        SAMPLE_NODE_ROWS,
        SAMPLE_REL_ROWS,
    )
except Exception:  # pragma: no cover
    SAMPLE_NODE_ROWS = [
        {"orig_id": "u1", "name": "Alice", "age": "34"},
        {"orig_id": "u2", "name": "Bob", "age": "29"},
    ]
    SAMPLE_REL_ROWS = [
        {"start_orig_id": "u1", "type": "KNOWS", "end_orig_id": "u2", "since": "2020"},
    ]


FIXTURES_DIR = Path(__file__).parent


def data_path(*parts: str) -> Path:
    """
    Return an absolute path inside the tests/fixtures directory.

    Example:
        data_path("data.json")
    """
    return FIXTURES_DIR.joinpath(*parts)


def write_nodes_csv(rows: Sequence[Mapping[str, str]], dest: Path) -> Path:
    """
    Write a generic nodes CSV for ETL import with at least 'orig_id' present.
    Extra columns are preserved as node properties.

    Headers are the union of all keys across rows (stable order: first row first).
    """
    if not rows:
        rows = [{"orig_id": "n1"}]  # minimal valid
    # Collect headers with stable order (keys from the first row first)
    headers: list[str] = list(rows[0].keys())
    for r in rows[1:]:
        for k in r.keys():
            if k not in headers:
                headers.append(k)

    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in headers})
    return dest


def write_relationships_csv(rows: Sequence[Mapping[str, str]], dest: Path) -> Path:
    """
    Write a relationships CSV compatible with ETLService.import_relationships_csv.

    Expected minimal columns:
      - start_orig_id
      - end_orig_id
      - type

    Any additional columns will be treated as relationship properties.
    """
    if not rows:
        rows = [{"start_orig_id": "n1", "type": "LINKS", "end_orig_id": "n2"}]

    headers: list[str] = list(rows[0].keys())
    for r in rows[1:]:
        for k in r.keys():
            if k not in headers:
                headers.append(k)

    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in headers})
    return dest


def write_json(path: Path, payload) -> Path:
    """Convenience: write a JSON payload to disk (UTF-8, pretty)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return path


__all__ = [
    "FakeMemgraphAdapter",
    "SAMPLE_NODE_ROWS",
    "SAMPLE_REL_ROWS",
    "FIXTURES_DIR",
    "data_path",
    "write_nodes_csv",
    "write_relationships_csv",
    "write_json",
]
