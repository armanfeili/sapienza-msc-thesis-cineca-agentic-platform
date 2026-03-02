import asyncio
import gzip
import io
import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from src.services.archive import ArchiveService
from src.services.etl import ETLService
from tests.fixtures.fake_memgraph import FakeMemgraph


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
SAMPLE_NODES: List[Dict[str, Any]] = [
    {"orig_id": "u:1", "labels": ["User"], "properties": {"name": "Alice"}},
    {"orig_id": "u:2", "labels": ["User"], "properties": {"name": "Bob"}},
    {"orig_id": "c:1", "labels": ["Company"], "properties": {"name": "Acme"}},
]
SAMPLE_RELS: List[Dict[str, Any]] = [
    {"type": "KNOWS", "start": "u:1", "end": "u:2", "properties": {"since": 2021}},
    {"type": "WORKS_AT", "start": "u:1", "end": "c:1", "properties": {"role": "Eng"}},
]


def _seed_fake_graph(fake: FakeMemgraph, nodes: List[Dict[str, Any]], rels: List[Dict[str, Any]]) -> None:
    """
    Seed the fake graph adapter using whatever helpers it exposes.
    Falls back to setting well-known attributes if helpers are missing.
    """
    # Full-graph seeders
    for m in ("seed_graph", "set_graph", "reset_with"):
        if hasattr(fake, m):
            getattr(fake, m)(nodes, rels)
            return

    # Reset if available
    for m in ("reset", "clear"):
        if hasattr(fake, m):
            getattr(fake, m)()

    # Add nodes one by one
    if hasattr(fake, "add_node"):
        for n in nodes:
            getattr(fake, "add_node")(n.get("orig_id"), n.get("labels", []), dict(n.get("properties") or {}))
    elif hasattr(fake, "create_node"):
        for n in nodes:
            getattr(fake, "create_node")(n.get("orig_id"), n.get("labels", []), dict(n.get("properties") or {}))
    else:
        # Last-resort attribute set
        try:
            setattr(fake, "nodes", [dict(n) for n in nodes])
        except Exception:
            setattr(fake, "_nodes", [dict(n) for n in nodes])

    # Add relationships one by one
    if hasattr(fake, "add_relationship"):
        for r in rels:
            getattr(fake, "add_relationship")(
                r.get("type"), r.get("start"), r.get("end"), dict(r.get("properties") or {})
            )
    elif hasattr(fake, "add_rel"):
        for r in rels:
            getattr(fake, "add_rel")(r.get("type"), r.get("start"), r.get("end"), dict(r.get("properties") or {}))
    else:
        try:
            setattr(fake, "rels", [dict(r) for r in rels])
        except Exception:
            setattr(fake, "_rels", [dict(r) for r in rels])


async def _make_archive_service(tmp_path: Path, seed: bool = True) -> ArchiveService:
    """
    Create an ArchiveService bound to a fresh ETLService with FakeMemgraph.
    Optionally seed the fake DB with a small graph.
    """
    fake_db = FakeMemgraph()
    if seed:
        _seed_fake_graph(fake_db, SAMPLE_NODES, SAMPLE_RELS)
    etl = ETLService(db=fake_db)
    svc = ArchiveService(etl=etl, base_dir=tmp_path, gzip_snapshots=True, batch_size=2, snapshot_prefix="graph")
    await svc.start()
    return svc


