import asyncio
import json
from pathlib import Path

import pytest

from tests.fixtures.fake_memgraph import FakeMemgraphAdapter, sample_graph
from src.services.etl import ETLService
from src.services.archive import ArchiveService, DEFAULT_BATCH_SIZE


@pytest.mark.asyncio
async def test_archive_snapshot_and_restore_round_trip(tmp_path: Path):
    """
    Build a small in-memory graph, snapshot it (gzipped), then restore into a
    fresh (empty) graph and assert node/relationship counts match.
    """
    # ── Build source graph in a fake Memgraph adapter
    src_graph = sample_graph()  # provides nodes + rels
    src_db = FakeMemgraphAdapter.from_graph(src_graph)
    src_etl = ETLService(db=src_db)
    src_archive = ArchiveService(etl=src_etl, base_dir=tmp_path, gzip_snapshots=True, batch_size=64)

    # ── Snapshot to gzipped json
    snap_res = await src_archive.snapshot_graph(pretty=False, gzip_output=True, name_prefix="graph")
    assert snap_res.ok, snap_res.error
    snap_file = Path(snap_res.data["file"])
    assert snap_file.exists() and snap_file.suffix == ".gz"

    # Sanity: snapshot payload decodes and contains fields we expect when un-gzipped
    # (We don't rely on ArchiveService internals here — just a quick check.)
    import gzip as _gzip

    with _gzip.open(snap_file, "rb") as f:
        payload = json.loads(f.read().decode("utf-8"))
    assert "generated_at" in payload and "nodes" in payload and "relationships" in payload
    assert payload["node_count"] == len(payload["nodes"])
    assert payload["relationship_count"] == len(payload["relationships"])

    # ── Restore into a fresh graph
    dst_db = FakeMemgraphAdapter()  # empty graph
    dst_etl = ETLService(db=dst_db)
    dst_archive = ArchiveService(etl=dst_etl, base_dir=tmp_path, gzip_snapshots=True, batch_size=DEFAULT_BATCH_SIZE)

    restore_res = await dst_archive.restore_graph(snap_file)
    assert restore_res.ok, restore_res.error

    # Validate round-trip counts via ETLService.validate_graph()
    src_stats = await src_etl.validate_graph()
    dst_stats = await dst_etl.validate_graph()
    assert src_stats.ok and dst_stats.ok
    assert src_stats.data["node_count"] == dst_stats.data["node_count"]
    assert src_stats.data["relationship_count"] == dst_stats.data["relationship_count"]

    # Spot-check labels/types presence symmetry (order not guaranteed)
    assert set(dst_stats.data["labels"]) == set(src_stats.data["labels"])
    assert set(dst_stats.data["relationship_types"]) == set(src_stats.data["relationship_types"])


@pytest.mark.asyncio
async def test_rotate_and_list_backups(tmp_path: Path):
    """
    Create a few fake backup files, ensure list_backups returns them sorted and
    rotate() keeps only the desired number.
    """
    # Prepare archive service with no actual ETL dependency (it won't be used)
    fake_db = FakeMemgraphAdapter()
    etl = ETLService(db=fake_db)
    svc = ArchiveService(etl=etl, base_dir=tmp_path, gzip_snapshots=True)

    # Create N fake backup files with increasing mtimes
    names = [
        "graph-20240101-000001.json.gz",
        "graph-20240102-000002.json.gz",
        "graph-20240103-000003.json.gz",
        "graph-20240104-000004.json.gz",
        "graph-20240105-000005.json.gz",
    ]
    paths = []
    for i, n in enumerate(names, start=1):
        p = tmp_path / n
        p.write_bytes(b"fake")
        # bump mtime so sorting by mtime is deterministic
        atime = p.stat().st_atime
        p.utime((atime, atime + i))
        paths.append(p)

    # list_backups should return all entries sorted by modified desc
    lst = await svc.list_backups()
    assert lst.ok
    files = [Path(e["file"]).name for e in lst.data]
    # Expect reverse of names (newest mtime last created)
    assert files == list(reversed(names))

    # Rotate to keep only the 2 newest
    rot = await svc.rotate(pattern=r"graph-\d{8}-\d{6}\.json(\.gz)?$", retain=2)
    assert rot.ok
    assert rot.data["kept"] == 2
    assert rot.data["deleted"] == len(names) - 2

    # Confirm only two remain on disk
    remaining = sorted([p.name for p in tmp_path.iterdir() if p.is_file()])
    expected_remaining = sorted(list(reversed(names))[:2])
    assert remaining == expected_remaining


@pytest.mark.asyncio
async def test_make_tar_gz(tmp_path: Path):
    """
    Ensure make_tar_gz archives the provided files and returns a path.
    """
    # Prepare some files
    f1 = tmp_path / "a.txt"
    f2 = tmp_path / "b.log"
    f1.write_text("hello")
    f2.write_text("world")

    # Wire up ArchiveService (ETL not used here but required by ctor)
    db = FakeMemgraphAdapter()
    etl = ETLService(db=db)
    svc = ArchiveService(etl=etl, base_dir=tmp_path)

    out = await svc.make_tar_gz([f1, f2], archive_name="bundle.tar.gz")
    assert out.ok, out.error
    tar_path = Path(out.data["file"])
    assert tar_path.exists() and tar_path.name == "bundle.tar.gz"

    # A quick read check: tarfile can open it and see two members
    import tarfile

    with tarfile.open(tar_path, "r:gz") as tar:
        names = sorted(m.name for m in tar.getmembers() if m.isfile())
    assert names == ["a.txt", "b.log"]
