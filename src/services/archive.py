"""
Archive service: on-demand graph snapshots, archival rotation, and restore.

Features
- Snapshot Memgraph graph to JSON (optionally gzip-compressed)
- Create tar.gz archives from arbitrary paths
- List/rotate backups with simple retention policy
- Restore graph from a snapshot JSON (produced by this service)

Notes
- Snapshot format (JSON) is self-contained:
    {
      "generated_at": "...",
      "node_count": N,
      "relationship_count": M,
      "nodes": [{"orig_id":"...","labels":[...],"properties":{...}}, ...],
      "relationships": [{"type":"X","start":"...","end":"...","properties":{...}}, ...]
    }
- Restore uses MERGE on (:Label {orig_id:$id}) and MERGE relationships.
- Large graphs: this uses batched MERGE statements to keep memory reasonable.
"""

from __future__ import annotations

import contextlib
import gzip
import json
import re
import tarfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from src.services import ServiceBase, ServiceError, ServiceResult, utc_now

try:
    from src.services.etl import ETLService
except Exception:  # pragma: no cover - import order safety
    ETLService = None  # type: ignore[assignment,misc]

if TYPE_CHECKING:
    from src.services.etl import ETLService

try:
    from src.config import settings  # type: ignore
except Exception:  # pragma: no cover
    settings = None  # type: ignore[assignment,misc]

log = structlog.get_logger(__name__)

DEFAULT_BACKUP_DIR = Path("./backups")
DEFAULT_BATCH_SIZE = 500


# ──────────────────────────────────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────────────────────────────────
def _timestamp() -> str:
    return utc_now().strftime("%Y%m%d-%H%M%S")


def _ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def _batched(items: Iterable[Any], size: int) -> Iterable[list[Any]]:
    batch: list[Any] = []
    for it in items:
        batch.append(it)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


# ──────────────────────────────────────────────────────────────────────────────
# Service
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class ArchiveConfig:
    base_dir: Path
    gzip_snapshots: bool = True
    batch_size: int = DEFAULT_BATCH_SIZE
    snapshot_prefix: str = "graph"


