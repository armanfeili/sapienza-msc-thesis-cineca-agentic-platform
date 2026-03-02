#!/usr/bin/env python3
import json
from pathlib import Path

from src.app import app

spec = app.openapi()
out = Path(__file__).resolve().parents[1] / "api" / "openapi.json"
out.parent.mkdir(parents=True, exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    json.dump(spec, f, indent=2)
print(f"Wrote {out}")
