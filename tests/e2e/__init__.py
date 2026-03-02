"""
End-to-end (E2E) test package.

These tests exercise the running stack (API + adapters) as a user would.
They may require services such as Memgraph and Redis to be available,
typically via `docker-compose up -d`.

All tests in this package are marked with `@pytest.mark.e2e`.
"""

import pytest

# Apply the "e2e" marker to the whole package so users can select or skip with:
#   pytest -m e2e
#   pytest -m "not e2e"
pytestmark = [pytest.mark.e2e]

__all__ = []
