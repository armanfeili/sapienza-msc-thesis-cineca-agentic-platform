"""
Reusable sample data helpers for tests.

This module provides tiny, dependency-free generators for CSV / JSONL payloads
and small utilities to materialize those payloads on disk inside a pytest
tmp_path. Tests across ETL, archive, and integration suites import from here.

Exports
-------
- SAMPLE_NODES: list of example node dicts
- SAMPLE_RELS: list of example relationship dicts
- generate_nodes_csv_text() -> str
- generate_relationships_csv_text() -> str
- write_sample_csvs(tmp_path) -> dict[str, pathlib.Path]
- write_sample_jsonl(tmp_path) -> pathlib.Path
- write_snapshot_json(tmp_path, *, gzip=False, nodes=None, rels=None) -> pathlib.Path
"""

from __future__ import annotations

import gzip
import io
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple


# ──────────────────────────────────────────────────────────────────────────────
# Canonical in-memory records (used by multiple tests)
# ──────────────────────────────────────────────────────────────────────────────

SAMPLE_NODES: List[Dict[str, Any]] = [
    # People
    {"orig_id": "u1", "labels": ["Person"], "properties": {"name": "Alice", "age": 30, "country": "UK"}},
    {"orig_id": "u2", "labels": ["Person"], "properties": {"name": "Bob", "age": 40, "country": "FR"}},
    # Company / Project
    {"orig_id": "c1", "labels": ["Company"], "properties": {"name": "Acme Corp", "sector": "R&D"}},
    {"orig_id": "p1", "labels": ["Project"], "properties": {"name": "Apollo", "budget": 100000}},
]

SAMPLE_RELS: List[Dict[str, Any]] = [
    {"type": "KNOWS", "start": "u1", "end": "u2", "properties": {"since": 2019}},
    {"type": "WORKS_AT", "start": "u1", "end": "c1", "properties": {"role": "Engineer"}},
    {"type": "WORKS_AT", "start": "u2", "end": "c1", "properties": {"role": "Manager"}},
    {"type": "ASSIGNED_TO", "start": "u1", "end": "p1", "properties": {"since": 2021}},
]


# Backwards-compatible aliases expected by some tests
SAMPLE_RELATIONSHIPS = SAMPLE_RELS


# ──────────────────────────────────────────────────────────────────────────────
# CSV generators (compatible with ETLService.import_*_csv)
# ──────────────────────────────────────────────────────────────────────────────


def generate_nodes_csv_text(rows: Optional[Sequence[Mapping[str, Any]]] = None) -> str:
    """
    Return a CSV string with headers: orig_id,name,age,country,labels (labels JSON)

    Intended to be imported with:
        etl.import_nodes_csv(..., label="Person", mapping=CsvMapping(id_column="orig_id"))
    where additional_labels can be provided if tests want multiple labels.
    """
    rows = rows or SAMPLE_NODES
    # Create a flattened view; labels column is kept JSON-ish for convenience but
    # ETLService.import_nodes_csv ignores it unless mapped into props (default behavior).
    headers = ["orig_id", "name", "age", "country", "labels", "sector", "budget"]
    out = io.StringIO()
    out.write(",".join(headers) + "\n")
    for n in rows:
        props = dict(n.get("properties") or {})
        labels = n.get("labels") or []
        out.write(
            ",".join(
                [
                    str(n.get("orig_id", "")),
                    str(props.get("name", "")),
                    str(props.get("age", "")),
                    str(props.get("country", "")),
                    json.dumps(labels),
                    str(props.get("sector", "")),
                    str(props.get("budget", "")),
                ]
            )
            + "\n"
        )
    return out.getvalue()


def generate_relationships_csv_text(rows: Optional[Sequence[Mapping[str, Any]]] = None) -> str:
    """
    Return a CSV string with headers: start_id,end_id,role,since,type

    Intended to be imported with:
        etl.import_relationships_csv(..., rel_type="<TYPE>", start_id_col="start_id", end_id_col="end_id")
    The rel_type parameter controls the created relationship label; ancillary columns
    will be copied as properties by passing prop_columns=None (default behavior).
    """
    rows = rows or SAMPLE_RELS
    headers = ["start_id", "end_id", "role", "since", "type"]
    out = io.StringIO()
    out.write(",".join(headers) + "\n")
    for r in rows:
        props = dict(r.get("properties") or {})
        out.write(
            ",".join(
                [
                    str(r.get("start", "")),
                    str(r.get("end", "")),
                    str(props.get("role", "")),
                    str(props.get("since", "")),
                    str(r.get("type", "")),
                ]
            )
            + "\n"
        )
    return out.getvalue()


