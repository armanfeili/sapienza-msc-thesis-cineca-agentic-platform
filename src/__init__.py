"""
Top-level package for the Cineca Agentic Platform.

This module intentionally avoids importing submodules (e.g., app, config)
to prevent import side-effects and circular imports at package import time.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version


def _pkg_version() -> str:
    try:
        return version("cineca-agentic-platform")
    except PackageNotFoundError:
        # Fallback for editable/unpackaged repos
        return "0.1.0"


__version__: str = _pkg_version()

__all__ = ["__version__"]
