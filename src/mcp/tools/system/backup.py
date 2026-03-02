"""
MCP Tool — system.backup

Create, list, and purge application/database backups.

Actions
-------
- create:
    payload: { "label"?: str, "method"?: "auto"|"script"|"export" }
    returns: { ok, action:"create", backup: { id, path, method, created_at, label } }

- list:
    payload: { "limit"?: int }
    returns: { ok, action:"list", backups: [ { id, path, created_at, size_bytes } ] }

- purge:
    payload: { "older_than_days"?: int }
    returns: { ok, action:"purge", removed: [id,...], kept: [id,...] }

Following P3 pattern:
- Uses @mcp_tool decorator
- Internal _act_* functions
- Proper context handling
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import uuid
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# ── JSON (prefer orjson for speed) ────────────────────────────────────────────
try:
    import orjson as _json  # type: ignore

    def _dumps(obj: Any) -> bytes:
        return _json.dumps(obj)

except Exception:  # pragma: no cover
    import json as _json  # type: ignore

    def _dumps(obj: Any) -> bytes:
        return _json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


# ── Logging ───────────────────────────────────────────────────────────────────
with suppress(Exception):
    from src.logging_setup import get_logger  # type: ignore

    logger = get_logger(__name__)  # type: ignore[assignment]
if "logger" not in globals():
    import logging

    logger = logging.getLogger(__name__)

# ── Settings / adapters (optional) ────────────────────────────────────────────
with suppress(Exception):
    from src.config import settings  # type: ignore
with suppress(Exception):
    from src.adapters.db_memgraph import MemgraphAdapter  # type: ignore
with suppress(Exception):
    from src.mcp.decorator import mcp_tool  # type: ignore
with suppress(Exception):
    from src.mcp.context import ToolContext  # type: ignore

# Fallback settings (lightweight) if not packaged
if "settings" not in globals():

    class _S:
        BACKUP_DIR: str = os.getenv("BACKUP_DIR", "backups")
        BACKUP_SCRIPT: str = os.getenv("BACKUP_SCRIPT", "")
        BACKUP_RETENTION_DAYS: int = int(os.getenv("BACKUP_RETENTION_DAYS", "14"))
        MG_HOST: str = os.getenv("MG_HOST", "memgraph")
        MG_PORT: int = int(os.getenv("MG_PORT", "7687"))
        MG_USER: str = os.getenv("MG_USER", "")
        MG_PASSWORD: str = os.getenv("MG_PASSWORD", "")

    settings = _S()  # type: ignore


# ─────────────────────────────────────────────────────────────────────────────
# Filesystem helpers
# ─────────────────────────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _backup_root() -> Path:
    root = Path(settings.BACKUP_DIR).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _new_backup_dir(label: str | None = None) -> tuple[str, Path]:
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    bid = f"{ts}-{uuid.uuid4().hex[:8]}"
    if label:
        safe = "".join(c for c in label if c.isalnum() or c in ("-", "_"))[:32]
        if safe:
            bid = f"{bid}-{safe}"
    path = _backup_root() / bid
    path.mkdir(parents=True, exist_ok=False)
    return bid, path


def _manifest_path(dirpath: Path) -> Path:
    return dirpath / "manifest.json"


def _write_manifest(dirpath: Path, manifest: dict[str, Any]) -> None:
    (_manifest_path(dirpath)).write_bytes(_dumps(manifest))


def _dir_size(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            with suppress(OSError):
                total += p.stat().st_size
    return total


def _list_backups(limit: int = 100) -> list[dict[str, Any]]:
    root = _backup_root()
    items: list[dict[str, Any]] = []
    for child in sorted(root.iterdir(), key=lambda p: p.name, reverse=True):
        if not child.is_dir():
            continue
        mpath = _manifest_path(child)
        created_at = "-"
        try:
            if mpath.exists():
                meta = mpath.read_bytes()
                created_at = "-"
                with suppress(Exception):
                    import json as _pj

                    created_at = _pj.loads(meta).get("created_at", "-")  # type: ignore
        except Exception:
            pass
        items.append(
            {
                "id": child.name,
                "path": str(child),
                "created_at": created_at,
                "size_bytes": _dir_size(child),
            }
        )
        if len(items) >= limit:
            break
    return items


# ─────────────────────────────────────────────────────────────────────────────
# Script-based backup
# ─────────────────────────────────────────────────────────────────────────────
def _script_path() -> Path | None:
    # 1) explicit
    if getattr(settings, "BACKUP_SCRIPT", ""):
        p = Path(settings.BACKUP_SCRIPT).expanduser().resolve()
        if p.exists():
            return p

    # 2) repo default: scripts/backup_db.sh
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "scripts" / "backup_db.sh"
        if candidate.exists():
            return candidate
        candidate2 = parent / "src" / "scripts" / "backup_db.sh"
        if candidate2.exists():
            return candidate2
    return None


def _is_executable(p: Path) -> bool:
    try:
        mode = p.stat().st_mode
        return bool(mode & stat.S_IXUSR) or os.access(str(p), os.X_OK)
    except Exception:
        return False


def _run_script(out_dir: Path) -> tuple[bool, str]:
    spath = _script_path()
    if not spath or not spath.exists():
        return False, "backup script not found"
    if not _is_executable(spath):
        return False, f"backup script not executable: {spath}"

    env = os.environ.copy()
    env["BACKUP_DIR"] = str(out_dir)
    env.setdefault("MG_HOST", str(getattr(settings, "MG_HOST", "memgraph")))
    env.setdefault("MG_PORT", str(getattr(settings, "MG_PORT", 7687)))
    if getattr(settings, "MG_USER", ""):
        env.setdefault("MG_USER", settings.MG_USER)
    if getattr(settings, "MG_PASSWORD", ""):
        env.setdefault("MG_PASSWORD", settings.MG_PASSWORD)

    logger.info("system.backup: running script", extra={"script": str(spath), "out_dir": str(out_dir)})

    try:
        proc = subprocess.run(
            [str(spath)],
            env=env,
            cwd=str(spath.parent),
            capture_output=True,
            text=True,
            check=False,
        )
        ok = proc.returncode == 0
        if not ok:
            logger.error(
                "system.backup: script failed",
                extra={"rc": proc.returncode, "stderr": proc.stderr[-4000:] if proc.stderr else ""},
            )
            return False, f"script failed (rc={proc.returncode})"
        return True, proc.stdout.strip() if proc.stdout else "ok"
    except FileNotFoundError as e:  # pragma: no cover
        return False, f"script not found: {e}"
    except Exception as e:  # pragma: no cover
        logger.exception("system.backup: script execution error")
        return False, str(e)


# ─────────────────────────────────────────────────────────────────────────────
# Export-based backup (Memgraph JSONL)
# ─────────────────────────────────────────────────────────────────────────────
def _export_memgraph(out_dir: Path) -> tuple[bool, str]:
    if "MemgraphAdapter" not in globals():  # pragma: no cover
        return False, "memgraph adapter unavailable"
    mg = None
    try:
        mg = MemgraphAdapter(  # type: ignore[call-arg]
            host=getattr(settings, "MG_HOST", "memgraph"),
            port=int(getattr(settings, "MG_PORT", 7687)),
            username=getattr(settings, "MG_USER", "") or None,
            password=getattr(settings, "MG_PASSWORD", "") or None,
        )
        # quick ping
        try:
            list(mg.execute("RETURN 1 AS ok"))
        except Exception as e:
            return False, f"memgraph unreachable: {e}"

        nodes_fp = (out_dir / "nodes.jsonl").open("wb")
        rels_fp = (out_dir / "relationships.jsonl").open("wb")

        # Export nodes (assumes orig_id exists for merge safety)
        for rec in mg.execute("MATCH (n) RETURN n.orig_id AS orig_id, labels(n) AS labels, properties(n) AS props"):
            line = _dumps(
                {
                    "type": "node",
                    "orig_id": rec.get("orig_id"),
                    "labels": rec.get("labels"),
                    "properties": rec.get("props"),
                }
            )
            nodes_fp.write(line + b"\n")

        # Export relationships keyed by node orig_id
        for rec in mg.execute(
            "MATCH (a)-[r]->(b) " "RETURN a.orig_id AS start, type(r) AS type, b.orig_id AS end, properties(r) AS props"
        ):
            line = _dumps(
                {
                    "type": "relationship",
                    "start": rec.get("start"),
                    "rel_type": rec.get("type"),
                    "end": rec.get("end"),
                    "properties": rec.get("props"),
                }
            )
            rels_fp.write(line + b"\n")

        nodes_fp.close()
        rels_fp.close()
        return True, "export completed"
    except Exception as e:  # pragma: no cover
        logger.exception("system.backup: export failed")
        return False, str(e)
    finally:
        with suppress(Exception):
            if mg:
                mg.close()  # type: ignore[attr-defined]


# ─────────────────────────────────────────────────────────────────────────────
# Internal action handlers (P3 pattern)
# ─────────────────────────────────────────────────────────────────────────────
def _act_create(ctx: ToolContext, payload: dict[str, Any]) -> dict[str, Any]:
    """Create a new backup using specified method."""
    label = payload.get("label")
    method = (payload.get("method") or "auto").lower()

    if method not in ("auto", "script", "export"):
        return {"ok": False, "action": "create", "error": f"invalid method: {method}"}

    bid, bdir = _new_backup_dir(label=label)
    created_at = _now_iso()

    used_method = None
    ok = False
    msg = ""

    if method in ("auto", "script"):
        ok, msg = _run_script(bdir)
        used_method = "script"
        if not ok and method == "script":
            # if explicitly requested script, do not fallback
            shutil.rmtree(bdir, ignore_errors=True)
            return {"ok": False, "action": "create", "error": msg}

    if not ok and method in ("auto", "export"):
        ok, msg = _export_memgraph(bdir)
        used_method = "export"
        if not ok:
            shutil.rmtree(bdir, ignore_errors=True)
            return {"ok": False, "action": "create", "error": msg}

    manifest = {
        "id": bid,
        "created_at": created_at,
        "method": used_method,
        "label": label,
        "principal": ctx.principal if hasattr(ctx, "principal") else None,
        "tenant": ctx.tenant if hasattr(ctx, "tenant") else None,
        "paths": {
            "root": str(bdir),
            "manifest": str(_manifest_path(bdir)),
        },
        "settings": {
            "mg_host": getattr(settings, "MG_HOST", None),
            "mg_port": getattr(settings, "MG_PORT", None),
        },
    }
    _write_manifest(bdir, manifest)
    return {
        "ok": True,
        "action": "create",
        "backup": {
            "id": bid,
            "path": str(bdir),
            "method": used_method,
            "created_at": created_at,
            "label": label,
        },
    }


def _act_list(ctx: ToolContext, payload: dict[str, Any]) -> dict[str, Any]:
    """List existing backups."""
    limit = int(payload.get("limit", 100))
    return {"ok": True, "action": "list", "backups": _list_backups(limit=limit)}


def _act_purge(ctx: ToolContext, payload: dict[str, Any]) -> dict[str, Any]:
    """Purge old backups based on retention policy."""
    days = payload.get("older_than_days")
    if days is None:
        days = int(getattr(settings, "BACKUP_RETENTION_DAYS", 14) or 14)
    cutoff = datetime.now(UTC) - timedelta(days=int(days))

    removed: list[str] = []
    kept: list[str] = []
    root = _backup_root()
    for child in root.iterdir():
        if not child.is_dir():
            continue
        # try parse the timestamp prefix YYYYmmdd-HHMMSS from ID
        try:
            prefix = child.name.split("-", 2)[0]  # YYYYmmdd
            timepart = child.name.split("-", 2)[1]  # HHMMSS
            dt = datetime.strptime(prefix + timepart, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
        except Exception:
            # fallback to mtime
            dt = None
            with suppress(Exception):
                mtime = datetime.fromtimestamp(child.stat().st_mtime, tz=UTC)
                dt = mtime
            if dt is None:
                kept.append(child.name)
                continue

        if dt < cutoff:
            shutil.rmtree(child, ignore_errors=True)
            removed.append(child.name)
        else:
            kept.append(child.name)

    return {"ok": True, "action": "purge", "removed": removed, "kept": kept, "older_than_days": int(days)}


# ─────────────────────────────────────────────────────────────────────────────
# Decorated entry point (P3 pattern)
# ─────────────────────────────────────────────────────────────────────────────
if "mcp_tool" in globals():

    @mcp_tool(tool_name="system.backup", required_scope="tools:admin")
    def system_backup(ctx: ToolContext, payload: dict[str, Any] | None = None, **kwargs) -> dict[str, Any]:
        """
        system.backup tool - Create, list, and purge backups.

        Actions: create, list, purge
        """
        payload = payload or {}
        action = str(payload.get("action") or "list").strip().lower()

        if action == "create":
            return _act_create(ctx, payload)
        elif action == "list":
            return _act_list(ctx, payload)
        elif action == "purge":
            return _act_purge(ctx, payload)
        else:
            raise ValueError(f"unsupported action: {action}")

else:
    # Fallback for environments without decorator
    def system_backup(payload: dict[str, Any] | None = None, **kwargs) -> dict[str, Any]:
        """Fallback entrypoint when decorator is unavailable."""

        # Create minimal context
        class _Ctx:
            principal = None
            tenant = None

        ctx = _Ctx()
        payload = payload or {}
        action = str(payload.get("action") or "list").strip().lower()

        if action == "create":
            return _act_create(ctx, payload)  # type: ignore
        elif action == "list":
            return _act_list(ctx, payload)  # type: ignore
        elif action == "purge":
            return _act_purge(ctx, payload)  # type: ignore
        else:
            raise ValueError(f"unsupported action: {action}")


# Aliases
invoke = system_backup
run = system_backup
handle = system_backup