def write_sample_csvs(
    tmp_path: Path,
    *,
    node_rows: Optional[Sequence[Mapping[str, Any]]] = None,
    rel_rows: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Dict[str, Path]:
    """
    Materialize nodes.csv and relationships.csv under the given tmp_path.

    Returns:
        {"nodes": <path>, "relationships": <path>}
    """
    base = Path(tmp_path)
    base.mkdir(parents=True, exist_ok=True)
    nodes_path = base / "sample_nodes.csv"
    rels_path = base / "sample_relationships.csv"
    nodes_path.write_text(generate_nodes_csv_text(node_rows), encoding="utf-8")
    rels_path.write_text(generate_relationships_csv_text(rel_rows), encoding="utf-8")
    return {"nodes": nodes_path, "relationships": rels_path}


# ──────────────────────────────────────────────────────────────────────────────
# JSONL generators (compatible with ETLService.import_jsonl)
# ──────────────────────────────────────────────────────────────────────────────


def _node_to_jsonl_record(n: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "type": "node",
        "id": n.get("orig_id"),
        "labels": list(n.get("labels") or []),
        "properties": dict(n.get("properties") or {}),
    }


def _rel_to_jsonl_record(r: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "type": "relationship",
        "label": r.get("type"),
        "start": {"id": r.get("start")},
        "end": {"id": r.get("end")},
        "properties": dict(r.get("properties") or {}),
    }


def write_sample_jsonl(
    tmp_path: Path,
    *,
    nodes: Optional[Sequence[Mapping[str, Any]]] = None,
    rels: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Path:
    """
    Write a JSONL file mixing node/relationship records.
    """
    nodes = list(nodes or SAMPLE_NODES)
    rels = list(rels or SAMPLE_RELS)
    dest = Path(tmp_path) / "sample.jsonl"
    with dest.open("w", encoding="utf-8") as f:
        for n in nodes:
            f.write(json.dumps(_node_to_jsonl_record(n), ensure_ascii=False) + "\n")
        for r in rels:
            f.write(json.dumps(_rel_to_jsonl_record(r), ensure_ascii=False) + "\n")
    return dest


# ──────────────────────────────────────────────────────────────────────────────
# Snapshot helpers (compatible with ArchiveService expectations)
# ──────────────────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def build_snapshot_payload(
    *, nodes: Optional[Sequence[Mapping[str, Any]]] = None, rels: Optional[Sequence[Mapping[str, Any]]] = None
) -> Dict[str, Any]:
    nodes = list(nodes or SAMPLE_NODES)
    rels = list(rels or SAMPLE_RELS)
    return {
        "generated_at": _now_iso(),
        "node_count": len(nodes),
        "relationship_count": len(rels),
        "nodes": [
            {
                "orig_id": n.get("orig_id"),
                "labels": list(n.get("labels") or []),
                "properties": dict(n.get("properties") or {}),
            }
            for n in nodes
        ],
        "relationships": [
            {
                "type": r.get("type"),
                "start": r.get("start"),
                "end": r.get("end"),
                "properties": dict(r.get("properties") or {}),
            }
            for r in rels
        ],
    }


def write_snapshot_json(
    tmp_path: Path,
    *,
    gzip_output: bool = False,
    nodes: Optional[Sequence[Mapping[str, Any]]] = None,
    rels: Optional[Sequence[Mapping[str, Any]]] = None,
    name_prefix: str = "graph",
) -> Path:
    """
    Write a snapshot JSON (or .json.gz) file shaped as expected by ArchiveService.restore_graph.
    """
    payload = build_snapshot_payload(nodes=nodes, rels=rels)
    dest = Path(tmp_path) / f"{name_prefix}-snapshot.json"
    if gzip_output:
        dest = dest.with_suffix(dest.suffix + ".gz")
        with gzip.open(dest, "wb") as f:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            f.write(data)
    else:
        dest.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return dest