def _open_snapshot(path: Path) -> Dict[str, Any]:
    if str(path).endswith(".gz"):
        with gzip.open(path, "rb") as f:
            data = f.read()
        return json.loads(data.decode("utf-8"))
    return json.loads(path.read_text("utf-8"))


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_snapshot_graph_creates_gz_and_lists_and_rotates(tmp_path: Path):
    svc = await _make_archive_service(tmp_path, seed=True)

    # Take a snapshot
    res = await svc.snapshot_graph(pretty=True)
    assert res.ok, res.error
    out_file = Path(res.data["file"])
    assert out_file.exists()
    assert out_file.suffixes[-2:] == [".json", ".gz"]  # .json.gz
    assert res.data["nodes"] == len(SAMPLE_NODES)
    assert res.data["relationships"] == len(SAMPLE_RELS)

    # Validate payload quickly
    payload = _open_snapshot(out_file)
    assert payload["node_count"] == len(SAMPLE_NODES)
    assert payload["relationship_count"] == len(SAMPLE_RELS)
    assert len(payload["nodes"]) == len(SAMPLE_NODES)
    assert len(payload["relationships"]) == len(SAMPLE_RELS)

    # List backups shows the file
    lst = await svc.list_backups()
    assert lst.ok
    files = [Path(e["file"]).name for e in lst.data]
    assert out_file.name in files

    # Create a couple of additional dummy snapshots to exercise rotation
    # Write small minimal valid snapshots that match the rotation pattern
    for i in range(2):
        p = tmp_path / f"graph-20990101-00000{i}.json.gz"
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
            gz.write(
                json.dumps(
                    {
                        "generated_at": "2099-01-01T00:00:0" + str(i),
                        "node_count": 0,
                        "relationship_count": 0,
                        "nodes": [],
                        "relationships": [],
                    }
                ).encode("utf-8")
            )
        p.write_bytes(buf.getvalue())

    # Keep only the newest 1
    rot = await svc.rotate(retain=1)
    assert rot.ok
    assert rot.data["kept"] == 1
    assert rot.data["deleted"] >= 2

    await svc.stop()


@pytest.mark.asyncio
async def test_make_tar_gz_creates_archive(tmp_path: Path):
    svc = await _make_archive_service(tmp_path, seed=False)

    # Create a couple of files to include
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("hello", encoding="utf-8")
    b.write_text("world", encoding="utf-8")

    mk = await svc.make_tar_gz([a, b, tmp_path / "missing.txt"])
    assert mk.ok
    arch = Path(mk.data["file"])
    assert arch.exists()
    assert arch.suffixes[-2:] == [".tar", ".gz"]

    await svc.stop()


@pytest.mark.asyncio
async def test_restore_graph_round_trip_from_gz_snapshot(tmp_path: Path):
    # 1) Create a snapshot from a seeded graph
    svc_a = await _make_archive_service(tmp_path, seed=True)
    snap_res = await svc_a.snapshot_graph(pretty=False, gzip_output=True)
    assert snap_res.ok, snap_res.error
    snap_path = Path(snap_res.data["file"])
    await svc_a.stop()

    # 2) Restore into a fresh, empty FakeMemgraph via a new service
    svc_b = await _make_archive_service(tmp_path, seed=False)
    restore = await svc_b.restore_graph(snap_path)
    assert restore.ok, restore.error
    assert restore.data["nodes"] == len(SAMPLE_NODES)
    assert restore.data["relationships"] == len(SAMPLE_RELS)

    # Sanity: export from restored DB and confirm counts match
    # (This also exercises ETL snapshot_export on the restored DB)
    exp_path = tmp_path / "verify.json"
    etl_res = await svc_b.etl.snapshot_export(exp_path, pretty=False)
    assert etl_res.ok
    payload = json.loads(exp_path.read_text("utf-8"))
    assert payload["node_count"] == len(SAMPLE_NODES)
    assert payload["relationship_count"] == len(SAMPLE_RELS)

    await svc_b.stop()


@pytest.mark.asyncio
async def test_restore_rejects_missing_or_bad_snapshot(tmp_path: Path):
    svc = await _make_archive_service(tmp_path, seed=False)

    # Missing file
    r1 = await svc.restore_graph(tmp_path / "nope.json")
    assert not r1.ok and r1.code == "NOT_FOUND"

    # Bad file (exists but invalid JSON)
    bad = tmp_path / "bad.json.gz"
    with gzip.open(bad, "wb") as f:
        f.write(b"not-json")
    r2 = await svc.restore_graph(bad)
    assert not r2.ok and r2.code == "BAD_SNAPSHOT"

    await svc.stop()
