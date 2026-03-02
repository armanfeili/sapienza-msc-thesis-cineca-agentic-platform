"""Export the application's OpenAPI spec to a repository file.

Usage:
    python scripts/export_openapi.py

This imports `app` from `src.app`, clears the cached schema, regenerates
it and writes it to `api/openapi.json` to keep the repository spec in sync
with the running code.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import urllib.request

try:
    from src.app import app
except Exception as e:
    print("Failed to import app from src.app:", e)
    sys.exit(2)

# Ensure any cached schema is cleared so we get a fresh build
try:
    app.openapi_schema = None
except Exception:
    try:
        if hasattr(app, "__cached_openapi__"):
            app.__cached_openapi__ = None
    except Exception:
        pass

spec = app.openapi()

# Write to api/openapi.json (repo source of truth)
out_path = pathlib.Path(__file__).resolve().parents[1] / "api" / "openapi.json"
out_path.parent.mkdir(parents=True, exist_ok=True)

with out_path.open("w", encoding="utf-8") as f:
    json.dump(spec, f, indent=2, ensure_ascii=False)

print(f"Wrote OpenAPI spec to: {out_path}")

# Print admin model-management paths for quick verification
paths = sorted([p for p in spec.get("paths", {}) if p.startswith("/v1/admin/models")])
print("ADMIN MODEL PATHS:")
for p in paths:
    print(p)

BASE = os.environ.get("OPENAPI_BASE", "http://localhost:8000").rstrip("/")

for ver, path in [("v1", "/v1/openapi.json"), ("v2", "/v2/openapi.json")]:
    try:
        url = BASE + path
        with urllib.request.urlopen(url, timeout=5) as r:
            spec = json.load(r)
        out = out_path.parent / ("openapi.json" if ver == "v1" else f"openapi_{ver}.json")
        with out.open("w", encoding="utf-8") as f2:
            json.dump(spec, f2, indent=2, ensure_ascii=False)
        print(f"Wrote {out}")
    except Exception as e:
        print(f"Failed to fetch/write {ver} spec from {url}: {e}")


def _check_colon_paths(spec: dict, name: str) -> bool:
    """Return True if spec contains colon characters in any path (bad).

    This enforces a CI guard that prevents publishing OpenAPI files with
    colon-containing path keys (e.g. templated host:port fragments).
    """
    bad = [p for p in spec.get("paths", {}) if ":" in p]
    if bad:
        print(f"ERROR: spec {name} contains paths with ':' which is disallowed:")
        for p in bad:
            print("  ", p)
        return True
    return False


# Perform colon-path checks for the generated local spec and any fetched specs
exit_error = False
try:
    if _check_colon_paths(spec, "aggregated"):
        exit_error = True
except Exception as e:
    print("Failed to validate aggregated spec for colon paths:", e)
    exit_error = True

# Also check any fetched files from the api/ directory (v1/v2) if present
for candidate in [out_path.parent / "openapi.json", out_path.parent / "openapi_v2.json"]:
    if candidate.exists():
        try:
            with candidate.open("r", encoding="utf-8") as f:
                s = json.load(f)
            if _check_colon_paths(s, str(candidate.name)):
                exit_error = True
        except Exception as e:
            print(f"Failed to validate {candidate}: {e}")
            exit_error = True

if exit_error:
    print("One or more OpenAPI specs contain invalid path keys. Aborting with non-zero exit.")
    sys.exit(3)

print("OpenAPI export completed and validated.")
