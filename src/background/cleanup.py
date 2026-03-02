"""
Background cleanup utilities.

Removes old temporary/cache files and optional ephemeral data in external
stores (e.g., Redis), guided by conservative defaults and environment-driven
overrides in `src.config.settings`.

Features
- Age-based pruning under one or more roots (default: ./var/tmp, ./var/cache)
- Glob pattern matching (tmp/log rollovers/pyc/etc.)
- Prunes __pycache__ folders
- Optional Redis key deletion by pattern (best-effort, optional dependency)
- Async wrapper for easy scheduling with APScheduler

Environment / Settings (via `src.config.settings`)
- CLEANUP_ROOTS: comma-separated directories to scan (default: "./var/tmp,./var/cache")
- CLEANUP_PATTERNS: comma-separated glob patterns (default below)
- CLEANUP_OLDER_THAN_DAYS: age threshold in days (default: 7)
- CLEANUP_REMOVE_EMPTY_DIRS: bool (default: true)
- CLEANUP_REDIS_PATTERNS: comma-separated redis glob patterns (optional)
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from src.config import settings

# Optional Redis (best-effort)
with contextlib.suppress(Exception):
    import redis  # type: ignore

    # If an adapter exists, prefer it.
    with contextlib.suppress(Exception):
        from db.redis_cache.client import get_redis  # type: ignore
    # If no adapter, we will fallback to redis.from_url via env later.
redis = locals().get("redis", None)  # type: ignore

log = structlog.get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Defaults from settings / env
# ─────────────────────────────────────────────────────────────────────
def _csv_to_list(value: str) -> list[str]:
    return [p.strip() for p in value.split(",") if p.strip()]


def _default_roots() -> list[Path]:
    raw = getattr(settings, "CLEANUP_ROOTS", "./var/tmp,./var/cache")
    paths = _csv_to_list(raw) if isinstance(raw, str) else list(raw)
    return [Path(p).expanduser().resolve() for p in paths]


def _default_patterns() -> list[str]:
    raw = getattr(
        settings,
        "CLEANUP_PATTERNS",
        "*.tmp,*.temp,*.bak,*.old,*.log.*,*.~*,*.swp,*.swo,*.pyc,*.pyo,.DS_Store",
    )
    return _csv_to_list(raw) if isinstance(raw, str) else list(raw)


def _default_redis_patterns() -> list[str]:
    raw = getattr(settings, "CLEANUP_REDIS_PATTERNS", "")
    return _csv_to_list(raw) if isinstance(raw, str) else list(raw)


@dataclass
class CleanupConfig:
    roots: list[Path] = field(default_factory=_default_roots)
    patterns: list[str] = field(default_factory=_default_patterns)
    older_than_days: int = int(getattr(settings, "CLEANUP_OLDER_THAN_DAYS", 7))
    remove_empty_dirs: bool = bool(getattr(settings, "CLEANUP_REMOVE_EMPTY_DIRS", True))
    dry_run: bool = False
    # folder names to always remove (recursively) when found
    purge_folders: tuple[str, ...] = ("__pycache__",)
    redis_patterns: list[str] = field(default_factory=_default_redis_patterns)

    def cutoff_ts(self) -> float:
        return time.time() - max(0, self.older_than_days) * 24 * 3600

    def ensure_roots(self) -> None:
        for r in self.roots:
            with contextlib.suppress(Exception):
                r.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────
# File-system cleanup
# ─────────────────────────────────────────────────────────────────────
SAFE_GUARD_MIN_DEPTH = 2  # e.g., "/tmp/cineca" depth is 2; avoid deleting shallow roots


def _is_under(parent: Path, child: Path) -> bool:
    try:
        child_resolved = child.resolve()
        parent_resolved = parent.resolve()
        return parent_resolved in child_resolved.parents or child_resolved == parent_resolved
    except Exception:
        return False


def _safe_guard(path: Path, roots: Sequence[Path]) -> bool:
    """
    Ensure we never operate outside allowed roots and we don't nuke suspicious
    top-level directories. This is intentionally conservative.
    """
    if not any(_is_under(r, path) for r in roots):
        return False
    # Protect extremely shallow directories (/, /tmp, project root)
    try:
        depth = len(path.resolve().parts)
        if depth <= SAFE_GUARD_MIN_DEPTH:
            return False
    except Exception:
        return False
    return True


def _iter_candidates(cfg: CleanupConfig) -> Iterable[Path]:
    cutoff = cfg.cutoff_ts()
    for root in cfg.roots:
        if not root.exists():
            continue

        # 1) Purge special folders recursively (e.g. __pycache__)
        for name in cfg.purge_folders:
            for folder in root.rglob(name):
                if folder.is_dir() and _safe_guard(folder, cfg.roots):
                    yield folder  # we handle directories later

        # 2) Pattern-based file pruning
        for pattern in cfg.patterns:
            for path in root.rglob(pattern):
                # Skip directories for file patterns (handled above)
                if path.is_dir():
                    continue
                with contextlib.suppress(FileNotFoundError):
                    mtime = path.stat().st_mtime
                    if mtime < cutoff and _safe_guard(path, cfg.roots):
                        yield path


def _delete_file(path: Path, dry_run: bool = False) -> bool:
    try:
        if dry_run:
            return True
        path.unlink(missing_ok=True)
        return True
    except Exception as e:  # pragma: no cover
        log.warning("cleanup.delete_file_error", path=str(path), err=str(e))
        return False


def _delete_dir_tree(path: Path, dry_run: bool = False) -> bool:
    try:
        if dry_run:
            return True
        shutil.rmtree(path, ignore_errors=True)
        return True
    except Exception as e:  # pragma: no cover
        log.warning("cleanup.delete_dir_error", path=str(path), err=str(e))
        return False


def _prune_empty_dirs(root: Path, dry_run: bool = False) -> int:
    removed = 0
    # Walk bottom-up to try removing empty directories
    for p in sorted([d for d in root.rglob("*") if d.is_dir()], key=lambda x: len(x.parts), reverse=True):
        with contextlib.suppress(OSError):
            try:
                if not any(p.iterdir()):
                    if not dry_run:
                        p.rmdir()
                    removed += 1
            except Exception:
                # Non-empty or permission issues—ignore
                pass
    return removed


def cleanup_filesystem(cfg: CleanupConfig | None = None) -> dict[str, int]:
    cfg = cfg or CleanupConfig()
    cfg.ensure_roots()
    stats = {"files_deleted": 0, "dirs_deleted": 0, "empty_dirs_pruned": 0, "skipped": 0}

    # Collect unique candidates (avoid duplicates if patterns overlap)
    candidates: list[Path] = []
    seen = set()
    for c in _iter_candidates(cfg):
        try:
            key = c.resolve()
        except Exception:
            key = c
        if key in seen:
            continue
        seen.add(key)
        candidates.append(c)

    for p in candidates:
        try:
            if p.is_dir():
                ok = _delete_dir_tree(p, cfg.dry_run)
                stats["dirs_deleted"] += int(ok)
                stats["skipped"] += int(not ok)
            else:
                ok = _delete_file(p, cfg.dry_run)
                stats["files_deleted"] += int(ok)
                stats["skipped"] += int(not ok)
        except Exception as e:  # pragma: no cover
            log.warning("cleanup.candidate_error", path=str(p), err=str(e))
            stats["skipped"] += 1

    if cfg.remove_empty_dirs:
        for root in cfg.roots:
            pruned = _prune_empty_dirs(root, cfg.dry_run)
            stats["empty_dirs_pruned"] += pruned

    log.info("cleanup.filesystem_done", **stats, roots=[str(r) for r in cfg.roots], dry_run=cfg.dry_run)
    return stats


# ─────────────────────────────────────────────────────────────────────
# Redis cleanup (best-effort)
# ─────────────────────────────────────────────────────────────────────
def _connect_redis_best_effort():
    """
    Try to obtain a Redis client from adapter or URL envs.
    Returns a client or None if not available.
    """
    # Prefer adapter if present
    with contextlib.suppress(Exception):
        if "get_redis" in globals():  # type: ignore
            client = get_redis()  # type: ignore
            if client:
                return client

    # Fallback to redis.from_url via env
    if redis is None:
        return None
    url = os.getenv("REDIS_URL") or os.getenv("UPSTASH_REDIS_URL") or os.getenv("CACHE_REDIS_URL") or None
    if not url:
        host = os.getenv("REDIS_HOST", "redis")
        port = int(os.getenv("REDIS_PORT", "6379"))
        db = int(os.getenv("REDIS_DB", "0"))
        url = f"redis://{host}:{port}/{db}"
    with contextlib.suppress(Exception):
        return redis.from_url(url, decode_responses=True)
    return None


def cleanup_redis(patterns: Sequence[str] | None = None) -> dict[str, int]:
    """
    Delete keys matching the given patterns using SCAN. This is *not* age-based,
    because portable age requires server-side modules or privileged commands.
    Use prefixes/suffixes that only hit ephemeral keys.
    """
    pats = list(patterns or [])
    if not pats:
        return {"deleted": 0, "scanned": 0}

    client = _connect_redis_best_effort()
    if not client:
        log.info("cleanup.redis_skipped_no_client")
        return {"deleted": 0, "scanned": 0}

    total_deleted = 0
    total_scanned = 0

    for pat in pats:
        try:
            cursor: int | str = 0
            batch: list[str] = []
            while True:
                cursor, batch = client.scan(cursor=cursor, match=pat, count=500)  # type: ignore[attr-defined]
                total_scanned += len(batch)
                if batch:
                    try:
                        total_deleted += client.delete(*batch)  # type: ignore[attr-defined]
                    except Exception:
                        # Fallback to single deletes to be safe
                        for k in batch:
                            with contextlib.suppress(Exception):
                                total_deleted += int(client.delete(k))  # type: ignore[attr-defined]
                if cursor in {0, "0"}:
                    break
            log.info("cleanup.redis_pattern_done", pattern=pat, deleted=total_deleted, scanned=total_scanned)
        except Exception as e:  # pragma: no cover
            log.warning("cleanup.redis_error", pattern=pat, err=str(e))

    return {"deleted": total_deleted, "scanned": total_scanned}


# ─────────────────────────────────────────────────────────────────────
# Unified entry points
# ─────────────────────────────────────────────────────────────────────
def cleanup_all(cfg: CleanupConfig | None = None) -> dict[str, dict[str, int] | list[str]]:
    """
    Run file-system cleanup and optional Redis cleanup.
    Returns a summary dict of per-subsystem stats.
    """
    cfg = cfg or CleanupConfig()
    fs_stats = cleanup_filesystem(cfg)
    redis_stats = {"deleted": 0, "scanned": 0}
    if cfg.redis_patterns:
        redis_stats = cleanup_redis(cfg.redis_patterns)

    summary = {
        "filesystem": fs_stats,
        "redis": redis_stats,
        "roots": [str(r) for r in cfg.roots],
        "patterns": cfg.patterns,
        "purge_folders": list(cfg.purge_folders),
    }
    log.info("cleanup.all_done", summary=summary)
    return summary


async def cleanup_once(cfg: CleanupConfig | None = None) -> dict[str, dict[str, int] | list[str]]:
    """Async wrapper for APScheduler."""
    return await asyncio.to_thread(cleanup_all, cfg)


# ─────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────
def _parse_cli() -> CleanupConfig:
    import argparse

    parser = argparse.ArgumentParser(description="Prune temporary/cache files and optional Redis keys.")
    parser.add_argument(
        "--roots",
        type=str,
        default=",".join(str(p) for p in _default_roots()),
        help="Comma-separated directories to scan.",
    )
    parser.add_argument(
        "--patterns",
        type=str,
        default=",".join(_default_patterns()),
        help="Comma-separated glob patterns for files.",
    )
    parser.add_argument("--older-than-days", type=int, default=int(getattr(settings, "CLEANUP_OLDER_THAN_DAYS", 7)))
    parser.add_argument("--no-prune-empty-dirs", action="store_true", help="Do not prune empty directories.")
    parser.add_argument("--dry-run", action="store_true", help="Do not delete; just log what would be removed.")
    parser.add_argument(
        "--redis-patterns",
        type=str,
        default=",".join(_default_redis_patterns()),
        help="Comma-separated Redis key patterns to delete (optional).",
    )

    args = parser.parse_args()

    roots = [Path(p).expanduser().resolve() for p in _csv_to_list(args.roots)]
    patterns = _csv_to_list(args.patterns)
    redis_pats = _csv_to_list(args.redis_patterns)

    return CleanupConfig(
        roots=roots,
        patterns=patterns,
        older_than_days=int(args.older_than_days),
        remove_empty_dirs=not args.no_prune_empty_dirs,
        dry_run=bool(args.dry_run),
        redis_patterns=redis_pats,
    )


if __name__ == "__main__":  # pragma: no cover
    cfg = _parse_cli()
    summary = cleanup_all(cfg)
    print(summary)

__all__ = [
    "CleanupConfig",
    "cleanup_all",
    "cleanup_filesystem",
    "cleanup_once",
    "cleanup_redis",
]
