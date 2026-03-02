"""
Test package namespace for database-related tests.

This package intentionally contains no import-time side effects to keep pytest
collection fast and to avoid connecting to real services by accident during
discovery. Individual tests import fixtures from `tests.fixtures` as needed.
"""

from __future__ import annotations

__all__: list[str] = []
