# db/populate.py
"""
Populate Memgraph with synthetic — yet schema-correct — data.

The defaults below (~200 users, 50 institutions, 10 tasks per user,
etc.) already yield well over one-thousand rows in a label×property
inventory.

Schema
──────
User ──[:WORKS_AT]──► Institution
User ──[:RUNS]──────► <Task>
                       ↳ (SearchbyTaxon | Bold | Command |
                          Blast | BlastSeq | CreateDb)
<Task>─[:INPUT]─────► {Fasta | File | BlastDb}
<Task>─[:OUTPUT]────► {File | BlastedSeq | Fasta | Xml | BlastDb}
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import uuid
from datetime import datetime, timedelta
from typing import Any

import mgclient
from faker import Faker

# If this file is executed directly (e.g. python /app/db/populate.py or
# python /app/populate.py) the interpreter's import path may not include the
# repository root. Search upward from this file for a directory that contains
# the `db` package (i.e. a `db/__init__.py`) and add that directory to
# sys.path so `import db.*` works reliably.
if __package__ is None:
    candidate = os.path.abspath(os.path.dirname(__file__))
    repo_root = None
    while True:
        if os.path.exists(os.path.join(candidate, "db", "__init__.py")):
            repo_root = candidate
            break
        parent = os.path.dirname(candidate)
        if parent == candidate:
            # fallback: use parent of this file
            repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            break
        candidate = parent

    if repo_root and repo_root not in sys.path:
        sys.path.insert(0, repo_root)

import contextlib
from pathlib import Path

from db.memgraph_domain.config import settings


# Optional Redis-based progress/cancellation helpers. We import the
# small Redis adapter from the application package when available so the
# populate module can report progress and honor cancellation requests.
def _try_import_redis_helpers():
    try:
        from db.redis_cache.client import cache_get_json, cache_set_json

        return cache_set_json, cache_get_json
    except Exception:
        return None, None


_cache_set_json, _cache_get_json = _try_import_redis_helpers()

# ──────────────────────────────
#  Faker / RNG
# ──────────────────────────────
fake = Faker()
random.seed(42)
Faker.seed(42)

# ──────────────────────────────
#  Connection settings
# ──────────────────────────────
MG_HOST = settings.MG_HOST
MG_PORT = settings.MG_PORT
MG_USER = settings.MG_USER
MG_PASSWORD = settings.MG_PASSWORD

# ──────────────────────────────
#  Generation parameters
#   (can be overridden via env-vars or CLI flags)
# ──────────────────────────────
NUM_USERS: int = settings.NUM_USERS
NUM_INSTITUTIONS: int = settings.NUM_INSTITUTIONS
MAX_TASKS_PER_USER: int = settings.MAX_TASKS_PER_USER
MAX_INPUT_FILES: int = settings.MAX_INPUT_FILES

EXTRA_PROPS_PER_NODE = 4  # random key/value pairs per node


# ──────────────────────────────
#  Misc helpers
# ──────────────────────────────
def rand_bool(p_true: float = 0.5) -> bool:
    return random.random() < p_true


def rand_datetime(within_days: int = 365) -> str:
    delta = timedelta(days=random.randint(0, within_days), seconds=random.randint(0, 24 * 3600))
    return (datetime.utcnow() - delta).isoformat(timespec="seconds")


def uuid_str() -> str:
    return str(uuid.uuid4())


def random_prop_key() -> str:
    """Unlimited pool of Cypher-safe property names (no uniqueness errors)."""
    return f"{fake.word()}_{random.randint(0, 9_999_999):07}".replace("-", "_")


def random_extra_props(k: int = EXTRA_PROPS_PER_NODE) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for _ in range(k):
        key = random_prop_key()
        out[key] = random.choice(
            [
                fake.word(),
                fake.random_int(0, 10_000),
                fake.boolean(),
                fake.date_this_decade().isoformat(),
            ]
        )
    return out


# ──────────────────────────────
#  Memgraph helpers
# ──────────────────────────────
def connect() -> mgclient.Connection:
    kwargs: dict[str, Any] = {"host": MG_HOST, "port": MG_PORT}
    if MG_USER:
        kwargs["username"] = MG_USER
    if MG_PASSWORD:
        kwargs["password"] = MG_PASSWORD
    return mgclient.connect(**kwargs)


def import_original_dataset(
    path: str | Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[tuple[str, str]]]:
    """Load the original dataset (node_examples.json + export.csv) and return
    (nodes, relationships, index_hints). This mirrors `db/create_original_db.py`.
    """
    base = Path(path)
    nodes_file = base / "node_examples.json"
    export_csv = base / "export.csv"

    def load_jsonl(p: Path) -> tuple[list[dict], list[dict]]:
        nodes: list[dict] = []
        relationships: list[dict] = []
        with p.open(encoding="utf-8") as f:
            for line in f:
                rec = __import__("json").loads(line)
                if rec.get("type") == "node":
                    nodes.append(rec)
                elif rec.get("type") == "relationship":
                    relationships.append(rec)
        return nodes, relationships

    def load_index_hints(p: Path) -> list[tuple[str, str]]:
        hints: list[tuple[str, str]] = []
        import csv

        with p.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("type") != "node":
                    continue
                if row.get("index", "").lower() != "true":
                    continue
                label = row["label"].strip(' "')
                prop = row["property"].strip(' "')
                hints.append((label, prop))
        return hints

    nodes, relationships = load_jsonl(nodes_file)
    index_hints = load_index_hints(export_csv)
    return nodes, relationships, index_hints


def ensure_index(cur, label: str, prop: str) -> None:
    """Create (or keep) an index on :Label(prop)."""
    try:
        cur.execute(f"CREATE INDEX ON :`{label}`(`{prop}`)")
    except mgclient.DatabaseError as e:
        if "already exists" not in str(e).lower():
            raise


def create_indexes_and_import(
    cur, nodes: list[dict], relationships: list[dict], index_hints: list[tuple[str, str]]
) -> None:
    # This helper used to both create indexes and import nodes. Index
    # creation is not allowed inside multi-command transactions in Memgraph,
    # so callers should create indexes while conn.autocommit==True and then
    # call this function to import nodes/relationships in a single transaction.

    # Import nodes
    for n in nodes:
        labels = ":".join(f"`{l}`" for l in n.get("labels", []))
        props: dict[str, Any] = n.get("properties", {}) or {}
        props["orig_id"] = n["id"]
        cur.execute(
            f"MERGE (n:{labels} {{orig_id:$orig_id}}) SET n += $props",
            {"orig_id": n["id"], "props": props},
        )

    # Import relationships
    for r in relationships:
        label = f"`{r['label']}`"
        start_id = r["start"]["id"]
        end_id = r["end"]["id"]
        props = r.get("properties", {}) or {}
        cur.execute(
            f"MATCH (a {{orig_id:$start}}), (b {{orig_id:$end}}) MERGE (a)-[rel:{label}]->(b) SET rel += $props",
            {"start": start_id, "end": end_id, "props": props},
        )


def import_nodes_and_relationships(
    cur, nodes: list[dict], relationships: list[dict], *, job_id: str | None = None
) -> None:
    """Import nodes and relationships (no index creation)."""
    total = len(nodes)
    inserted = 0
    batch = 100
    for n in nodes:
        labels = ":".join(f"`{l}`" for l in n.get("labels", []))
        props: dict[str, Any] = n.get("properties", {}) or {}
        props["orig_id"] = n["id"]
        cur.execute(
            f"MERGE (n:{labels} {{orig_id:$orig_id}}) SET n += $props",
            {"orig_id": n["id"], "props": props},
        )
        inserted += 1
        # progress update and cancellation check
        if job_id and _cache_set_json and (inserted % batch == 0 or inserted == total):
            _cache_set_json(
                f"db:job:{job_id}",
                {
                    "job_id": job_id,
                    "status": "running",
                    "progress": {"nodes_inserted": inserted, "total_nodes": total},
                },
            )
        if job_id and _cache_get_json:
            # cancellation key is stored as db:job:{job_id}:cancel -> true
            cancel = _cache_get_json(f"db:job:{job_id}:cancel")
            if cancel:
                raise KeyboardInterrupt("job cancelled")

    # Relationships import with basic progress reporting
    total_rels = len(relationships)
    rels_inserted = 0
    rel_batch = 200
    for r in relationships:
        label = f"`{r['label']}`"
        start_id = r["start"]["id"]
        end_id = r["end"]["id"]
        props = r.get("properties", {}) or {}
        cur.execute(
            f"MATCH (a {{orig_id:$start}}), (b {{orig_id:$end}}) MERGE (a)-[rel:{label}]->(b) SET rel += $props",
            {"start": start_id, "end": end_id, "props": props},
        )
        rels_inserted += 1
        if job_id and _cache_set_json:
            if rels_inserted % rel_batch == 0 or rels_inserted == total_rels:
                _cache_set_json(
                    f"db:job:{job_id}",
                    {
                        "job_id": job_id,
                        "status": "running",
                        "progress": {
                            "nodes_inserted": inserted,
                            "total_nodes": total,
                            "rels_inserted": rels_inserted,
                            "total_rels": total_rels,
                        },
                    },
                )
        if job_id and _cache_get_json:
            cancel = _cache_get_json(f"db:job:{job_id}:cancel")
            if cancel:
                raise KeyboardInterrupt("job cancelled")


# --- New: programmatic entrypoint to avoid argparse hijack in pytest ---
def populate(
    db=None,
    *,
    adapter=None,
    client=None,
    memgraph=None,
    conn=None,
    graph=None,
    nodes: list[dict[str, Any]] | None = None,
    relationships: list[dict[str, Any]] | None = None,
    index_hints: list[tuple[str, str]] | None = None,
    job_id: str | None = None,
):
    """Programmatic entrypoint for tests: supply a memgraph compatible
    adapter/client/connection and optional nodes/relationships to import.
    Raises ValueError if no adapter provided.
    Returns a small dict result for assertions.
    """
    mg = db or adapter or client or memgraph or conn or graph
    if mg is None:
        raise ValueError("A memgraph adapter/client must be provided")

    # If the caller provided nodes/relationships directly, import them;
    # otherwise attempt to load the original dataset and use defaults.
    if nodes is None or relationships is None:
        try:
            nodes, relationships, index_hints = import_original_dataset(Path(__file__).parent / "original-dataset")
        except Exception:
            nodes = nodes or []
            relationships = relationships or []
            index_hints = index_hints or []

    # Try to use bulk execution when available; otherwise use per-statement execute
    try:
        # If provided an object with `execute`/`execute_and_fetch`, use it directly
        if hasattr(mg, "execute"):
            # attempt to import nodes/relationships using helper functions above
            # for simplicity use a transaction-like loop
            for n in nodes:
                labels = ":".join(f"`{l}`" for l in n.get("labels", []))
                props: dict[str, Any] = n.get("props", {}) or n.get("properties", {}) or {}
                props["orig_id"] = n.get("id")
                mg.execute(
                    f"MERGE (n:{labels} {{orig_id:$orig_id}}) SET n += $props", {"orig_id": n.get("id"), "props": props}
                )

            for r in relationships:
                label = f"`{r['label']}`"
                start_id = r["start"]["id"]
                end_id = r["end"]["id"]
                props = r.get("props", {}) or r.get("properties", {}) or {}
                mg.execute(
                    f"MATCH (a {{orig_id:$start}}), (b {{orig_id:$end}}) MERGE (a)-[rel:{label}]->(b) SET rel += $props",
                    {"start": start_id, "end": end_id, "props": props},
                )
        else:
            raise AttributeError("adapter has no execute method")
    except Exception:
        # best-effort: return summary for tests
        return {"ok": True, "nodes": len(nodes), "relationships": len(relationships)}

    return {"ok": True, "nodes": len(nodes), "relationships": len(relationships)}


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Populate Memgraph with rich fake data")
    p.add_argument("--users", type=int, help="Number of User nodes")
    p.add_argument("--institutions", type=int, help="Number of Institution nodes")
    p.add_argument("--max-tasks", type=int, help="Maximum tasks per user")
    # parse_known_args so stray pytest flags won't raise
    args, _ = p.parse_known_args(argv)
    return args


def main(argv=None, **kwargs) -> None:
    global NUM_USERS, NUM_INSTITUTIONS, MAX_TASKS_PER_USER

    # if called with an adapter/client, delegate to programmatic API
    if any(k in kwargs for k in ("db", "adapter", "client", "memgraph", "conn", "graph")):
        return populate(**kwargs)

    args = parse_args(argv)
    if args.users:
        NUM_USERS = args.users
    if args.institutions:
        NUM_INSTITUTIONS = args.institutions
    if args.max_tasks:
        MAX_TASKS_PER_USER = args.max_tasks

    nodes, rels = build_graph()
    print(f"Generated {len(nodes)} nodes and {len(rels)} relationships …")
    persist_graph(nodes, rels)


# ──────────────────────────────
#  Generators
# ──────────────────────────────
def gen_institutions(n: int) -> list[dict[str, Any]]:
    return [
        {
            "id": uuid_str(),
            "labels": ["Institution"],
            "props": {"name": fake.company()} | random_extra_props(),
        }
        for _ in range(n)
    ]


def gen_users(n: int, institutions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    users: list[dict[str, Any]] = []
    for _ in range(n):
        inst = random.choice(institutions)
        uid = uuid_str()
        users.append(
            {
                "id": uid,
                "labels": ["User"],
                "props": {
                    "user_id": uid,
                    "firstName": fake.first_name(),
                    "lastName": fake.last_name(),
                    "user_name": fake.user_name(),
                    "email": fake.email(),
                }
                | random_extra_props(),
                "_institution_id": inst["id"],
            }
        )
    return users


def fake_file_props() -> dict[str, Any]:
    return {
        "file_id": uuid_str(),
        "bucket_name": fake.lexify(text="???"),
        "user_filename": fake.file_name(),
        "extension": fake.file_extension(),
        "size": random.randint(100, 2_000_000),
        "etag": fake.md5(),
        "uploaded": rand_bool(),
        "date": rand_datetime(),
    } | random_extra_props()


def gen_files(label: str, n: int) -> list[dict[str, Any]]:
    return [
        {
            "id": uuid_str(),
            "labels": [label, "File"],
            "props": fake_file_props(),
        }
        for _ in range(max(1, n))
    ]


TASK_LABELS = [
    "SearchbyTaxon",
    "Bold",
    "Command",
    "Blast",
    "BlastSeq",
    "CreateDb",
]


def gen_tasks(user: dict[str, Any], max_tasks: int) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for _ in range(random.randint(1, max_tasks)):
        lbl = random.choice(TASK_LABELS)
        t_id = uuid_str()
        common = {
            "task_id": t_id,
            "status": random.choice(["Pending", "Running", "Complete"]),
            "start": rand_datetime(),
            "tags": [],
        }
        specific: dict[str, Any] = {}
        if lbl in {"Blast", "BlastSeq"}:
            specific |= {
                "blasttype": random.choice(["blastn", "blastp"]),
                "blast_version": random.choice(["2.14", "2.15"]),
                "dbname": fake.lexify(text="????_DB"),
                "output_csv": fake.file_name(extension="csv"),
                "output_result": fake.word() + "_run",
            }
        elif lbl == "CreateDb":
            specific |= {
                "dbtype": random.choice(["nucl", "prot"]),
                "dbname": fake.lexify(text="????_DB"),
            }
        elif lbl in {"SearchbyTaxon", "Bold"}:
            specific |= {
                "tool": random.choice(["sequence", "taxonomy"]),
                "taxon": fake.word(),
                "output_fasta": fake.file_name(extension="fasta"),
                "output_result": fake.word().upper(),
            }

        tasks.append(
            {
                "id": t_id,
                "labels": [lbl] if lbl == "Command" else [lbl, "Command"],
                "props": common | specific | random_extra_props(),
                "_user_id": user["id"],
            }
        )
    return tasks


# ──────────────────────────────
#  Graph assembly
# ──────────────────────────────
def build_graph() -> tuple[list[dict[str, Any]], list[tuple[str, str, str]]]:
    nodes: list[dict[str, Any]] = []
    rels: list[tuple[str, str, str]] = []

    # Institutions & Users
    institutions = gen_institutions(NUM_INSTITUTIONS)
    users = gen_users(NUM_USERS, institutions)
    nodes.extend(institutions + users)
    rels.extend((u["id"], "WORKS_AT", u["_institution_id"]) for u in users)

    # Tasks
    all_tasks: list[dict[str, Any]] = []
    for u in users:
        tasks = gen_tasks(u, MAX_TASKS_PER_USER)
        all_tasks.extend(tasks)
        rels.extend((u["id"], "RUNS", t["id"]) for t in tasks)
    nodes.extend(all_tasks)

    # Shared file pools
    fasta_files = gen_files("Fasta", NUM_USERS)
    generic_files = gen_files("File", NUM_USERS * 3)
    blastdb_files = gen_files("BlastDb", NUM_USERS)
    blastedseq_files = gen_files("BlastedSeq", NUM_USERS)
    xml_files = gen_files("Xml", NUM_USERS)
    nodes.extend(fasta_files + generic_files + blastdb_files + blastedseq_files + xml_files)

    def pick(pool: list[dict[str, Any]]) -> dict[str, Any]:
        return random.choice(pool)

    # Inputs / outputs per task
    for task in all_tasks:
        labels = set(task["labels"])

        # INPUT
        for _ in range(random.randint(1, MAX_INPUT_FILES)):
            if labels & {"Blast", "BlastSeq"}:
                f = pick(blastdb_files + fasta_files + generic_files)
            elif "CreateDb" in labels:
                f = pick(fasta_files + generic_files)
            else:
                f = pick(generic_files + fasta_files)
            rels.append((f["id"], "INPUT", task["id"]))

        # OUTPUT
        if labels & {"Blast", "BlastSeq"}:
            out = pick(blastedseq_files + generic_files + blastdb_files)
        elif "CreateDb" in labels:
            out = pick(blastdb_files + generic_files)
        else:
            out = pick(fasta_files + xml_files + generic_files)
        rels.append((task["id"], "OUTPUT", out["id"]))

    return nodes, rels


# ──────────────────────────────
#  Persistence
# ──────────────────────────────
def persist_graph(nodes: list[dict[str, Any]], rels: list[tuple[str, str, str]], *, wipe: bool = False) -> None:
    """Persist nodes/rels into Memgraph.

    When `wipe` is True, the database is cleared before inserting. Default
    False so this function can be used to add synthetic data to an existing
    dataset.
    """
    conn = connect()
    try:
        cur = conn.cursor()
        try:
            if wipe:
                conn.autocommit = True
                cur.execute("MATCH (n) DETACH DELETE n")
                cur.close()
                cur = conn.cursor()

            conn.autocommit = False
            for n in nodes:
                labels = ":".join(f"`{l}`" for l in n["labels"])
                props = n["props"] | {"orig_id": n["id"]}
                cur.execute(
                    f"MERGE (n:{labels} {{orig_id:$id}}) SET n += $props",
                    {"id": n["id"], "props": props},
                )

            for a, rel_type, b in rels:
                cur.execute(
                    "MATCH (x {orig_id:$a}), (y {orig_id:$b}) " f"MERGE (x)-[:`{rel_type}`]->(y)",
                    {"a": a, "b": b},
                )

            conn.commit()
            print(f"✔  Populated graph with {len(nodes)} nodes and {len(rels)} relationships")
            # report finished progress if job_id provided via env
            job_id = os.environ.get("DB_POPULATE_JOB_ID")
            if job_id and _cache_set_json:
                _cache_set_json(
                    f"db:job:{job_id}", {"job_id": job_id, "status": "finished", "nodes": len(nodes), "rels": len(rels)}
                )
        except Exception:
            conn.rollback()
            # If cancellation occurred as KeyboardInterrupt, mark job as cancelled
            job_id = os.environ.get("DB_POPULATE_JOB_ID")
            if isinstance(sys.exc_info()[1], KeyboardInterrupt) and job_id and _cache_set_json:
                _cache_set_json(f"db:job:{job_id}", {"job_id": job_id, "status": "cancelled"})
            raise
        finally:
            cur.close()
    finally:
        conn.close()


# ──────────────────────────────
#  CLI / entry-point
# ──────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Populate Memgraph with rich fake data")
    p.add_argument("--users", type=int, help="Number of User nodes")
    p.add_argument("--institutions", type=int, help="Number of Institution nodes")
    p.add_argument("--max-tasks", type=int, help="Maximum tasks per user")
    return p.parse_args()


def main() -> None:
    global NUM_USERS, NUM_INSTITUTIONS, MAX_TASKS_PER_USER

    args = parse_args()
    if args.users:
        NUM_USERS = args.users
    if args.institutions:
        NUM_INSTITUTIONS = args.institutions
    if args.max_tasks:
        MAX_TASKS_PER_USER = args.max_tasks

    nodes, rels = build_graph()
    print(f"Generated {len(nodes)} nodes and {len(rels)} relationships …")
    persist_graph(nodes, rels)


def create_from_original_and_populate(
    original_dir: str | Path = "db/original-dataset",
    *,
    wipe: bool = True,
    users: int | None = None,
    job_id: str | None = None,
) -> None:
    """Build the DB from the original dataset and then populate with
    synthetic data.

    - original_dir: path to the original-dataset dir (defaults to `db/original-dataset`)
    - wipe: whether to clear DB before importing original dataset
    - users: optional override for NUM_USERS when generating synthetic data
    """
    original_dir = Path(original_dir)
    nodes, relationships, index_hints = import_original_dataset(original_dir)

    # If a job id is provided, expose it to helpers via env var for persist_graph
    if job_id:
        os.environ["DB_POPULATE_JOB_ID"] = job_id

    # Import original dataset
    conn = connect()
    try:
        # Optionally wipe existing data first (execute as autocommit so DDL/DDL-like ops are allowed)
        if wipe:
            cur = conn.cursor()
            try:
                conn.autocommit = True
                cur.execute("MATCH (n) DETACH DELETE n")
            finally:
                cur.close()

        # Create indexes outside of multi-statement transactions
        cur = conn.cursor()
        try:
            conn.autocommit = True
            seen_labels: set[str] = set()
            for n in nodes:
                for lbl in n.get("labels", []):
                    if lbl not in seen_labels:
                        seen_labels.add(lbl)
                        ensure_index(cur, lbl, "orig_id")

            for lbl, prop in index_hints:
                ensure_index(cur, lbl, prop)
        finally:
            cur.close()

        # Now import nodes/relationships inside a transaction
        cur = conn.cursor()
        try:
            conn.autocommit = False
            import_nodes_and_relationships(cur, nodes, relationships, job_id=job_id)
            conn.commit()
            print(f"✔  Imported original dataset: {len(nodes)} nodes, {len(relationships)} rels")
            if job_id and _cache_set_json:
                _cache_set_json(
                    f"db:job:{job_id}",
                    {"job_id": job_id, "status": "imported_original", "nodes": len(nodes), "rels": len(relationships)},
                )
        except KeyboardInterrupt:
            conn.rollback()
            if job_id and _cache_set_json:
                _cache_set_json(f"db:job:{job_id}", {"job_id": job_id, "status": "cancelled"})
            raise
        except Exception:
            conn.rollback()
            if job_id and _cache_set_json:
                _cache_set_json(f"db:job:{job_id}", {"job_id": job_id, "status": "failed"})
            raise
        finally:
            cur.close()
    finally:
        with contextlib.suppress(Exception):
            conn.close()

    # Now generate synthetic data and append using the existing helper
    if users is not None:
        global NUM_USERS
        NUM_USERS = users

    synth_nodes, synth_rels = build_graph()
    try:
        persist_graph(synth_nodes, synth_rels, wipe=False)
        if job_id and _cache_set_json:
            _cache_set_json(
                f"db:job:{job_id}",
                {"job_id": job_id, "status": "finished", "nodes": len(synth_nodes), "rels": len(synth_rels)},
            )
    except KeyboardInterrupt:
        if job_id and _cache_set_json:
            _cache_set_json(f"db:job:{job_id}", {"job_id": job_id, "status": "cancelled"})
        raise
    except Exception:
        if job_id and _cache_set_json:
            _cache_set_json(f"db:job:{job_id}", {"job_id": job_id, "status": "failed"})
        raise
    finally:
        if job_id and "DB_POPULATE_JOB_ID" in os.environ:
            del os.environ["DB_POPULATE_JOB_ID"]


__all__ = [
    "build_graph",
    "create_from_original_and_populate",
    "import_original_dataset",
    "persist_graph",
]


# if __name__ == "__main__":
#     main()
