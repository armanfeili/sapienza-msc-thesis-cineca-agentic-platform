#!/usr/bin/env python3
"""
Export OpenAPI schema from the Cineca Agentic Platform FastAPI app.

Usage:
  python -m src.scripts.export_openapi \
    --out build/openapi.json \
    --yaml build/openapi.yaml \
    --pretty

Notes:
  - This script imports the FastAPI application factory (create_app) from src.app.
  - Falls back to a module-level `app` instance if no factory is available.
  - Optionally emits both JSON and YAML formats.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    # First try a factory function (preferred)
    from src.app import create_app  # type: ignore
except Exception:  # pragma: no cover
    create_app = None  # type: ignore

try:
    # As a fallback, import a module-level app instance
    from src.app import app as module_app  # type: ignore
except Exception:  # pragma: no cover
    module_app = None  # type: ignore


def ensure_parent(path: Path) -> None:
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)


def load_app():
    # Prefer create_app factory if available
    if callable(create_app):
        return create_app()
    if module_app is not None:
        return module_app
    raise RuntimeError(
        "Could not import FastAPI application. Ensure src.app provides " "`create_app()` or a module-level `app`."
    )


def to_yaml(data: dict[str, Any]) -> str:
    try:
        import yaml  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError("PyYAML is required to export YAML. Install with `pip install pyyaml`.") from e
    # Safe dump with a stable format
    return yaml.safe_dump(data, sort_keys=False)  # type: ignore


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Export OpenAPI schema from FastAPI app.")
    p.add_argument("--out", type=Path, default=Path("openapi.json"), help="Path to output JSON file")
    p.add_argument("--yaml", dest="yaml_out", type=Path, default=None, help="Optional path to output YAML file")
    p.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    p.add_argument(
        "--strip-servers",
        action="store_true",
        help="Remove 'servers' key from the schema (useful for env-agnostic artifacts)",
    )
    p.add_argument(
        "--version",
        type=str,
        default=None,
        help="Override the OpenAPI 'info.version' value",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    app = load_app()
    # Build (or fetch cached) OpenAPI schema via FastAPI
    schema: dict[str, Any] = app.openapi()

    if args.strip_servers:
        schema.pop("servers", None)

    if args.version:
        schema.setdefault("info", {})
        schema["info"]["version"] = args.version

    # Write JSON
    ensure_parent(args.out)
    with args.out.open("w", encoding="utf-8") as f:
        if args.pretty:
            json.dump(schema, f, indent=2, ensure_ascii=False)
            f.write("\n")
        else:
            json.dump(schema, f, separators=(",", ":"), ensure_ascii=False)

    # Optionally write YAML
    if args.yaml_out:
        ensure_parent(args.yaml_out)
        yaml_text = to_yaml(schema)
        args.yaml_out.write_text(yaml_text, encoding="utf-8")

    # Minimal console output for CI logs
    if args.yaml_out:
        print(f"Wrote OpenAPI JSON -> {args.out}")
        print(f"Wrote OpenAPI YAML -> {args.yaml_out}")
    else:
        print(f"Wrote OpenAPI JSON -> {args.out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
