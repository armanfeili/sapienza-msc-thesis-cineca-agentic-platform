"""
tests package initializer.

This module makes it easier to run tests from any working directory by:
- ensuring the project root is on sys.path
- setting safe default environment variables for the test runtime
- applying a few sensible warning filters
"""

from __future__ import annotations

import asyncio
import os
import sys
import warnings
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────────────────────
TESTS_ROOT: Path = Path(__file__).resolve().parent
PROJECT_ROOT: Path = TESTS_ROOT.parent

# Put project root at the front of sys.path so `import src` works reliably
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ──────────────────────────────────────────────────────────────────────────────
# Environment defaults for tests (do not override if already set)
# ──────────────────────────────────────────────────────────────────────────────
_env_defaults = {
    # App/env
    "APP_ENV": "test",
    "ENV": "test",
    "LOG_LEVEL": "WARNING",
    "APP_VERSION": "0.0.0-test",
    # DB (Memgraph) — tests often use fakes/mocks, but keep defaults sane
    "MG_HOST": "memgraph",
    "MG_PORT": "7687",
    "MG_USER": "",
    "MG_PASSWORD": "",
    # Redis (used by rate limit & sessions; tests can stub, but default to local)
    "REDIS_URL": "redis://localhost:6379/0",
    "REDIS_PREFIX": "cineca-test",
    "CACHE_TTL_SECONDS": "60",
    # Rate limiting
    "RATE_LIMIT_ENABLED": "true",
    "RATE_LIMIT_BACKEND": "memory",  # default to in-process backend for tests
    "RATE_LIMIT_DEFAULT_LIMIT": "60",
    "RATE_LIMIT_DEFAULT_WINDOW": "60",
    # Guards
    "INTENT_FILTER_ENABLED": "true",
    "INTENT_FILTER_MODE": "monitor",
    "OUTPUT_GUARD_MODE": "monitor",
    "OUTPUT_GUARD_ENFORCE_LIMIT": "true",
    "OUTPUT_GUARD_DEFAULT_LIMIT": "100",
    # Tenancy
    "TENANCY_ENABLED": "false",
    "TENANCY_DEFAULT": "",
    # Sessions
    "SESSION_TTL_SECONDS": "604800",  # 7 days
    # Observability toggles (safe, low-noise)
    "PROMETHEUS_ENABLED": "false",
    "TRACING_ENABLED": "false",
}

for k, v in _env_defaults.items():
    os.environ.setdefault(k, v)


# ──────────────────────────────────────────────────────────────────────────────
# Warnings & asyncio policy
# ──────────────────────────────────────────────────────────────────────────────
# Make deprecations visible during tests; treat resource warnings as errors
warnings.simplefilter("default", DeprecationWarning)
warnings.simplefilter("default", FutureWarning)
warnings.simplefilter("error", ResourceWarning)

# On Windows/Py3.8-, prefer the modern event loop policy for compatibility
if sys.platform.startswith("win"):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]
    except Exception:
        pass


__all__ = ["TESTS_ROOT", "PROJECT_ROOT"]
