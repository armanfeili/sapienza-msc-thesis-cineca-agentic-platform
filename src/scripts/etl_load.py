#!/usr/bin/env python3
"""
Cineca Agentic Platform — ETL Loader

Loads data into Memgraph (or Neo4j-compatible) via Bolt.

Two main modes:
  1) Synthetic generation (Faker) based on the project's schema.
  2) Load from JSON/JSONL files containing nodes/relationships.

Schema (synthetic mode):
  User ──[:WORKS_AT]──► Institution
  User ──[:RUNS]──────► <Task>            (SearchbyTaxon | Bold | Command | Blast | BlastSeq | CreateDb)
  <Task> ←[:INPUT]───── {Fasta | File | BlastDb}
  <Task> ─[:OUTPUT]───► {File | BlastedSeq | Fasta | Xml | BlastDb}

Usage:
  python -m src.scripts.etl_load \
    --mode synthetic \
    --bolt "bolt://localhost:7687" \
    --user "" --password "" \
    --drop --create-indexes \
    --institutions 50 --users 200 --tasks-per-user 0:10 \
    --seed 42

  python -m src.scripts.etl_load \
    --mode files \
    --bolt "bolt://localhost:7687" \
    --nodes /path/to/nodes.jsonl \
    --rels  /path/to/rels.jsonl

Environment:
  MEMGRAPH_BOLT_URL, MEMGRAPH_USER, MEMGRAPH_PASSWORD can be used as defaults.

Notes:
  - Requires the `neo4j` Python driver (works with Memgraph via Bolt).
  - Safe to run multiple times with MERGE-heavy upserts.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# Optional project settings (fallback to env/args if missing)
DEFAULT_BOLT = os.getenv("MEMGRAPH_BOLT_URL", "bolt://localhost:7687")
DEFAULT_USER = os.getenv("MEMGRAPH_USER", "")
DEFAULT_PASSWORD = os.getenv("MEMGRAPH_PASSWORD", "")

try:
    # Prefer project config if available
    from src.config import settings as _settings  # type: ignore

    DEFAULT_BOLT = getattr(_settings, "MEMGRAPH_BOLT_URL", DEFAULT_BOLT)
    DEFAULT_USER = getattr(_settings, "MEMGRAPH_USER", DEFAULT_USER)
    DEFAULT_PASSWORD = getattr(_settings, "MEMGRAPH_PASSWORD", DEFAULT_PASSWORD)
except Exception:
    pass

# External deps
try:
    from neo4j import Driver, GraphDatabase
except Exception:  # pragma: no cover
    print("ERROR: neo4j Python driver is required. Install via `pip install neo4j`.", file=sys.stderr)
    raise


# ------------------------------ Data Models (Synthetic) ------------------------------


TASK_TYPES = ("SearchbyTaxon", "Bold", "Command", "Blast", "BlastSeq", "CreateDb")
FILE_TYPES_INPUT = ("Fasta", "File", "BlastDb")
FILE_TYPES_OUTPUT = ("File", "BlastedSeq", "Fasta", "Xml", "BlastDb")


@dataclass(frozen=True)
class Institution:
    name: str
    props: dict[str, Any]


@dataclass(frozen=True)
class User:
    user_id: str
    user_name: str
    firstName: str
    lastName: str
    email: str
    institution: str
    props: dict[str, Any]


@dataclass(frozen=True)
class Task:
    task_id: str
    task_type: str
    user_id: str
    status: str
    start: str  # ISO 8601
    tags: list[str]
    props: dict[str, Any]


@dataclass(frozen=True)
class FileNode:
    file_id: str
    file_type: str  # label such as File, Fasta, Xml, BlastDb, BlastedSeq
    user_filename: str
    extension: str
    size: int
    bucket_name: str
    etag: str
    uploaded: bool
    date: str  # ISO 8601
    props: dict[str, Any]


@dataclass(frozen=True)
class Link:
    kind: str  # INPUT or OUTPUT
    task_id: str
    file_id: str


# ------------------------------ Helpers ------------------------------


def batch(iterable: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    n = max(1, int(size))
    for i in range(0, len(iterable), n):
        yield iterable[i : i + n]


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ------------------------------ Synthetic Data Generator ------------------------------


def random_props(rng: random.Random, count: int = 4) -> dict[str, Any]:
    """Small random properties payload (non-PII)."""
    words = [
        "alpha",
        "beta",
        "gamma",
        "delta",
        "epsilon",
        "zeta",
        "theta",
        "kappa",
        "lambda",
        "omega",
    ]
    d: dict[str, Any] = {}
    for i in range(count):
        key = f"extra{i+1}"
        choice = rng.choice(
            [
                rng.randint(1, 10_000),
                round(rng.random(), 5),
                rng.choice(words),
                bool(rng.randint(0, 1)),
            ]
        )
        d[key] = choice
    return d


def generate_synthetic(
    *,
    institutions_count: int = 50,
    users_count: int = 200,
    tasks_per_user_range: tuple[int, int] = (0, 10),
    rng: random.Random | None = None,
) -> tuple[list[Institution], list[User], list[Task], list[FileNode], list[Link]]:
    """Generate synthetic entities matching the documented schema."""
    rng = rng or random.Random()

    institutions: list[Institution] = []
    for _ in range(institutions_count):
        name = f"Institution {rng.randint(1, 9999)}-{rng.choice(['A','B','C','D'])}"
        institutions.append(
            Institution(
                name=name,
                props=random_props(rng),
            )
        )

    users: list[User] = []
    for i in range(users_count):
        first = f"User{i}"
        last = rng.choice(["Smith", "Garcia", "Lee", "Khan", "Rossi", "Kowalski", "Nguyen", "Kim"])
        uname = f"{first.lower()}.{last.lower()}"
        email = f"{uname}@example.org"
        inst = rng.choice(institutions).name
        users.append(
            User(
                user_id=str(uuid.uuid4()),
                user_name=uname,
                firstName=first,
                lastName=last,
                email=email,
                institution=inst,
                props=random_props(rng),
            )
        )

    tasks: list[Task] = []
    files: list[FileNode] = []
    links: list[Link] = []

    for u in users:
        n_tasks = rng.randint(tasks_per_user_range[0], tasks_per_user_range[1])
        for _ in range(n_tasks):
            ttype = rng.choice(TASK_TYPES)
            tid = str(uuid.uuid4())
            status = rng.choice(["queued", "running", "succeeded", "failed"])
            tags = rng.sample(["fast", "dev", "high-priority", "retry", "batch", "adhoc"], rng.randint(0, 3))
            # Type-specific props:
            tprops = random_props(rng)
            if ttype in ("Blast", "BlastSeq"):
                tprops.update(
                    {
                        "blasttype": rng.choice(["blastn", "blastp", "blastx"]),
                        "blast_version": rng.choice(["2.13.0", "2.14.1", "2.15.0"]),
                        "dbname": rng.choice(["nt", "nr", "swissprot"]),
                        "output_csv": rng.choice([True, False]),
                        "output_result": rng.choice([True, False]),
                    }
                )
            elif ttype == "CreateDb":
                tprops.update({"dbtype": rng.choice(["protein", "nucleotide"]), "dbname": f"db_{rng.randint(100,999)}"})
            elif ttype in ("SearchbyTaxon", "Bold"):
                tprops.update(
                    {
                        "tool": ttype.lower(),
                        "taxon": rng.choice(
                            ["Homo sapiens", "Escherichia coli", "Pan troglodytes", "Arabidopsis thaliana"]
                        ),
                        "output_fasta": rng.choice([True, False]),
                        "output_result": rng.choice([True, False]),
                    }
                )

            tasks.append(
                Task(
                    task_id=tid,
                    task_type=ttype,
                    user_id=u.user_id,
                    status=status,
                    start=now_iso(),
                    tags=tags,
                    props=tprops,
                )
            )

            # Inputs (File -> Task)
            for _in in range(rng.randint(0, 3)):
                ftype = rng.choice(FILE_TYPES_INPUT)
                fid = str(uuid.uuid4())
                fprops = random_props(rng)
                fnode = FileNode(
                    file_id=fid,
                    file_type=ftype,
                    user_filename=f"{u.user_name}-{ftype.lower()}-{fid[:8]}.{rng.choice(['fa','fasta','txt','db'])}",
                    extension=rng.choice(["fa", "fasta", "txt", "db", "gz", "xml"]),
                    size=rng.randint(100, 10_000_000),
                    bucket_name=rng.choice(["uploads", "results", "tmp"]),
                    etag=str(uuid.uuid4()),
                    uploaded=bool(rng.randint(0, 1)),
                    date=now_iso(),
                    props=fprops,
                )
                files.append(fnode)
                links.append(Link(kind="INPUT", task_id=tid, file_id=fid))

            # Outputs (Task -> File)
            for _out in range(rng.randint(1, 3)):
                ftype = rng.choice(FILE_TYPES_OUTPUT)
                fid = str(uuid.uuid4())
                fprops = random_props(rng)
                fnode = FileNode(
                    file_id=fid,
                    file_type=ftype,
                    user_filename=f"{u.user_name}-{ftype.lower()}-{fid[:8]}.{rng.choice(['fa','fasta','txt','db','xml'])}",
                    extension=rng.choice(["fa", "fasta", "txt", "db", "xml", "csv"]),
                    size=rng.randint(100, 10_000_000),
                    bucket_name=rng.choice(["uploads", "results", "tmp"]),
                    etag=str(uuid.uuid4()),
                    uploaded=True,
                    date=now_iso(),
                    props=fprops,
                )
                files.append(fnode)
                links.append(Link(kind="OUTPUT", task_id=tid, file_id=fid))

    # De-duplicate files by id (defensive; generation already unique)
    by_id: dict[str, FileNode] = {f.file_id: f for f in files}
    files = list(by_id.values())
    return institutions, users, tasks, files, links


# ------------------------------ DB Layer ------------------------------


class DB:
    """Thin wrapper around neo4j.Driver for convenience."""

    def __init__(self, bolt: str, user: str, password: str) -> None:
        self._driver: Driver = GraphDatabase.driver(bolt, auth=(user or None, password or None))

    def close(self) -> None:
        self._driver.close()

    def run(self, cypher: str, parameters: dict[str, Any] | None = None) -> None:
        with self._driver.session() as session:
            session.execute_write(lambda tx: tx.run(cypher, parameters or {}).consume())

    def run_fetch(self, cypher: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        with self._driver.session() as session:
            result = session.execute_read(lambda tx: list(tx.run(cypher, parameters or {})))
        return [r.data() for r in result]


# ------------------------------ Cypher Loaders ------------------------------


def drop_all(db: DB) -> None:
    # Memgraph supports DROP GRAPH; for compatibility use detach delete.
    db.run("MATCH ()-[r]-() DELETE r;")
    db.run("MATCH (n) DELETE n;")


def create_indexes(db: DB) -> None:
    stmts = [
        "CREATE INDEX IF NOT EXISTS ON :User(user_id);",
        "CREATE INDEX IF NOT EXISTS ON :User(user_name);",
        "CREATE INDEX IF NOT EXISTS ON :Institution(name);",
        "CREATE INDEX IF NOT EXISTS ON :Task(task_id);",
        "CREATE INDEX IF NOT EXISTS ON :File(file_id);",
    ]
    for s in stmts:
        try:
            db.run(s)
        except Exception:
            # Some Memgraph versions may not support IF NOT EXISTS; ignore errors
            pass


def load_institutions(db: DB, rows: Sequence[Institution], batch_size: int = 500) -> None:
    cypher = """
    UNWIND $rows AS row
    MERGE (i:Institution {name: row.name})
    SET i += row.props
    """
    for part in batch([asdict(r) for r in rows], batch_size):
        db.run(cypher, {"rows": part})


def load_users(db: DB, rows: Sequence[User], batch_size: int = 500) -> None:
    cypher = """
    UNWIND $rows AS row
    MERGE (u:User {user_id: row.user_id})
    SET u.user_name = row.user_name,
        u.firstName = row.firstName,
        u.lastName  = row.lastName,
        u.email     = row.email
    SET u += row.props
    WITH u, row
    MATCH (i:Institution {name: row.institution})
    MERGE (u)-[:WORKS_AT]->(i)
    """
    for part in batch([asdict(r) for r in rows], batch_size):
        db.run(cypher, {"rows": part})


def load_tasks(db: DB, rows: Sequence[Task], batch_size: int = 500) -> None:
    cypher = """
    UNWIND $rows AS row
    MERGE (t:Task {task_id: row.task_id})
    SET t.status = row.status,
        t.start  = row.start,
        t.tags   = row.tags
    SET t += row.props
    // also add a concrete type label
    WITH t, row
    CALL apoc.create.addLabels(t, [row.task_type]) YIELD node
    WITH node AS t, row
    MATCH (u:User {user_id: row.user_id})
    MERGE (u)-[:RUNS]->(t)
    """
    # If APOC isn't available on Memgraph, we fallback to dynamic label via CASE.
    # We'll try APOC first, if it fails we use a per-type MERGE.
    try:
        for part in batch([asdict(r) for r in rows], batch_size):
            db.run(cypher, {"rows": part})
        return
    except Exception:
        pass

    # Fallback: run by type without APOC
    for ttype in TASK_TYPES:
        filtered = [asdict(r) for r in rows if r.task_type == ttype]
        if not filtered:
            continue
        cy = f"""
        UNWIND $rows AS row
        MERGE (t:Task:{ttype} {{task_id: row.task_id}})
        SET t.status = row.status,
            t.start  = row.start,
            t.tags   = row.tags
        SET t += row.props
        WITH t, row
        MATCH (u:User {{user_id: row.user_id}})
        MERGE (u)-[:RUNS]->(t)
        """
        for part in batch(filtered, batch_size):
            db.run(cy, {"rows": part})


def load_files(db: DB, rows: Sequence[FileNode], batch_size: int = 500) -> None:
    # Try dynamic labels via APOC; fallback to static-per-type batches otherwise.
    cypher_apoc = """
    UNWIND $rows AS row
    MERGE (f:File {file_id: row.file_id})
    SET f.user_filename = row.user_filename,
        f.extension     = row.extension,
        f.size          = row.size,
        f.bucket_name   = row.bucket_name,
        f.etag          = row.etag,
        f.uploaded      = row.uploaded,
        f.date          = row.date
    SET f += row.props
    WITH f, row
    CALL apoc.create.addLabels(f, [row.file_type]) YIELD node
    RETURN count(node) AS cnt
    """
    try:
        for part in batch([asdict(r) for r in rows], batch_size):
            db.run(cypher_apoc, {"rows": part})
        return
    except Exception:
        pass

    for ftype in sorted({r.file_type for r in rows}):
        filtered = [asdict(r) for r in rows if r.file_type == ftype]
        cy = f"""
        UNWIND $rows AS row
        MERGE (f:File:{ftype} {{file_id: row.file_id}})
        SET f.user_filename = row.user_filename,
            f.extension     = row.extension,
            f.size          = row.size,
            f.bucket_name   = row.bucket_name,
            f.etag          = row.etag,
            f.uploaded      = row.uploaded,
            f.date          = row.date
        SET f += row.props
        """
        for part in batch(filtered, batch_size):
            db.run(cy, {"rows": part})


def load_links(db: DB, rows: Sequence[Link], batch_size: int = 1000) -> None:
    # INPUT: File -> Task
    cy_in = """
    UNWIND $rows AS row
    MATCH (f:File {file_id: row.file_id})
    MATCH (t:Task {task_id: row.task_id})
    MERGE (f)-[:INPUT]->(t)
    """
    # OUTPUT: Task -> File
    cy_out = """
    UNWIND $rows AS row
    MATCH (f:File {file_id: row.file_id})
    MATCH (t:Task {task_id: row.task_id})
    MERGE (t)-[:OUTPUT]->(f)
    """
    input_rows = [asdict(r) for r in rows if r.kind.upper() == "INPUT"]
    output_rows = [asdict(r) for r in rows if r.kind.upper() == "OUTPUT"]

    for part in batch(input_rows, batch_size):
        db.run(cy_in, {"rows": part})
    for part in batch(output_rows, batch_size):
        db.run(cy_out, {"rows": part})


# ------------------------------ File-based Loader ------------------------------


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def load_from_files(
    db: DB,
    *,
    nodes_path: Path | None,
    rels_path: Path | None,
    batch_size: int = 500,
) -> None:
    """
    Nodes file format (JSONL). Each line:
      {"labels": ["User"], "key": {"user_id": "..."}, "props": { ... }}

    Relationships file format (JSONL). Each line:
      {"type":"RUNS", "from":{"label":"User","key":{"user_id":"..."}}, "to":{"label":"Task","key":{"task_id":"..."}}, "props":{}}
    """
    if nodes_path and nodes_path.exists():
        nodes = load_jsonl(nodes_path)
        # Group by first label for upsert
        by_label: dict[str, list[dict[str, Any]]] = {}
        for n in nodes:
            label = (n.get("labels") or ["Node"])[0]
            by_label.setdefault(label, []).append(n)

        for label, rows in by_label.items():
            # derive key field name and values
            keys = [list(r.get("key", {}).keys()) for r in rows]
            # ensure single-key, consistent (for simplicity)
            key_name = None
            for k in keys:
                if not k:
                    continue
                key_name = k[0]
                break
            if not key_name:
                # fallback generic id
                key_name = "id"

            cy = f"""
            UNWIND $rows AS row
            MERGE (n:{label} {{{key_name}: row.key.{key_name}}})
            SET n += row.props
            """
            for part in batch(rows, batch_size):
                db.run(cy, {"rows": part})

    if rels_path and rels_path.exists():
        rels = load_jsonl(rels_path)
        by_type: dict[str, list[dict[str, Any]]] = {}
        for r in rels:
            rtype = r.get("type", "REL")
            by_type.setdefault(rtype, []).append(r)

        for rtype, rows in by_type.items():
            # Assume single key in from/to
            def pick(label_key: dict[str, Any]) -> tuple[str, str]:
                label = label_key.get("label", "Node")
                key_dict = label_key.get("key", {})
                if not key_dict:
                    return label, "id"
                return label, next(iter(key_dict.keys()))

            flabel, fkey = pick(rows[0]["from"])
            tlabel, tkey = pick(rows[0]["to"])

            cy = f"""
            UNWIND $rows AS row
            MATCH (a:{flabel} {{{fkey}: row.from.key.{fkey}}})
            MATCH (b:{tlabel} {{{tkey}: row.to.key.{tkey}}})
            MERGE (a)-[r:{rtype}]->(b)
            SET r += coalesce(row.props, {{}})
            """
            for part in batch(rows, batch_size):
                db.run(cy, {"rows": part})


# ------------------------------ CLI ------------------------------


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ETL loader for Memgraph-compatible databases.")
    p.add_argument("--mode", choices=["synthetic", "files"], default="synthetic", help="Load mode")
    p.add_argument("--bolt", default=DEFAULT_BOLT, help="Bolt URL (e.g., bolt://localhost:7687)")
    p.add_argument("--user", default=DEFAULT_USER, help="DB user (empty for none)")
    p.add_argument("--password", default=DEFAULT_PASSWORD, help="DB password (empty for none)")
    p.add_argument("--drop", action="store_true", help="Drop all nodes/relationships before load")
    p.add_argument("--create-indexes", action="store_true", help="Create recommended indexes")

    # Synthetic controls
    p.add_argument("--institutions", type=int, default=50, help="Number of institutions (synthetic)")
    p.add_argument("--users", type=int, default=200, help="Number of users (synthetic)")
    p.add_argument(
        "--tasks-per-user",
        type=str,
        default="0:10",
        help="Tasks per user as MIN:MAX (inclusive)",
    )
    p.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")

    # Files mode
    p.add_argument("--nodes", type=Path, default=None, help="Path to nodes JSONL")
    p.add_argument("--rels", type=Path, default=None, help="Path to relationships JSONL")

    # Perf
    p.add_argument("--batch-size", type=int, default=500, help="Batch size for writes")

    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    print(f"[etl] Connecting to {args.bolt} ...", file=sys.stderr)
    db = DB(args.bolt, args.user, args.password)
    try:
        if args.drop:
            print("[etl] Dropping all nodes and relationships ...", file=sys.stderr)
            drop_all(db)

        if args.create_indexes:
            print("[etl] Creating indexes ...", file=sys.stderr)
            create_indexes(db)

        if args.mode == "synthetic":
            rng = random.Random(args.seed)
            a, b = 0, 10
            try:
                parts = [int(x) for x in str(args.tasks_per_user).split(":")]
                if len(parts) == 2:
                    a, b = parts[0], parts[1]
            except Exception:
                pass

            print(
                f"[etl] Generating synthetic data: institutions={args.institutions} users={args.users} tasks/user={a}:{b} seed={args.seed}",
                file=sys.stderr,
            )
            insts, users, tasks, files, links = generate_synthetic(
                institutions_count=args.institutions,
                users_count=args.users,
                tasks_per_user_range=(a, b),
                rng=rng,
            )

            t0 = time.time()
            load_institutions(db, insts, args.batch_size)
            load_users(db, users, args.batch_size)
            load_tasks(db, tasks, args.batch_size)
            load_files(db, files, args.batch_size)
            load_links(db, links, args.batch_size)
            dt = time.time() - t0

            print(
                json.dumps(
                    {
                        "mode": "synthetic",
                        "counts": {
                            "institutions": len(insts),
                            "users": len(users),
                            "tasks": len(tasks),
                            "files": len(files),
                            "links": len(links),
                        },
                        "elapsed_sec": round(dt, 3),
                    },
                    indent=2,
                )
            )
        else:
            print("[etl] Loading from files ...", file=sys.stderr)
            load_from_files(db, nodes_path=args.nodes, rels_path=args.rels, batch_size=args.batch_size)
            print(
                json.dumps(
                    {
                        "mode": "files",
                        "nodes": str(args.nodes) if args.nodes else None,
                        "relationships": str(args.rels) if args.rels else None,
                        "status": "ok",
                    },
                    indent=2,
                )
            )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
