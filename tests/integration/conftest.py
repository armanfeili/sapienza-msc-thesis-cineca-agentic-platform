"""
Integration tests configuration.

This conftest.py inherits fixtures from tests/conftest.py and adds
integration-specific configuration.
"""

import os

import pytest

# Only set DB_HOST to localhost if not already configured
# This allows integration tests to run both locally and inside Docker
if "DB_HOST" not in os.environ:
    os.environ["DB_HOST"] = "localhost"
    os.environ["DB_PORT"] = "5432"

# Disable DEMO_MODE for integration tests to ensure real LLM execution
os.environ["DEMO_MODE"] = "false"


@pytest.fixture(scope="session", autouse=True)
def integration_setup():
    """Set up environment for integration tests."""
    # Only set DB_HOST if not already configured (allows Docker tests to use 'postgres')
    if "DB_HOST" not in os.environ:
        os.environ["DB_HOST"] = "localhost"
    yield


# Mark all tests in this directory as integration tests
def pytest_collection_modifyitems(items):
    """Add integration marker to all tests."""
    for item in items:
        item.add_marker(pytest.mark.integration)
