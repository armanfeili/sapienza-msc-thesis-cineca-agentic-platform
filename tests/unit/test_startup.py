from __future__ import annotations

import importlib
import pytest


ROUTERS = [
    "src.routers.health",
    "src.routers.auth",
    "src.routers.agent",
    "src.routers.tools",
    "src.routers.models",
    "src.routers.model_management",
    "src.routers.model_processes",
    "src.routers.tenants",
    "src.routers.internal_ops",
]


def test_router_imports():
    """Smoke test: importing router modules should not raise.

    This complements `_try_include` logging so import-time errors surface during CI.
    """
    for mod in ROUTERS:
        try:
            importlib.import_module(mod)
        except Exception as e:
            pytest.fail(f"Failed to import {mod}: {e}")
