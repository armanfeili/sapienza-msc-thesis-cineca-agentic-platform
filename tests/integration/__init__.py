"""
Integration tests package.

Small helpers for environment-driven behavior shared by integration tests.
"""

from __future__ import annotations

import os
from typing import Optional


def env_flag(name: str, default: bool = False) -> bool:
    """
    Parse a boolean-like environment variable.

    Truthy: "1", "true", "yes", "on"
    Falsy:  "0", "false", "no", "off"
    """
    val = os.getenv(name)
    if val is None:
        return bool(default)
    s = str(val).strip().lower()
    if s in {"1", "true", "yes", "on"}:
        return True
    if s in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def env_str(name: str, default: Optional[str] = None) -> Optional[str]:
    """Fetch string environment variable with optional default."""
    v = os.getenv(name)
    return v if v is not None else default


def is_ci() -> bool:
    """Detect if running in a CI environment."""
    return env_flag("CI", False) or bool(env_str("GITHUB_ACTIONS"))


# Conventional toggles used by tests
RUN_SLOW = env_flag("RUN_SLOW", False)
RUN_E2E_EXTERNAL = env_flag("CINECA_TEST_EXTERNAL", False)
BASE_URL = env_str("CINECA_BASE_URL", "http://localhost:8000")

__all__ = [
    "env_flag",
    "env_str",
    "is_ci",
    "RUN_SLOW",
    "RUN_E2E_EXTERNAL",
    "BASE_URL",
]
