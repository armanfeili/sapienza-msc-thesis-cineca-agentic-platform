# db/create_original_db.py
"""
Create the *original* graph in Memgraph from the three reference files
under db/original-dataset/ :

* export.csv          – schema summary (we read it for index hints)
* node_examples.json  – actual data (nodes & relationships)
* records.json        – unused here (larger schema snapshot)

Run this inside the `db-populate` container started by docker-compose,
or directly on the host if Memgraph is reachable on $MG_HOST:$MG_PORT.
"""

from __future__ import annotations

import contextlib
import csv
import json
from pathlib import Path
from typing import Any

import mgclient
from db.config import settings

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).parent / "original-dataset"
NODES_FILE = DATA_DIR / "node_examples.json"
EXPORT_CSV = DATA_DIR / "export.csv"

MG_HOST = settings.MG_HOST
MG_PORT = settings.MG_PORT
MG_USER = settings.MG_USER
MG_PASSWORD = settings.MG_PASSWORD


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def load_jsonl(path: Path) -> tuple[list[dict], list[dict]]:
    """Return two lists: (nodes, relationships) parsed from a JSON-Lines file."""
    nodes: list[dict] = []
    relationships: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec["type"] == "node":
                nodes.append(rec)
            elif rec["type"] == "relationship":
                relationships.append(rec)
    return nodes, relationships


def load_index_hints(path: Path) -> list[tuple[str, str]]:
    """Read export.csv and return [(label, property)] where index == true."""
    hints: list[tuple[str, str]] = []
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("type") != "node":  # ignore relationship rows
                continue
            if row.get("index", "").lower() != "true":
                continue
            label = row["label"].strip(' "')
            prop = row["property"].strip(' "')
            hints.append((label, prop))
    return hints


def connect() -> mgclient.Connection:
    """Open a Memgraph connection; include auth only if env-vars are set."""
    kwargs: dict[str, Any] = {"host": MG_HOST, "port": MG_PORT}
    if MG_USER:
        kwargs["username"] = MG_USER
    if MG_PASSWORD:
        kwargs["password"] = MG_PASSWORD
    return mgclient.connect(**kwargs)


def ensure_index(cur, label: str, prop: str) -> None:
    """Attempt to create an index; ignore 'already exists' errors."""
    with contextlib.suppress(mgclient.DatabaseError):
        cur.execute(f"CREATE INDEX ON :`{label}`(`{prop}`)")


def create_all_indexes(cur, nodes: list[dict], index_hints: list[tuple[str, str]]) -> None:
    """Create orig_id indexes + any extra indexes advertised in export.csv."""
    # Index on orig_id for every label present in the sample data
    seen_labels: set[str] = set()
    for n in nodes:
        for lbl in n["labels"]:
            if lbl not in seen_labels:
                seen_labels.add(lbl)
                ensure_index(cur, lbl, "orig_id")

    # Extra indexes from export.csv
    for lbl, prop in index_hints:
        ensure_index(cur, lbl, prop)


def import_nodes(cur, nodes: list[dict]) -> None:
    """MERGE all nodes."""
    for n in nodes:
        labels = ":".join(f"`{l}`" for l in n["labels"])
        props: dict[str, Any] = n["properties"] or {}
        props["orig_id"] = n["id"]
        query = f"MERGE (n:{labels} {{orig_id:$orig_id}}) " f"SET n += $props"
        cur.execute(query, {"orig_id": n["id"], "props": props})


def import_relationships(cur, relationships: list[dict]) -> None:
    """MERGE all relationships."""
    for r in relationships:
        label = f"`{r['label']}`"
        start_id = r["start"]["id"]
        end_id = r["end"]["id"]
        props = r.get("properties", {})
        query = (
            f"MATCH (a {{orig_id:$start}}), (b {{orig_id:$end}}) " f"MERGE (a)-[rel:{label}]->(b) " f"SET rel += $props"
        )
        cur.execute(query, {"start": start_id, "end": end_id, "props": props})


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    nodes, relationships = load_jsonl(NODES_FILE)
    index_hints = load_index_hints(EXPORT_CSV)

    print(f"Nodes: {len(nodes):>3} | Relationships: {len(relationships):>3}")
    print(f"Index hints from export.csv: {len(index_hints)}")

    conn = connect()
    try:
        cur = conn.cursor()
        try:
            conn.autocommit = False

            # Drop existing data (comment out if you prefer to append)
            cur.execute("MATCH (n) DETACH DELETE n")

            create_all_indexes(cur, nodes, index_hints)
            import_nodes(cur, nodes)
            import_relationships(cur, relationships)

            conn.commit()
            print("✔  Original dataset loaded into Memgraph")
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
    finally:
        conn.close()


# if __name__ == "__main__":
#     main()
