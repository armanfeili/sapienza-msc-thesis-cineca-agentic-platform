"""
Routers package for the Cineca Agentic Platform.

Concrete router modules live next to this file (e.g., health.py, auth.py, agent.py, ...).
They are imported lazily by `src.app` to avoid import-time side effects and circular
dependencies. This __init__ intentionally avoids importing submodules.
"""

from __future__ import annotations

__all__: list[str] = []