class ArchiveService(ServiceBase):
    """
    Manage graph snapshots and generic archives.
    """

    def __init__(
        self,
        *,
        etl: Any | None = None,
        base_dir: str | Path | None = None,
        gzip_snapshots: bool | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        snapshot_prefix: str = "graph",
    ) -> None:
        super().__init__(name="archive-service")

        # Resolve base backup directory from settings or default
        cfg_base = Path(getattr(settings, "BACKUP_DIR", "")) if settings else None
        base = Path(base_dir or cfg_base or DEFAULT_BACKUP_DIR)
        self.config = ArchiveConfig(
            base_dir=_ensure_dir(base),
            gzip_snapshots=bool(True if gzip_snapshots is None else gzip_snapshots),
            batch_size=batch_size,
            snapshot_prefix=snapshot_prefix,
        )

        if etl is not None:
            self.etl = etl
        elif ETLService is not None:
            # Resolve ETLService at runtime so tests that monkeypatch src.services.etl.EtlService or
            # pass in a test double are respected.
            try:
                from src.services import etl as _runtime_etl_mod  # type: ignore

                RuntimeETL = getattr(_runtime_etl_mod, "EtlService", ETLService)
            except Exception:
                RuntimeETL = ETLService
            try:
                self.etl = RuntimeETL()  # type: ignore[assignment]
            except Exception:
                # Fallback to just instantiating the ETLService placeholder
                self.etl = ETLService()  # type: ignore[assignment]
        else:  # pragma: no cover
            raise ServiceError("ETLService is unavailable; cannot initialize ArchiveService")

        log.info(
            "archive.init",
            base_dir=str(self.config.base_dir),
            gzip=self.config.gzip_snapshots,
            batch_size=self.config.batch_size,
        )

    # ──────────────────────────────────────────────────────────────────
    # Snapshot / Restore
    # ──────────────────────────────────────────────────────────────────
    async def snapshot_graph(
        self,
        *,
        pretty: bool = False,
        gzip_output: bool | None = None,
        name_prefix: str | None = None,
    ) -> ServiceResult[dict[str, Any]]:
        """
        Create a snapshot JSON using ETLService.snapshot_export, optionally gzip it.

        Returns:
            {
              "file": "/path/to/graph-YYYYmmdd-HHMMSS.json[.gz]",
              "nodes": N,
              "relationships": M
            }
        """
        prefix = name_prefix or self.config.snapshot_prefix
        ts = _timestamp()
        json_path = self.config.base_dir / f"{prefix}-{ts}.json"

        res = await self.etl.snapshot_export(json_path, pretty=pretty)  # type: ignore[attr-defined]
        if not res.ok:
            return res

        # Compress?
        gz = self.config.gzip_snapshots if gzip_output is None else gzip_output
        out_file = json_path
        if gz:
            gz_path = json_path.with_suffix(json_path.suffix + ".gz")
            await self._gzip_file(json_path, gz_path)
            with contextlib.suppress(FileNotFoundError):
                json_path.unlink()
            out_file = gz_path

        log.info(
            "archive.snapshot_graph.ok",
            file=str(out_file),
            nodes=res.data.get("nodes", 0) if res.data else 0,
            relationships=res.data.get("relationships", 0) if res.data else 0,
        )
        return ServiceResult.success(
            {
                "file": str(out_file),
                "nodes": res.data.get("nodes", 0) if res.data else 0,
                "relationships": res.data.get("relationships", 0) if res.data else 0,
            }
        )

    async def restore_graph(
        self,
        snapshot_path: str | Path,
    ) -> ServiceResult[dict[str, Any]]:
        """
        Restore graph from a snapshot JSON (optionally gzip-compressed).

        Steps:
          - Read JSON payload (auto-decompress .gz)
          - MERGE nodes in batches
          - MERGE relationships in batches
        """
        path = Path(snapshot_path)
        if not path.exists():
            # Return failure with code expected by tests
            return ServiceResult.failure(f"Snapshot not found: {path}", code="NOT_FOUND")

        try:
            payload = await self._read_snapshot_payload(path)
        except Exception as exc:
            return ServiceResult.failure(f"Invalid snapshot: {exc}", code="BAD_SNAPSHOT")

        nodes: list[dict[str, Any]] = list(payload.get("nodes") or [])
        rels: list[dict[str, Any]] = list(payload.get("relationships") or [])
        batch_size = self.config.batch_size

        # Insert nodes
        node_q_tpl = "MERGE (n{labels} {{orig_id:$id}}) SET n += $props"
        node_total = 0
        for batch in _batched(nodes, batch_size):
            statements: list[tuple[str, dict[str, Any]]] = []
            for n in batch:
                labels_list = list(n.get("labels") or [])
                labels_inner = ":".join(f"`{l}`" for l in labels_list)
                labels_segment = f":{labels_inner}" if labels_inner else ""
                props = dict(n.get("properties") or {})
                props["orig_id"] = n.get("orig_id")
                # include _label property to make MERGE label-aware and reversible
                props["_label"] = labels_list[-1] if labels_list else None
                q = node_q_tpl.format(labels=labels_segment)
                statements.append((q, {"id": n.get("orig_id"), "props": props}))
            if statements:
                self.etl.db.bulk_execute(statements)  # type: ignore[attr-defined]
                node_total += len(statements)

        # Insert relationships
        rel_total = 0
        for batch in _batched(rels, batch_size):
            statements = []
            for r in batch:
                rtype = r.get("type")
                start = r.get("start")
                end = r.get("end")
                props = dict(r.get("properties") or {})
                if not rtype or not start or not end:
                    continue
                q = "MATCH (a {orig_id:$a}), (b {orig_id:$b}) " f"MERGE (a)-[rel:`{rtype}`]->(b) " "SET rel += $props"
                statements.append((q, {"a": start, "b": end, "props": props}))
            if statements:
                self.etl.db.bulk_execute(statements)  # type: ignore[attr-defined]
                rel_total += len(statements)

        log.info("archive.restore_graph.ok", nodes=node_total, relationships=rel_total, file=str(path))
        return ServiceResult.success({"nodes": node_total, "relationships": rel_total})

    # ──────────────────────────────────────────────────────────────────
    # Generic archive helpers
    # ──────────────────────────────────────────────────────────────────
    async def make_tar_gz(
        self,
        items: Sequence[str | Path],
        *,
        archive_name: str | None = None,
        base_dir: str | Path | None = None,
    ) -> ServiceResult[dict[str, Any]]:
        """
        Create a tar.gz archive from a list of files/dirs.

        Args:
            items: paths to include
            archive_name: optional filename (default: archive-<ts>.tar.gz)
            base_dir: optional directory to place the archive (default: backup dir)
        """
        out_dir = Path(base_dir) if base_dir else self.config.base_dir
        _ensure_dir(out_dir)
        name = archive_name or f"archive-{_timestamp()}.tar.gz"
        dest = out_dir / name

        try:
            with tarfile.open(dest, "w:gz") as tar:
                for it in items:
                    p = Path(it)
                    if not p.exists():
                        log.warning("archive.make_tar_gz.missing", path=str(p))
                        continue
                    tar.add(str(p), arcname=p.name)
        except Exception as exc:
            return ServiceResult.failure(f"Failed to create archive: {exc}")

        log.info("archive.make_tar_gz.ok", file=str(dest), count=len(items))
        return ServiceResult.success({"file": str(dest), "count": len(items)})

    async def rotate(
        self,
        *,
        pattern: str = r"(graph|snapshot)-\d{8}-\d{6}\.json(\.gz|\.tar\.gz)?$",
        retain: int = 7,
        directory: str | Path | None = None,
    ) -> ServiceResult[dict[str, Any]]:
        """
        Keep the most recent `retain` backups matching `pattern`; delete the rest.

        Args:
            pattern: regex applied to filenames
            retain: number of newest files to keep
            directory: folder to scan (default: backup dir)
        """
        dir_path = Path(directory) if directory else self.config.base_dir
        if not dir_path.exists():
            return ServiceResult.success({"kept": 0, "deleted": 0, "directory": str(dir_path)})

        rx = re.compile(pattern)
        files = [p for p in dir_path.iterdir() if p.is_file() and rx.search(p.name)]
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        keep = files[: max(retain, 0)]
        delete = files[max(retain, 0) :]

        for p in delete:
            with contextlib.suppress(Exception):
                p.unlink()

        log.info("archive.rotate.ok", kept=len(keep), deleted=len(delete), directory=str(dir_path))
        return ServiceResult.success({"kept": len(keep), "deleted": len(delete), "directory": str(dir_path)})

    async def list_backups(
        self,
        *,
        directory: str | Path | None = None,
        sort_desc: bool = True,
    ) -> ServiceResult[list[dict[str, Any]]]:
        """
        Return a list of backup files with size and mtime.
        """
        dir_path = Path(directory) if directory else self.config.base_dir
        if not dir_path.exists():
            return ServiceResult.success([])

        entries: list[dict[str, Any]] = []
        for p in dir_path.iterdir():
            if not p.is_file():
                continue
            st = p.stat()
            entries.append(
                {
                    "file": str(p),
                    "bytes": int(st.st_size),
                    "modified": utc_now().__class__.fromtimestamp(st.st_mtime).isoformat(),  # type: ignore[attr-defined]
                }
            )
        entries.sort(key=lambda x: x["modified"], reverse=sort_desc)
        return ServiceResult.success(entries)

    # ──────────────────────────────────────────────────────────────────
    # Internals
    # ──────────────────────────────────────────────────────────────────
    async def _gzip_file(self, src: Path, dest: Path) -> None:
        """
        Compress `src` → `dest` using gzip.
        """
        with src.open("rb") as f_in, gzip.open(dest, "wb") as f_out:
            while True:
                chunk = f_in.read(1024 * 1024)
                if not chunk:
                    break
                f_out.write(chunk)

    async def _read_snapshot_payload(self, path: Path) -> dict[str, Any]:
        """
        Read and parse snapshot JSON (supports .json or .json.gz).
        """
        if str(path).endswith(".gz") or str(path).endswith(".tar.gz"):
            with gzip.open(path, "rb") as f:
                data = f.read()
            return json.loads(data.decode("utf-8"))
        content = path.read_text(encoding="utf-8")
        return json.loads(content)

    # ──────────────────────────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────────────────────────
    async def start(self) -> None:
        await super().start()
        log.info("archive.started", base_dir=str(self.config.base_dir))

    async def stop(self) -> None:
        log.info("archive.stopping")
        await super().stop()
