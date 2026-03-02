import importlib
import inspect
import json
from pathlib import Path
from typing import Any, Callable, Optional

import pytest


def _write_yaml(p: Path, text: str) -> None:
    p.write_text(text.strip() + "\n", encoding="utf-8")


def _find_callable(mod, names: list[str]) -> Optional[Callable[..., Any]]:
    for n in names:
        fn = getattr(mod, n, None)
        if callable(fn):
            return fn
    return None


def _try_call(fn: Callable[..., Any], base_dir: Path):
    """
    Try a few common signatures:
      - fn(base_dir=tmp)
      - fn(tmp)
      - fn(path=tmp)
      - fn(directory=tmp)
    """
    # Keyword first (most robust)
    for kwargs in ({"base_dir": base_dir}, {"path": base_dir}, {"directory": base_dir}):
        try:
            sig = inspect.signature(fn)
            if any(k in sig.parameters for k in kwargs):
                return fn(**kwargs)
        except TypeError:
            pass
    # Positional fallback
    try:
        return fn(base_dir)
    except TypeError:
        # Last resort: no-arg loader that uses its own default folder
        return fn()


def _walk_contains(obj: Any, key: str = "", value: Any = None) -> bool:
    """
    Recursively search for a key (by name) or a concrete value in a JSON-able object.
    If 'key' is provided, returns True if any dict contains that key.
    If 'value' is provided, returns True if any leaf equals that value.
    """
    if isinstance(obj, dict):
        if key and key in obj:
            return True
        for k, v in obj.items():
            if _walk_contains(v, key=key, value=value):
                return True
    elif isinstance(obj, (list, tuple)):
        for it in obj:
            if _walk_contains(it, key=key, value=value):
                return True
    else:
        if value is not None and obj == value:
            return True
    return False


@pytest.mark.parametrize("role_name,max_attempts", [("analyst", 3)])
def test_policies_loader_merges_yaml_files(tmp_path: Path, role_name: str, max_attempts: int):
    """
    Create a temporary policy directory with roles.yaml and retry.yaml, then
    load them through src.security.policies_loader and assert the combined
    structure contains data from both files.

    The test is intentionally resilient to loader API differences by probing
    for common function names and signatures.
    """
    # Arrange: write two policy files
    roles_yaml = f"""
    roles:
      {role_name}:
        allow:
          - "graph.read"
          - "tools.use"
        deny:
          - "admin.write"
    """
    retry_yaml = f"""
    retry:
      backoff: "exponential"
      max_attempts: {max_attempts}
      min_seconds: 0.2
      max_seconds: 3
    """
    _write_yaml(tmp_path / "roles.yaml", roles_yaml)
    _write_yaml(tmp_path / "retry.yaml", retry_yaml)

    # Import the loader
    mod = importlib.import_module("src.security.policies_loader")

    # Find a suitable loader function
    loader = _find_callable(mod, ["load_policies", "load_all", "load_from", "load", "load_dir"])
    if loader is None:
        pytest.skip("policies_loader has no callable loader (load_policies/load_all/load_from/load/load_dir)")

    # Act: call with flexible signature handling
    data = _try_call(loader, tmp_path)

    # Some loaders might return (data, meta) or ServiceResult; normalize
    if hasattr(data, "ok") and hasattr(data, "data"):  # ServiceResult-like
        assert getattr(data, "ok"), f"loader returned failure: {getattr(data, 'error', None)}"
        payload = getattr(data, "data")
    elif isinstance(data, tuple) and len(data) >= 1:
        payload = data[0]
    else:
        payload = data

    # Payload must be JSON-able (dict-like)
    # Using json round-trip for a strict check
    json_payload = json.loads(json.dumps(payload))

    # Assert we can find role structure and retry config somewhere in the result
    assert _walk_contains(json_payload, key="roles"), "Expected 'roles' key in loaded policies"
    assert _walk_contains(json_payload, value=role_name) or _walk_contains(
        json_payload, key=role_name
    ), f"Expected role '{role_name}' in loaded policies"
    assert _walk_contains(json_payload, key="retry"), "Expected 'retry' key in loaded policies"
    assert _walk_contains(json_payload, value=max_attempts), "Expected retry.max_attempts value present"


def test_policies_loader_cache_roundtrip(tmp_path: Path):
    """
    If the loader exposes a cache-aware API (get_policies / reload_policies / clear_cache),
    ensure we can load, mutate files, reload, and observe changes.

    If cache functions aren't available, the test is skipped gracefully.
    """
    # Initial files
    _write_yaml(
        tmp_path / "roles.yaml",
        """
        roles:
          operator:
            allow: ["jobs.run"]
        """,
    )
    _write_yaml(
        tmp_path / "retry.yaml",
        """
        retry:
          backoff: "linear"
          max_attempts: 2
        """,
    )

    mod = importlib.import_module("src.security.policies_loader")

    # Prefer an explicit load into cache if exposed
    load_into_cache = _find_callable(mod, ["load_policies", "load_all", "load_from", "load", "load_dir"])
    get_cached = _find_callable(mod, ["get_policies", "get_cached", "policies"])
    reload_cache = _find_callable(mod, ["reload_policies", "reload", "clear_cache"])

    if load_into_cache is None or get_cached is None or reload_cache is None:
        pytest.skip("policies_loader does not expose cache API (get_policies + reload/clear_cache)")

    # Load once
    _try_call(load_into_cache, tmp_path)
    first = get_cached() if inspect.signature(get_cached).parameters == {} else get_cached()  # noqa: E731

    # Mutate retry file
    _write_yaml(
        tmp_path / "retry.yaml",
        """
        retry:
          backoff: "exponential"
          max_attempts: 5
        """,
    )

    # Reload (signature-insensitive)
    try:
        # prefer base_dir-aware
        _try_call(reload_cache, tmp_path)
    except TypeError:
        # or no-arg
        reload_cache()

    second = get_cached() if inspect.signature(get_cached).parameters == {} else get_cached()

    # Normalize via json round-trip to avoid custom objects
    first_json = json.loads(json.dumps(first))
    second_json = json.loads(json.dumps(second))

    # Expect a difference on max_attempts after reload
    assert not _walk_contains(first_json, value=5), "First load unexpectedly contains new value"
    assert _walk_contains(second_json, value=5), "Reloaded policies should include updated retry.max_attempts"
