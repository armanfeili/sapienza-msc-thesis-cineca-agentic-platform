"""
Policy loader (YAML) — roles/scopes and security knobs

Purpose
-------
Centralize loading and merging of YAML-based policy files so the rest of the
security pipeline (authorization, intent/output guards, etc.) can consult a
single, cached source of truth.

Features
--------
- Loads from one or more YAML files (first → last precedence/override).
- Merges dicts deeply; merges role scope lists with de-duplication.
- Exposes helpers to:
    - get the merged policy bundle (with version hash & source mtimes)
    - fetch values via dot-path (e.g., "guards.output.default_limit")
    - list roles and get role→scopes mappings
    - refresh automatically if any source file changed on disk

Configuration
-------------
- You can override default search paths via environment or `src.config.settings`:
    * settings.POLICIES_PATHS   (comma- or colon-separated string, or list)
    * settings.POLICIES_PATH    (single path)
  Defaults (in order):
    - "src/mcp/policies.yaml"
    - "src/agent_policies/roles.yaml"   (if present; supports minimal schema)

Schema (examples)
-----------------
Primary policy file (src/mcp/policies.yaml):
    roles:
      user:   ["read", "tools.invoke"]
      admin:  ["*"]

    guards:
      output:
        mode: "monitor"
        default_limit: 100

Legacy/secondary roles file (src/agent_policies/roles.yaml):
    roles:
      user: ["read"]
      admin: ["*"]

This module is **best-effort**: missing files or invalid YAML won't crash the
app; you'll get an empty/default bundle.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

# YAML is optional but recommended
try:  # pragma: no cover
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

from contextlib import suppress

from src.config import settings

# Logging (structlog if available; stdlib otherwise)
with suppress(Exception):
    from src.logging_setup import get_logger  # type: ignore

    logger = get_logger(__name__)  # type: ignore[assignment]
if "logger" not in globals():
    import logging

    logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Datamodel
# ──────────────────────────────────────────────────────────────────────────────
@dataclass(slots=True)
class PolicyBundle:
    data: dict[str, Any] = field(default_factory=dict)
    roles: dict[str, list[str]] = field(default_factory=dict)
    files: tuple[str, ...] = field(default_factory=tuple)
    mtimes: dict[str, float] = field(default_factory=dict)
    version: str = "sha256:0"
    loaded_at: float = field(default_factory=time.time)

    def get(self, path: str, default: Any = None) -> Any:
        return _get_by_path(self.data, path, default=default)


# ──────────────────────────────────────────────────────────────────────────────
# Defaults & config
# ──────────────────────────────────────────────────────────────────────────────
_DEFAULT_PATHS = (
    os.path.join("src", "mcp", "policies.yaml"),
    os.path.join("src", "agent_policies", "roles.yaml"),
)


def _configured_paths() -> tuple[str, ...]:
    # Accept list-like or delimited strings on settings
    candidates: list[str] = []
    for attr in ("POLICIES_PATHS", "POLICY_PATHS", "POLICIES_PATH", "POLICY_PATH"):
        val = getattr(settings, attr, None)
        if not val:
            continue
        if isinstance(val, (list, tuple, set)):
            candidates.extend([str(x) for x in val])
        else:
            # split on comma or colon
            parts = [p.strip() for p in str(val).replace(";", ",").replace(":", ",").split(",")]
            candidates.extend([p for p in parts if p])
    if not candidates:
        candidates = list(_DEFAULT_PATHS)
    # Deduplicate while preserving order
    seen = set()
    out: list[str] = []
    for p in candidates:
        if p not in seen:
            out.append(p)
            seen.add(p)
    return tuple(out)


# ──────────────────────────────────────────────────────────────────────────────
# YAML loading & merging
# ──────────────────────────────────────────────────────────────────────────────
def _load_yaml(path: str) -> dict[str, Any]:
    if yaml is None:
        logger.debug("PyYAML not available; skipping %s", path)
        return {}
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            return {}
        return data
    except Exception as e:  # pragma: no cover
        logger.warning("failed to load policy file %s: %s", path, e)
        return {}


def _deep_merge(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """
    Merge dict b into a (mutating a) with simple rules:
      - dict + dict: recurse
      - list + list under 'roles' values: de-dup/append preserving order
      - otherwise overwrite with b
    """
    for k, v in b.items():
        if k in a and isinstance(a[k], dict) and isinstance(v, dict):
            _deep_merge(a[k], v)
        elif k == "roles" and isinstance(v, dict):
            base = a.setdefault("roles", {})
            if isinstance(base, dict):
                for role, scopes in v.items():
                    if not isinstance(scopes, (list, tuple)):
                        continue
                    existing = base.get(role, [])
                    if not isinstance(existing, list):
                        existing = []
                    merged: list[str] = []
                    seen = set()
                    for item in list(existing) + [str(x) for x in scopes]:
                        if item not in seen:
                            merged.append(item)
                            seen.add(item)
                    base[role] = merged
            else:
                a["roles"] = v
        elif isinstance(a.get(k), list) and isinstance(v, list):
            # Merge lists by union-preserving order
            a[k] = list(dict.fromkeys(list(a.get(k)) + list(v)))
        else:
            a[k] = v
    return a


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _bundle_from_files(paths: Iterable[str]) -> PolicyBundle:
    merged: dict[str, Any] = {}
    mtimes: dict[str, float] = {}

    for path in paths:
        dat = _load_yaml(path)
        if dat:
            _deep_merge(merged, dat)
            with suppress(Exception):
                mtimes[path] = os.path.getmtime(path)

    # Normalize roles mapping
    roles = {}
    roles_section = merged.get("roles") or merged.get("role_scopes") or {}
    if isinstance(roles_section, dict):
        for r, scopes in roles_section.items():
            if isinstance(scopes, (list, tuple)):
                roles[str(r)] = [str(x) for x in scopes]

    version = "sha256:" + _sha256_hex(_canonical(merged))
    b = PolicyBundle(
        data=merged,
        roles=roles,
        files=tuple(paths),
        mtimes=mtimes,
        version=version,
        loaded_at=time.time(),
    )
    return b


# ──────────────────────────────────────────────────────────────────────────────
# Public, cached interface
# ──────────────────────────────────────────────────────────────────────────────
_BUNDLE: PolicyBundle | None = None


def _load_initial() -> PolicyBundle:
    paths = _configured_paths()
    bundle = _bundle_from_files(paths)
    logger.info(
        "policies_loaded",
        version=bundle.version,
        files=list(bundle.files),
        roles=list(bundle.roles.keys()),
    )
    return bundle


def get_bundle() -> PolicyBundle:
    """Return the cached policy bundle (load if needed)."""
    global _BUNDLE
    if _BUNDLE is None:
        _BUNDLE = _load_initial()
    return _BUNDLE


def refresh_if_changed() -> bool:
    """
    Reload policies if any source file's mtime has changed or if a path that
    previously didn't exist now exists. Returns True if reloaded.
    """
    global _BUNDLE
    current = get_bundle()
    changed = False
    new_mtimes: dict[str, float] = {}

    # Check known files
    for path in current.files:
        with suppress(Exception):
            m = os.path.getmtime(path)
            new_mtimes[path] = m
            if current.mtimes.get(path) != m:
                changed = True

    # Check if any configured-but-missing file appeared
    for path in _configured_paths():
        if (path not in current.files or path not in new_mtimes) and os.path.exists(path):
            changed = True
            new_mtimes[path] = os.path.getmtime(path)

    if not changed:
        return False

    _BUNDLE = _bundle_from_files(_configured_paths())
    logger.info("policies_reloaded", version=_BUNDLE.version, files=list(_BUNDLE.files))
    return True


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def get_roles() -> dict[str, list[str]]:
    """Return role → scopes mapping."""
    return dict(get_bundle().roles)


def get_scopes_for_role(role: str) -> list[str]:
    """Return scopes for a role (or empty list)."""
    return list(get_bundle().roles.get(role, []))


def _get_by_path(data: Mapping[str, Any], path: str, *, default: Any = None) -> Any:
    """
    Traverse dict by dot-path: "guards.output.default_limit"
    """
    cur: Any = data
    for part in path.split("."):
        if not isinstance(cur, Mapping) or part not in cur:
            return default
        cur = cur[part]
    return cur


def get(path: str, default: Any = None) -> Any:
    """Shortcut to fetch from the bundle's data using a dot-path."""
    return get_bundle().get(path, default=default)


def describe() -> dict[str, Any]:
    """Return metadata about the loaded policies (for diagnostics)."""
    b = get_bundle()
    return {
        "version": b.version,
        "files": list(b.files),
        "mtimes": b.mtimes,
        "roles": list(b.roles.keys()),
        "loaded_at": b.loaded_at,
    }


__all__ = [
    "PolicyBundle",
    "describe",
    "get",
    "get_bundle",
    "get_roles",
    "get_scopes_for_role",
    "refresh_if_changed",
]
