"""
Fake Memgraph adapter for tests.

This is a tiny, dependency-free in-memory test double that mimics the handful
of methods our services use from `src.adapters.db_memgraph.MemgraphAdapter`.

Supported API (sync):
- ping() -> bool
- info() -> dict
- execute(cypher: str) -> None
- execute_and_fetch(cypher: str) -> Iterable[dict]
- bulk_execute(stmts: list[tuple[str, dict]]) -> None

The goal is to be *just* capable enough to drive unit/integration tests for:
- ETLService (nodes/relationships import/export, counts, labels/types)
- ArchiveService (batched MERGE for nodes and relationships)
- HealthService (ping/info)

It is NOT a full Cypher interpreter; it only recognizes the small set of query
shapes our code emits.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, Iterator, List, Mapping, MutableMapping, Optional, Sequence, Tuple
from pathlib import Path


@dataclass
class _Node:
    orig_id: str
    labels: set[str] = field(default_factory=set)
    properties: Dict[str, object] = field(default_factory=dict)


@dataclass
class _Rel:
    type: str
    start: str
    end: str
    properties: Dict[str, object] = field(default_factory=dict)


class FakeMemgraphAdapter:
    def __init__(self, *_, **__) -> None:
        # Graph state
        self._nodes: Dict[str, _Node] = {}
        # keyed by (start, type, end)
        self._rels: Dict[Tuple[str, str, str], _Rel] = {}
        # Call-recording for tests that assert on adapter traffic
        # keep simple lists so tests can inspect adapter activity
        self.executed = []
        self.bulk_executed = []
        self.query_log = []

    @classmethod
    def from_graph(cls, graph: Mapping[str, object]) -> "FakeMemgraphAdapter":
        """Construct a FakeMemgraphAdapter pre-populated from a snapshot dict
        with keys 'nodes' and 'relationships' matching sample_data.build_snapshot_payload().
        """
        inst = cls()
        nodes = graph.get("nodes") or []
        for n in nodes:
            oid = str(n.get("orig_id") or n.get("id") or "")
            labels = set(l for l in (n.get("labels") or []))
            props = dict(n.get("properties") or {})
            if oid:
                inst._merge_node(oid, labels, props)
        rels = graph.get("relationships") or []
        for r in rels:
            start = str(r.get("start") or "")
            end = str(r.get("end") or "")
            rtype = str(r.get("type") or r.get("label") or "")
            props = dict(r.get("properties") or {})
            if start and end and rtype:
                # Ensure endpoints exist; create minimal nodes if missing
                if start not in inst._nodes:
                    inst._merge_node(start, set(), {})
                if end not in inst._nodes:
                    inst._merge_node(end, set(), {})
                inst._merge_relationship(start, rtype, end, props)
        return inst

    # ──────────────────────────────────────────────────────────────────────
    # Basic API
    # ──────────────────────────────────────────────────────────────────────
    def ping(self) -> bool:
        return True

    def info(self) -> Mapping[str, object]:
        return {
            "fake": True,
            "nodes": len(self._nodes),
            "relationships": len(self._rels),
            "labels": sorted({l for n in self._nodes.values() for l in n.labels}),
            "types": sorted({t for (_, t, _) in self._rels.keys()}),
        }

    # ──────────────────────────────────────────────────────────────────────
    # Write operations
    # ──────────────────────────────────────────────────────────────────────
    def execute(self, cypher: str, params: Optional[Mapping[str, object]] = None) -> None:
        """
        Accepts:
          - CREATE INDEX ... (no-op)
          - Dedup query emitted by ETLService.deduplicate_by_property(...)
          - Single MERGE/MATCH...MERGE statements (delegate to _apply_statement)
        """
        q = (cypher or "").strip()

        # Record call for test observation
        try:
            self.executed.append((q, dict(params or {})))
        except Exception:
            pass

        # CREATE INDEX ... → no-op
        if q.upper().startswith("CREATE INDEX"):
            return

        # Deduplicate by property (very narrow recognition)
        if "FOREACH (d IN dups | DETACH DELETE d)" in q and "MATCH (n:`" in q:
            m = re.search(
                r"MATCH\s+\(n:`(?P<label>[^`]+)`\).*?WITH\s+n\.(?P<prop>[A-Za-z_][A-ZaLz0-9_]*)\s+AS\s+k", q, re.DOTALL
            )
            if not m:
                return
            label = m.group("label")
            prop = m.group("prop")
            # Build buckets by property
            buckets: Dict[object, List[_Node]] = {}
            for node in self._nodes.values():
                if label in node.labels:
                    key = node.properties.get(prop)
                    buckets.setdefault(key, []).append(node)
            # For each bucket with >1, keep first, delete the rest
            to_delete: set[str] = set()
            for nodes in buckets.values():
                if len(nodes) > 1:
                    for d in nodes[1:]:
                        to_delete.add(d.orig_id)
            for oid in to_delete:
                self._delete_node(oid)
            return

        # Delegate other MERGE/relationship creation statements to the internal applier
        try:
            self._apply_statement(q, params or {})
        except Exception:
            # Swallow unexpected errors to keep fake adapter forgiving for tests
            return

    def bulk_execute(self, statements: Sequence[Tuple[str, Mapping[str, object]]]) -> None:
        # Record bulk statements (flattened) for tests
        for cypher, params in statements:
            try:
                self.bulk_executed.append((str(cypher or ""), dict(params or {})))
            except Exception:
                pass
            self._apply_statement(cypher, params or {})

    # ──────────────────────────────────────────────────────────────────────
    # Read operations
    # ──────────────────────────────────────────────────────────────────────
    def execute_and_fetch(
        self, cypher: str, params: Optional[Mapping[str, object]] = None
    ) -> Iterable[Mapping[str, object]]:
        """
        Recognizes the query shapes emitted by ETLService and tests.
        Returns an iterator (so callers may use `next(...)`).
        """
        q = (cypher or "").strip()

        # Record query text for tests
        try:
            self.query_log.append(q)
        except Exception:
            pass

        # Counts
        if re.match(r"^MATCH\s*\(n\)\s*RETURN\s*count\(n\)\s+AS\s+c\s*$", q, re.IGNORECASE):
            return iter([{"c": len(self._nodes)}])
        if re.match(r"^MATCH\s*\(\)\-\[r\]\-\>\(\)\s*RETURN\s*count\(r\)\s+AS\s+c\s*$", q, re.IGNORECASE):
            return iter([{"c": len(self._rels)}])

        # Distinct labels
        if re.match(
            r"^MATCH\s*\(n\)\s*UNWIND\s*labels\(n\)\s*AS\s*l\s*RETURN\s+DISTINCT\s+l\s+AS\s+label\s*$", q, re.IGNORECASE
        ):
            labels = sorted({l for n in self._nodes.values() for l in n.labels})
            return iter([{"label": l} for l in labels])

        # Distinct relationship types
        if re.match(r"^MATCH\s*\(\)\-\[r\]\-\>\(\)\s*RETURN\s+DISTINCT\s+type\(r\)\s+AS\s+type\s*$", q, re.IGNORECASE):
            types = sorted({t for (_, t, _) in self._rels.keys()})
            return iter([{"type": t} for t in types])

        # Nodes snapshot export (full shape)
        if re.match(
            r"^MATCH\s*\(n\)\s*RETURN\s*n\.orig_id\s+AS\s+orig_id,\s*labels\(n\)\s+AS\s+labels,\s*properties\(n\)\s+AS\s+properties\s*$",
            q,
            re.IGNORECASE,
        ):
            out: List[Mapping[str, object]] = []
            for n in self._nodes.values():
                out.append(
                    {
                        "orig_id": n.orig_id,
                        "labels": sorted(n.labels),
                        "properties": dict(n.properties),
                    }
                )
            return iter(out)

        # Nodes simple RETURN labels, properties (used by some tests)
        if re.match(
            r"^MATCH\s*\(n\)\s*RETURN\s*labels\(n\)\s+AS\s+labels,\s*properties\(n\)\s+AS\s+properties\s*$",
            q,
            re.IGNORECASE,
        ):
            out: List[Mapping[str, object]] = []
            for n in self._nodes.values():
                out.append(
                    {
                        "labels": sorted(n.labels),
                        "properties": dict(n.properties),
                    }
                )
            return iter(out)

        # Properties lookup by orig_id (e.g. MATCH (n {orig_id:'u1'}) RETURN properties(n) AS properties)
        m_props = re.match(
            r"^MATCH\s*\(n\s*\{\s*orig_id\s*:\s*'(?P<id>[^']+)'\s*\}\)\s*RETURN\s*properties\(n\)\s+AS\s+properties\s*$",
            q,
            re.IGNORECASE,
        )
        if m_props:
            node_id = m_props.group("id")
            node = self._nodes.get(node_id)
            if node:
                return iter([{"properties": dict(node.properties)}])
            return iter([])

        # Relationships snapshot export
        if re.match(
            r"^MATCH\s*\(a\)\-\[r\]\-\>\(b\)\s*RETURN\s*type\(r\)\s+AS\s+type,\s*a\.orig_id\s+AS\s+start,\s+b\.orig_id\s+AS\s+end,\s*properties\(r\)\s+AS\s+properties\s*$",
            q,
            re.IGNORECASE,
        ):
            out: List[Mapping[str, object]] = []
            for (s, t, e), r in self._rels.items():
                out.append(
                    {
                        "type": t,
                        "start": s,
                        "end": e,
                        "properties": dict(r.properties),
                    }
                )
            return iter(out)

        # Fallback: return empty iterator
        return iter([])

    # ──────────────────────────────────────────────────────────────────────
    # Internals
    # ──────────────────────────────────────────────────────────────────────
    def _apply_statement(self, cypher: str, params: Mapping[str, object]) -> None:
        """
        Handle the MERGE/SET patterns emitted by our services.
        """
        q = (cypher or "").strip()

        # MERGE (n:<labels> {orig_id:$id|$orig_id}) SET n += $props
        m_node = re.match(
            r"^MERGE\s*\(n(?::(?P<labels>(?:`[^`]+`:?)+))?\s*\{\s*orig_id:\s*\$(?P<idkey>id|orig_id)\s*\}\)\s*SET\s*n\s*\+=\s*\$props\s*$",
            q,
        )
        if m_node:
            labels_str = m_node.group("labels") or ""
            idkey = m_node.group("idkey")
            oid = str(params.get(idkey, ""))
            props = dict(params.get("props", {})) if isinstance(params.get("props"), Mapping) else {}
            if not oid:
                return
            labels = {lbl.strip("`") for lbl in labels_str.split(":") if lbl} if labels_str else set()
            self._merge_node(oid, labels, props)
            return

        # MATCH (a {orig_id:$a|$sid}), (b {orig_id:$b|$tid}) MERGE (a)-[rel:`TYPE`]->(b) SET rel += $props
        m_rel = re.match(
            r"^MATCH\s*\(a(?:[:`A-Za-z0-9_`]+)?\s*\{\s*orig_id\s*:\s*\$(?P<akey>a|sid)\s*\}\)\s*,\s*"
            r"\(b(?:[:`A-Za-z0-9_`]+)?\s*\{\s*orig_id\s*:\s*\$(?P<bkey>b|tid)\s*\}\)\s*"
            r"MERGE\s*\(a\)\-\[rel:`(?P<type>[^`]+)`\]\-\>\(b\)\s*SET\s*rel\s*\+=\s*\$props\s*$",
            q,
        )
        if m_rel:
            akey = m_rel.group("akey")
            bkey = m_rel.group("bkey")
            rtype = m_rel.group("type")
            sid = str(params.get(akey, ""))
            tid = str(params.get(bkey, ""))
            props = dict(params.get("props", {})) if isinstance(params.get("props"), Mapping) else {}
            if not sid or not tid:
                return
            # Ensure endpoints exist (mirror Cypher MATCH semantics loosely: if not found, nothing happens)
            if sid not in self._nodes or tid not in self._nodes:
                return
            self._merge_relationship(sid, rtype, tid, props)
            return

        # Other DDL or unknown — ignore.

    def _merge_node(self, orig_id: str, labels: Iterable[str], props: Mapping[str, object]) -> None:
        node = self._nodes.get(orig_id)
        if not node:
            node = _Node(orig_id=orig_id, labels=set(labels), properties={})
            self._nodes[orig_id] = node
        else:
            node.labels.update(labels)
        # MERGE + SET n += props
        for k, v in props.items():
            node.properties[k] = v
        # Ensure orig_id property is set as well
        node.properties.setdefault("orig_id", orig_id)

    def _merge_relationship(self, start: str, rtype: str, end: str, props: Mapping[str, object]) -> None:
        key = (start, rtype, end)
        rel = self._rels.get(key)
        if not rel:
            rel = _Rel(type=rtype, start=start, end=end, properties={})
            self._rels[key] = rel
        for k, v in props.items():
            rel.properties[k] = v

    def _delete_node(self, orig_id: str) -> None:
        self._nodes.pop(orig_id, None)
        # remove attached relationships
        to_del = [k for k in self._rels.keys() if k[0] == orig_id or k[2] == orig_id]
        for k in to_del:
            self._rels.pop(k, None)

    # Convenience, in case any caller expects a `.query` alias
    def query(self, cypher: str, params: Optional[Mapping[str, object]] = None) -> Iterable[Mapping[str, object]]:
        return self.execute_and_fetch(cypher, params=params)

    # Convenience helpers for tests that seed the fake adapter
    def seed_graph(self, nodes: Iterable[Mapping[str, object]], rels: Iterable[Mapping[str, object]]) -> None:
        # Clear existing state
        self._nodes.clear()
        self._rels.clear()
        # Add nodes
        for n in nodes:
            oid = str(n.get("orig_id") or n.get("id") or "")
            labels = set(l for l in (n.get("labels") or []))
            props = dict(n.get("properties") or {})
            if oid:
                self._merge_node(oid, labels, props)
        # Add relationships
        for r in rels:
            start = str(r.get("start") or "")
            end = str(r.get("end") or "")
            rtype = str(r.get("type") or r.get("label") or "")
            props = dict(r.get("properties") or {})
            if start and end and rtype:
                if start not in self._nodes:
                    self._merge_node(start, set(), {})
                if end not in self._nodes:
                    self._merge_node(end, set(), {})
                self._merge_relationship(start, rtype, end, props)

    # alias expected by some test helpers
    def set_graph(self, nodes: Iterable[Mapping[str, object]], rels: Iterable[Mapping[str, object]]) -> None:
        return self.seed_graph(nodes, rels)

    def reset_with(self, nodes: Iterable[Mapping[str, object]], rels: Iterable[Mapping[str, object]]) -> None:
        return self.seed_graph(nodes, rels)

    def reset(self) -> None:
        self._nodes.clear()
        self._rels.clear()

    def clear(self) -> None:
        self.reset()

    def add_node(
        self, orig_id: str, labels: Iterable[str] | None = None, properties: Mapping[str, object] | None = None
    ) -> None:
        self._merge_node(orig_id, set(labels or []), dict(properties or {}))

    def create_node(
        self, orig_id: str, labels: Iterable[str] | None = None, properties: Mapping[str, object] | None = None
    ) -> None:
        return self.add_node(orig_id, labels, properties)

    def add_relationship(self, type: str, start: str, end: str, properties: Mapping[str, object] | None = None) -> None:
        if start not in self._nodes:
            self._merge_node(start, set(), {})
        if end not in self._nodes:
            self._merge_node(end, set(), {})
        self._merge_relationship(start, type, end, dict(properties or {}))

    def add_rel(self, type: str, start: str, end: str, properties: Mapping[str, object] | None = None) -> None:
        return self.add_relationship(type, start, end, properties)


# Backwards-compatible alias expected by some tests
FakeMemgraph = FakeMemgraphAdapter

# Minimal sample graph factory for tests that expect `sample_graph()`
try:
    from tests.fixtures.sample_data import SAMPLE_RELS
except Exception:
    SAMPLE_RELS = []


def sample_graph() -> dict:
    return {
        "nodes": [{"orig_id": "u1"}, {"orig_id": "u2"}, {"orig_id": "c1"}],
        "relationships": SAMPLE_RELS,
    }


# Add a small compatibility helper so tests using Path.utime() work across Python versions
# pathlib.Path in older runtimes may not expose utime, so provide a helper function used by tests.
try:
    Path.utime
except Exception:

    def _path_utime(p: Path, times):
        import os

        os.utime(str(p), times)

    Path.utime = _path_utime
