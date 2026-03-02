"""
ETL service for importing, transforming, and exporting Memgraph data.

Highlights
- CSV → Nodes / Relationships (configurable mapping)
- JSONL → Generic import (compatible with db/create_original_db.py format)
- Snapshot export (nodes + relationships) to JSON
- Lightweight graph stats & validation helpers
- Pure-Python; no external IO libs required

Notes
- Uses MERGE on :Label {orig_id:$orig_id} for idempotent upserts.
- Relationship imports use MERGE (a)-[:TYPE]->(b) by matching endpoints on orig_id.
- For large imports, increase batch_size or switch to server-side loaders later.
"""

from __future__ import annotations

import asyncio
import contextlib
import csv
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from src.services import ServiceBase, ServiceError, ServiceResult, utc_now

if TYPE_CHECKING:
    pass

try:
    from src.config import settings
except Exception:  # pragma: no cover
    settings = None  # type: ignore[assignment,misc]


log = structlog.get_logger(__name__)

DEFAULT_BATCH_SIZE = 500


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def _batched(items: Iterable[Any], size: int) -> Iterable[list[Any]]:
    batch: list[Any] = []
    for it in items:
        batch.append(it)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


async def _to_thread(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


# ──────────────────────────────────────────────────────────────────────────────
# Service
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class CsvMapping:
    """
    Column mapping for CSV imports.

    Attributes
    ----------
    id_column: column providing the unique orig_id (or any stable id)
    prop_columns: if None, use all columns (except id_column); otherwise use listed
    """

    id_column: str = "orig_id"
    prop_columns: Sequence[str] | None = None


class ETLService(ServiceBase):
    """
    Extract/Transform/Load utilities around Memgraph.

    Most routines are async wrappers around synchronous I/O and db calls.
    """

    def __init__(self, db: Any | None = None) -> None:
        super().__init__(name="etl-service")
        if db is not None:
            self.db = db
        else:
            # Attempt to initialize an adapter, but fall back to None if settings/adapter aren't present
            try:
                from src.adapters.db_memgraph import (
                    MemgraphAdapter as _RuntimeMemgraphAdapter,  # type: ignore
                )
            except Exception:
                _RuntimeMemgraphAdapter = None  # type: ignore

            try:
                _global_MemgraphAdapter = globals().get("MemgraphAdapter", None)
            except Exception:
                _global_MemgraphAdapter = None
            adapter_cls = _RuntimeMemgraphAdapter or _global_MemgraphAdapter
            if adapter_cls and settings:
                try:
                    self.db = adapter_cls.from_env()  # type: ignore[assignment]
                except Exception:
                    try:
                        self.db = adapter_cls()
                    except Exception as exc:  # pragma: no cover - defensive
                        raise ServiceError(f"Failed to initialize Memgraph adapter: {exc}") from exc
            else:
                # Do not raise during construction; allow callers to provide db later or use ETL purely for file operations
                self.db = None

        # basic sanity
        try:
            if self.db is not None:
                self.db.ping()  # type: ignore[attr-defined]
        except Exception:
            log.warning("etl.db.ping_failed")

    def _exec_statements(self, statements: list[tuple[str, dict[str, Any]]]) -> None:
        """Execute a list of (query, params) statements using either
        bulk_execute when available or a per-statement execute fallback.
        """
        if not statements:
            return
        if self.db is None:
            return
        try:
            if hasattr(self.db, "bulk_execute"):
                self.db.bulk_execute(statements)  # type: ignore[attr-defined]
                return
        except Exception:
            # fall back to per-statement execution
            log.debug("etl.bulk_execute_failed_fallback")

        for q, params in statements:
            try:
                # prefer execute(q, params)
                try:
                    self.db.execute(q, params)  # type: ignore[attr-defined]
                except TypeError:
                    self.db.execute(q)  # type: ignore[attr-defined]
            except Exception:
                # ignore single statement failure in best-effort mode
                log.warning("etl.exec_statement_failed", query=q)

    # ──────────────────────────────────────────────────────────────────
    # CSV → Nodes
    # ──────────────────────────────────────────────────────────────────
    async def import_nodes_csv(
        self,
        csv_path: str | Path,
        *,
        label: str,
        mapping: CsvMapping = CsvMapping(),
        additional_labels: Sequence[str] | None = None,
        ensure_index_on: Sequence[str] | None = ("orig_id",),
        batch_size: int = DEFAULT_BATCH_SIZE,
        lower_case_headers: bool = True,
    ) -> ServiceResult[dict[str, Any]]:
        """
        Import nodes from a CSV file. Each row becomes one node.

        Example:
            await etl.import_nodes_csv("users.csv", label="User",
                                       mapping=CsvMapping(id_column="user_id"))

        Returns:
            { inserted: N, label: "User" }
        """
        path = Path(csv_path)
        if not path.exists():
            return ServiceResult.failure(f"CSV not found: {path}", code="NOT_FOUND")

        # Prepare label set
        labels = [label, *list(additional_labels or [])]
        labels_cypher = ":".join(f"`{l}`" for l in labels)

        # Ensure indexes
        if ensure_index_on:
            for prop in ensure_index_on:
                q = f"CREATE INDEX ON :`{label}`(`{prop}`)"
                try:
                    if self.db is not None:
                        self.db.execute(q)  # type: ignore[attr-defined]
                except Exception:
                    # ignore "already exists"
                    log.debug("etl.create_index_skipped", prop=prop, label=label)

        def _read_rows() -> list[dict[str, Any]]:
            with path.open("r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows: list[dict[str, Any]] = []
                for row in reader:
                    if lower_case_headers:
                        row = {str(k).lower(): v for k, v in row.items()}
                    rows.append(row)
                return rows

        rows = await _to_thread(_read_rows)
        if not rows:
            return ServiceResult.success({"inserted": 0, "label": label})

        # If headers were lower-cased, normalize any provided mapping
        if lower_case_headers and mapping:
            mapping = CsvMapping(
                id_column=(mapping.id_column.lower() if mapping.id_column else mapping.id_column),
                prop_columns=(
                    [c.lower() for c in mapping.prop_columns] if mapping.prop_columns else mapping.prop_columns
                ),
            )

        # Determine properties to include
        if mapping.prop_columns is None:
            all_cols = list(rows[0].keys())
            prop_cols = [c for c in all_cols if c != mapping.id_column]
        else:
            prop_cols = list(mapping.prop_columns)

        total = 0
        for batch in _batched(rows, batch_size):
            statements: list[tuple[str, dict[str, Any]]] = []
            for r in batch:
                orig_id = r.get(mapping.id_column)
                if orig_id is None or orig_id == "":
                    # skip rows missing id
                    continue
                props = {c: r.get(c) for c in prop_cols if c != mapping.id_column}
                props["orig_id"] = orig_id
                q = f"MERGE (n:{labels_cypher} {{orig_id:$orig_id}}) SET n += $props"
                statements.append((q, {"orig_id": orig_id, "props": props}))
            if statements:
                if self.db is not None:
                    self._exec_statements(statements)
                # When no DB is configured (tests), treat statements as counted but skip execution
                total += len(statements)

        log.info("etl.import_nodes_csv.ok", label=label, inserted=total, file=str(path))
        return ServiceResult.success({"inserted": total, "label": label})

    # ──────────────────────────────────────────────────────────────────
    # CSV → Relationships
    # ──────────────────────────────────────────────────────────────────
    async def import_relationships_csv(
        self,
        csv_path: str | Path,
        *,
        rel_type: str,
        start_id_col: str,
        end_id_col: str,
        start_label: str | None = None,
        end_label: str | None = None,
        prop_columns: Sequence[str] | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        lower_case_headers: bool = True,
    ) -> ServiceResult[dict[str, Any]]:
        """
        Import relationships from CSV using orig_id endpoints.

        CSV must include columns for `start_id_col` and `end_id_col`.
        """
        path = Path(csv_path)
        if not path.exists():
            return ServiceResult.failure(f"CSV not found: {path}", code="NOT_FOUND")

        def _read_rows() -> list[dict[str, Any]]:
            with path.open("r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = []
                for row in reader:
                    if lower_case_headers:
                        row = {str(k).lower(): v for k, v in row.items()}
                    rows.append(row)
                return rows

        rows = await _to_thread(_read_rows)
        if not rows:
            return ServiceResult.success({"created": 0, "type": rel_type})

        # Normalize column names if headers were lowercased
        if lower_case_headers:
            start_id_col = start_id_col.lower()
            end_id_col = end_id_col.lower()
            if prop_columns is not None:
                prop_columns = [c.lower() for c in prop_columns]

        # Ensure indexes on endpoint id properties to speed up MERGE (do once)
        try:
            if start_label and start_id_col:
                self.db.execute(f"CREATE INDEX IF NOT EXISTS FOR (n:{start_label}) ON (n.{start_id_col})")
        except Exception:
            log.debug("etl.create_index_skipped", label=start_label)
        try:
            if end_label and end_id_col:
                self.db.execute(f"CREATE INDEX IF NOT EXISTS FOR (n:{end_label}) ON (n.{end_id_col})")
        except Exception:
            log.debug("etl.create_index_skipped", label=end_label)

        prefix_a = f":`{start_label}`" if start_label else ""
        prefix_b = f":`{end_label}`" if end_label else ""
        rel_cypher = f":`{rel_type}`"

        total = 0
        for batch in _batched(rows, batch_size):
            statements: list[tuple[str, dict[str, Any]]] = []
            for r in batch:
                sid = r.get(start_id_col)
                tid = r.get(end_id_col)
                if not sid or not tid:
                    continue
                props = {c: r.get(c) for c in prop_columns or []}
                # Ensure indexes on endpoint id properties to speed up MERGE
                if start_label and start_id_col:
                    with contextlib.suppress(Exception):
                        self.db.execute(f"CREATE INDEX IF NOT EXISTS FOR (n:{start_label}) ON (n.{start_id_col})")
                if end_label and end_id_col:
                    with contextlib.suppress(Exception):
                        self.db.execute(f"CREATE INDEX IF NOT EXISTS FOR (n:{end_label}) ON (n.{end_id_col})")

                q = (
                    f"MATCH (a{prefix_a} {{orig_id:$sid}}), (b{prefix_b} {{orig_id:$tid}}) "
                    f"MERGE (a)-[rel{rel_cypher}]->(b) "
                    f"SET rel += $props"
                )
                statements.append((q, {"sid": sid, "tid": tid, "props": props}))
            if statements:
                if self.db is not None:
                    self._exec_statements(statements)
                total += len(statements)

        log.info("etl.import_relationships_csv.ok", type=rel_type, created=total, file=str(path))
        return ServiceResult.success({"created": total, "type": rel_type})

    # ──────────────────────────────────────────────────────────────────
    # JSONL Import (nodes + relationships)
    # ──────────────────────────────────────────────────────────────────
    async def import_jsonl(
        self,
        jsonl_path: str | Path,
        *,
        create_indexes: bool = True,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> ServiceResult[dict[str, int]]:
        """
        Import a JSON-lines file with records:
          {"type":"node","id":"...","labels":["User"],"properties":{...}}
          {"type":"relationship","label":"WORKS_AT","start":{"id":"..."}, "end":{"id":"..."}, "properties":{...}}
        """
        path = Path(jsonl_path)
        if not path.exists():
            return ServiceResult.failure(f"File not found: {path}", code="NOT_FOUND")

        def _read() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
            nodes: list[dict[str, Any]] = []
            rels: list[dict[str, Any]] = []
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    if rec.get("type") == "node":
                        nodes.append(rec)
                    elif rec.get("type") == "relationship":
                        rels.append(rec)
            return nodes, rels

        nodes, rels = await _to_thread(_read)
        if create_indexes:
            # index orig_id for each label observed
            seen: set[str] = set()
            for n in nodes:
                for lbl in n.get("labels", []):
                    if lbl not in seen:
                        seen.add(lbl)
                        try:
                            self.db.execute(f"CREATE INDEX ON :`{lbl}`(`orig_id`)")  # type: ignore[attr-defined]
                        except Exception:
                            log.debug("etl.create_index_skipped", label=lbl)

        # Insert nodes
        node_count = 0
        for batch in _batched(nodes, batch_size):
            stmts: list[tuple[str, dict[str, Any]]] = []
            for n in batch:
                labels = ":".join(f"`{l}`" for l in n.get("labels", []))
                props = dict(n.get("properties") or {})
                props["orig_id"] = n.get("id")
                q = f"MERGE (n:{labels} {{orig_id:$id}}) SET n += $props"
                stmts.append((q, {"id": n.get("id"), "props": props}))
            if stmts:
                if self.db is not None:
                    self._exec_statements(stmts)
                node_count += len(stmts)

        # Insert relationships
        rel_count = 0
        for batch in _batched(rels, batch_size):
            stmts = []
            for r in batch:
                lbl = r.get("label")
                sid = r.get("start", {}).get("id")
                tid = r.get("end", {}).get("id")
                props = dict(r.get("properties") or {})
                if not lbl or not sid or not tid:
                    continue
                q = "MATCH (a {orig_id:$a}), (b {orig_id:$b}) " f"MERGE (a)-[rel:`{lbl}`]->(b) " "SET rel += $props"
                stmts.append((q, {"a": sid, "b": tid, "props": props}))
            if stmts:
                if self.db is not None:
                    self._exec_statements(stmts)
                rel_count += len(stmts)

        log.info("etl.import_jsonl.ok", nodes=node_count, relationships=rel_count, file=str(path))
        return ServiceResult.success({"nodes": node_count, "relationships": rel_count})

    # ──────────────────────────────────────────────────────────────────
    # Exporters
    # ──────────────────────────────────────────────────────────────────
    async def snapshot_export(
        self,
        out_path: str | Path,
        *,
        pretty: bool = False,
        include_properties: bool = True,
    ) -> ServiceResult[dict[str, Any]]:
        """
        Export full graph to JSON with shape:
        {
          "generated_at": "...",
          "nodes": [{"orig_id": "...", "labels": [...], "properties": {...}}, ...],
          "relationships": [{"type":"X","start":"...","end":"...","properties": {...}}, ...]
        }
        """
        path = Path(out_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Nodes
        nodes_q = (
            "MATCH (n) "
            "RETURN n.orig_id AS orig_id, labels(n) AS labels, "
            f"{'properties(n) AS properties' if include_properties else 'NULL AS properties'}"
        )
        nodes = list(self.db.execute_and_fetch(nodes_q))  # type: ignore[attr-defined]

        # Relationships
        rels_q = (
            "MATCH (a)-[r]->(b) "
            "RETURN type(r) AS type, a.orig_id AS start, b.orig_id AS end, "
            f"{'properties(r) AS properties' if include_properties else 'NULL AS properties'}"
        )
        rels = list(self.db.execute_and_fetch(rels_q))  # type: ignore[attr-defined]

        payload = {
            "generated_at": utc_now().isoformat(),
            "node_count": len(nodes),
            "relationship_count": len(rels),
            "nodes": nodes,
            "relationships": rels,
        }

        def _write():
            with path.open("w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2 if pretty else None, ensure_ascii=False)

        await _to_thread(_write)
        log.info("etl.snapshot_export.ok", nodes=len(nodes), relationships=len(rels), file=str(path))
        return ServiceResult.success({"nodes": len(nodes), "relationships": len(rels), "file": str(path)})

    async def export_nodes_csv(
        self,
        out_path: str | Path,
        *,
        label: str | None = None,
        limit: int | None = None,
    ) -> ServiceResult[dict[str, Any]]:
        """
        Export nodes (optionally filtered by label) to CSV with dynamic properties.
        The CSV contains 'orig_id', 'labels', and a JSON column 'properties'.
        """
        path = Path(out_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        where = f"WHERE '{label}' IN labels(n)" if label else ""
        lim = f"LIMIT {int(limit)}" if limit else ""
        q = (
            f"MATCH (n) {where} "
            "RETURN n.orig_id AS orig_id, labels(n) AS labels, properties(n) AS properties "
            f"{lim}"
        )
        rows = list(self.db.execute_and_fetch(q))  # type: ignore[attr-defined]

        def _write():
            with path.open("w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow(["orig_id", "labels", "properties"])
                for r in rows:
                    w.writerow([r.get("orig_id"), json.dumps(r.get("labels")), json.dumps(r.get("properties"))])

        await _to_thread(_write)
        log.info("etl.export_nodes_csv.ok", count=len(rows), label=label, file=str(path))
        return ServiceResult.success({"count": len(rows), "file": str(path)})

    async def export_relationships_csv(
        self,
        out_path: str | Path,
        *,
        type_filter: str | None = None,
        limit: int | None = None,
    ) -> ServiceResult[dict[str, Any]]:
        """
        Export relationships to CSV with columns: start_orig_id, type, end_orig_id, properties(JSON).
        """
        path = Path(out_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        where = f"WHERE type(r) = '{type_filter}'" if type_filter else ""
        lim = f"LIMIT {int(limit)}" if limit else ""
        q = (
            f"MATCH (a)-[r]->(b) {where} "
            "RETURN a.orig_id AS start, type(r) AS type, b.orig_id AS end, properties(r) AS properties "
            f"{lim}"
        )
        rows = list(self.db.execute_and_fetch(q))  # type: ignore[attr-defined]

        def _write():
            with path.open("w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow(["start_orig_id", "type", "end_orig_id", "properties"])
                for r in rows:
                    w.writerow([r.get("start"), r.get("type"), r.get("end"), json.dumps(r.get("properties"))])

        await _to_thread(_write)
        log.info("etl.export_relationships_csv.ok", count=len(rows), type=type_filter, file=str(path))
        return ServiceResult.success({"count": len(rows), "file": str(path)})

    # ──────────────────────────────────────────────────────────────────
    # Utilities & transforms
    # ──────────────────────────────────────────────────────────────────
    async def validate_graph(self) -> ServiceResult[dict[str, Any]]:
        """
        Return quick counts to sanity-check the graph.
        """
        nodes = next(self.db.execute_and_fetch("MATCH (n) RETURN count(n) AS c"))["c"]  # type: ignore[attr-defined]
        rels = next(self.db.execute_and_fetch("MATCH ()-[r]->() RETURN count(r) AS c"))["c"]  # type: ignore[attr-defined]
        labels = list(self.db.execute_and_fetch("MATCH (n) UNWIND labels(n) AS l RETURN DISTINCT l AS label"))  # type: ignore[attr-defined]
        types = list(self.db.execute_and_fetch("MATCH ()-[r]->() RETURN DISTINCT type(r) AS type"))  # type: ignore[attr-defined]
        return ServiceResult.success(
            {
                "node_count": nodes,
                "relationship_count": rels,
                "labels": [x["label"] for x in labels],
                "relationship_types": [x["type"] for x in types],
            }
        )

    async def deduplicate_by_property(self, *, label: str, prop: str = "orig_id") -> ServiceResult[dict[str, Any]]:
        """
        Delete duplicate nodes keeping one per unique property value.
        This is conservative; it only removes exact duplicates by (label, prop).
        """
        q = (
            "MATCH (n:`{label}`) "
            "WITH n.{prop} AS k, collect(n) AS nodes "
            "WHERE size(nodes) > 1 "
            "WITH nodes[0] AS keep, nodes[1..] AS dups "
            "FOREACH (d IN dups | DETACH DELETE d) "
            "RETURN 0 AS ok"
        ).format(label=label.replace("`", ""), prop=prop)
        try:
            self.db.execute(q)  # type: ignore[attr-defined]
        except Exception as exc:
            return ServiceResult.failure(f"Deduplication failed: {exc}")
        return ServiceResult.success({"status": "ok", "label": label, "property": prop})

    async def run_query_file(self, cypher_path: str | Path) -> ServiceResult[dict[str, Any]]:
        """
        Execute a .cypher/.cql file containing one or more queries separated by ';\n'
        """
        path = Path(cypher_path)
        if not path.exists():
            return ServiceResult.failure(f"File not found: {path}", code="NOT_FOUND")

        def _read() -> str:
            return path.read_text(encoding="utf-8")

        content = await _to_thread(_read)
        # naive split on semicolon-newline boundaries; preserves semicolons in strings poorly
        # For robust parsing, feed the file as-is to the driver; here we keep it simple.
        queries = [q.strip() for q in content.split(";\n") if q.strip()]
        for q in queries:
            self.db.execute(q)  # type: ignore[attr-defined]
        log.info("etl.run_query_file.ok", queries=len(queries), file=str(path))
        return ServiceResult.success({"executed": len(queries)})

    # ──────────────────────────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────────────────────────
    async def start(self) -> None:
        await super().start()
        log.info("etl.started")

    async def stop(self) -> None:
        log.info("etl.stopping")
        await super().stop()
