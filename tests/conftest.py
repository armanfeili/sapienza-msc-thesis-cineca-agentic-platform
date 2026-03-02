"""
Root-level pytest configuration.

This is loaded before tests/conftest.py and BEFORE any test collection.
We use it to set RATE_LIMIT_MODE early so it's available when db modules are imported.

NOTE: The running Docker API server may have RATE_LIMIT_MODE set from docker-compose.
This test configuration must match that setting for rate limit tests to pass.
"""

import os
from pathlib import Path

# Load main .env file (consolidated configuration)
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(env_file, override=False)

# Set RATE_LIMIT_MODE=test for tests BEFORE anything else imports db modules
# This must match the API server's RATE_LIMIT_MODE (typically set in docker-compose)
if "RATE_LIMIT_MODE" not in os.environ:
    os.environ["RATE_LIMIT_MODE"] = "test"

# Set DEMO_MODE=true to skip provider health checks during testing
if "DEMO_MODE" not in os.environ:
    os.environ["DEMO_MODE"] = "true"

# Set APP_ENV=test to disable scheduler and other production features
if "APP_ENV" not in os.environ:
    os.environ["APP_ENV"] = "test"

# Disable scheduler during tests
if "ENABLE_SCHEDULER" not in os.environ:
    os.environ["ENABLE_SCHEDULER"] = "false"


def pytest_addoption(parser):
    """Add custom command-line options for Memgraph NL prompt tests."""
    parser.addoption(
        "--nl-prompts",
        action="store",
        default=None,
        help=(
            "Select specific Memgraph NL prompts to test. "
            "Syntax: comma-separated selectors. "
            "Examples: '3' (index), 'p03' (id), '5:10' (range), 'all' (all prompts). "
            "Combinations: '3,5:10,p19'. "
            "If not specified, defaults to the first prompt (p01) for Phase 1 or full catalog (-m memgraph_nl_full)."
        ),
    )
    parser.addoption(
        "--nl-prompt-text",
        action="store",
        default=None,
        help=(
            "Run a single ad-hoc Memgraph NL prompt (bypasses JSON catalog). "
            "Example: 'How many Blast nodes are there with version X?' "
            "If specified, --nl-prompts is ignored."
        ),
    )
    parser.addoption(
        "--nl-prompts-role",
        action="store",
        default="both",
        choices=["both", "admin", "user"],
        help=(
            "Filter tests by role. "
            "Options: 'both' (default, tests both admin and user), "
            "'admin' (only admin role), 'user' (only user role)."
        ),
    )
    parser.addoption(
        "--nl-force-full-agentic",
        action="store_true",
        default=False,
        help="Disable trivial fast paths for Memgraph NL tests and force full agentic pipeline.",
    )


def pytest_configure(config):
    """Register custom markers for Memgraph NL prompt tests."""
    config.addinivalue_line(
        "markers",
        "memgraph_nl: Memgraph NL→Cypher smoke tests (subset of prompts with smoke=true)"
    )
    config.addinivalue_line(
        "markers",
        "memgraph_nl_full: Memgraph NL→Cypher full catalog tests (all prompts, ~90 minutes)"
    )
