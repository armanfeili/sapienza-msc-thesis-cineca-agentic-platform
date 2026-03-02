"""
Background backups helpers.

This module provides small, dependency-light utilities used by the background
scheduler to create timestamped, compressed snapshots of selected project
artifacts (by default the `db/` directory and a few config files). If a more
capable `ArchiveService` is available it can still be used by the background
manager directly; these helpers are a safe fallback.

Features
- Timestamped `.tar.gz` archive creation
- Optional retention pruning by age (days)
- Lightweight ignore rules (e.g., __pycache__, .git)
- Async-friendly wrappers for use in APScheduler jobs

Environment / Settings (via `src.config.settings`)
- BACKUP_DIR: destination directory (default: "./var/backups")
- BACKUP_RETENTION_DAYS: delete backups older than N days (default: 14)
- BACKUP_SOURCES: comma-separated list of paths to include (default: "db")
"""

from __future__ import annotations

import asyncio
import contextlib
import tarfile
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from src.observability.metrics import ServiceMetrics

# Optional metrics interface (duck-typed)
with contextlib.suppress(Exception):
    from src.services.service_metrics import ServiceMetrics  # type: ignore

from src.config import settings

log = structlog.get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────
def _default_backup_dir() -> Path:
    raw = getattr(settings, "BACKUP_DIR", "./var/backups")
    return Path(raw).expanduser().resolve()


def _default_sources() -> list[Path]:
    raw = getattr(settings, "BACKUP_SOURCES", "db")
    if isinstance(raw, str):
        parts = [p.strip() for p in raw.split(",") if p.strip()]
    else:
        # Accept list-like already
        parts = list(raw)
    # Only include paths that currently exist to avoid noisy warnings
    return [Path(p).expanduser().resolve() for p in parts if Path(p).exists()]


@dataclass
class BackupConfig:
    dest_dir: Path = field(default_factory=_default_backup_dir)
    sources: list[Path] = field(default_factory=_default_sources)
    retention_days: int = int(getattr(settings, "BACKUP_RETENTION_DAYS", 14))
    label: str = "cineca"

    def ensure_dir(self) -> None:
        self.dest_dir.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────
IGNORE_NAMES = {
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    ".venv",
    "venv",
    ".tox",
}


def _should_ignore(path: Path) -> bool:
    name = path.name
    if name in IGNORE_NAMES:
        return True
    return bool(name.endswith((".pyc", ".pyo", ".pyd", ".swp", ".DS_Store")))


def _iter_files(base: Path) -> Iterable[Path]:
    if base.is_file():
        yield base
        return
    for p in base.rglob("*"):
        if p.is_dir():
            if _should_ignore(p):
                # Skip directory subtree
                # NOTE: rglob doesn't allow pruning; we'll just ignore adds
                continue
            continue
        if _should_ignore(p):
            continue
        yield p


def _archive_name(cfg: BackupConfig, ts: datetime | None = None) -> Path:
    ts = ts or datetime.utcnow()
    fname = f"{cfg.label}-backup-{ts.strftime('%Y%m%d-%H%M%S')}.tar.gz"
    return cfg.dest_dir / fname


def list_backups(dest_dir: Path | None = None) -> list[Path]:
    """Return list of backup files sorted newest-first."""
    d = (dest_dir or _default_backup_dir()).expanduser()
    if not d.exists():
        return []
    files = [p for p in d.glob("*.tar.gz") if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def latest_backup_path(dest_dir: Path | None = None) -> Path | None:
    files = list_backups(dest_dir)
    return files[0] if files else None


def prune_old_backups(dest_dir: Path, retention_days: int) -> int:
    """Delete backups older than `retention_days`. Returns number removed."""
    if retention_days <= 0:
        return 0
    now = time.time()
    cutoff = now - retention_days * 24 * 3600
    removed = 0
    for p in list_backups(dest_dir):
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink(missing_ok=True)
                removed += 1
                log.info("backup.pruned", file=str(p))
        except Exception as e:  # pragma: no cover
            log.warning("backup.prune_error", file=str(p), err=str(e))
    return removed


# ─────────────────────────────────────────────────────────────────────
# Core create-backup
# ─────────────────────────────────────────────────────────────────────
def create_backup(cfg: BackupConfig | None = None, metrics: ServiceMetrics | None = None) -> Path:
    """
    Create a compressed tar archive with the configured sources.
    Returns the created archive path.
    """
    cfg = cfg or BackupConfig()
    cfg.ensure_dir()
    if not cfg.sources:
        log.warning("backup.no_sources", dest=str(cfg.dest_dir))
        # Still create an empty tarball to mark the attempt
        cfg.sources = []

    dest = _archive_name(cfg)
    start = time.perf_counter()
    files_added = 0

    with tarfile.open(dest, "w:gz") as tar:
        for src in cfg.sources:
            try:
                if src.is_dir():
                    for f in _iter_files(src):
                        arcname = f.relative_to(src.parent)
                        tar.add(f, arcname=str(arcname), recursive=False)
                        files_added += 1
                elif src.is_file():
                    arcname = src.name
                    tar.add(src, arcname=arcname, recursive=False)
                    files_added += 1
                else:
                    log.debug("backup.source_missing", path=str(src))
            except Exception as e:  # pragma: no cover
                log.warning("backup.add_error", path=str(src), err=str(e))

    dur = time.perf_counter() - start
    size = dest.stat().st_size if dest.exists() else 0
    log.info(
        "backup.created",
        dest=str(dest),
        files=files_added,
        bytes=size,
        duration=f"{dur:.3f}s",
    )

    # Record metrics if available (duck-typed)
    with contextlib.suppress(Exception):
        if metrics and hasattr(metrics, "record_backup"):
            metrics.record_backup(bytes=size, files=files_added, duration_seconds=dur)  # type: ignore[attr-defined]

    # Retention pruning
    removed = prune_old_backups(cfg.dest_dir, cfg.retention_days)
    if removed:
        log.info("backup.prune_summary", removed=removed, retention_days=cfg.retention_days)

    return dest


async def backup_once(cfg: BackupConfig | None = None, metrics: ServiceMetrics | None = None) -> Path:
    """Async wrapper for `create_backup` suitable for APScheduler async jobs."""
    return await asyncio.to_thread(create_backup, cfg, metrics)


# ─────────────────────────────────────────────────────────────────────
# CLI / direct execution (optional)
# ─────────────────────────────────────────────────────────────────────
def _parse_cli() -> BackupConfig:
    import argparse

    parser = argparse.ArgumentParser(description="Create a timestamped backup archive.")
    parser.add_argument("--dest", type=str, default=str(_default_backup_dir()), help="Destination directory")
    parser.add_argument(
        "--sources",
        type=str,
        default=",".join(str(p) for p in _default_sources()) or "db",
        help="Comma-separated list of source paths",
    )
    parser.add_argument("--label", type=str, default="cineca", help="Archive label/prefix")
    parser.add_argument("--retention-days", type=int, default=int(getattr(settings, "BACKUP_RETENTION_DAYS", 14)))
    args = parser.parse_args()

    srcs = [Path(s.strip()).expanduser().resolve() for s in args.sources.split(",") if s.strip()]
    return BackupConfig(
        dest_dir=Path(args.dest).expanduser().resolve(),
        sources=srcs,
        retention_days=int(args.retention_days),
        label=args.label,
    )


if __name__ == "__main__":  # pragma: no cover
    cfg = _parse_cli()
    p = create_backup(cfg)
    print(p)

__all__ = [
    "BackupConfig",
    "backup_once",
    "create_backup",
    "latest_backup_path",
    "list_backups",
    "prune_old_backups",
]
