"""
Root-level pytest configuration.

This is loaded before tests/conftest.py and BEFORE any test collection.
We use it to set RATE_LIMIT_MODE early so it's available when db modules are imported.

NOTE: The running Docker API server may have RATE_LIMIT_MODE set from docker-compose.
This test configuration must match that setting for rate limit tests to pass.
"""

import os
from pathlib import Path

import pytest

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


# ---------------------------------------------------------------------------
# Shared OIDC / JWT fixtures
# ---------------------------------------------------------------------------
# These are used across many test modules (api, compliance, caching, security,
# integration, unit, jobs, docs, health, performance, routers, sse, middleware).
# They generate RSA keys at session scope, write a temporary JWKS file, and
# override the app's OIDC settings so that tokens minted in tests are accepted.

from tests.fixtures.oidc import generate_rsa_keypair, write_jwks, mint_jwt  # noqa: E402


@pytest.fixture(scope="session")
def _oidc_keypair():
    """Session-scoped RSA keypair for OIDC test tokens."""
    return generate_rsa_keypair(kid="test-kid-1")


@pytest.fixture()
def configure_oidc(_oidc_keypair, tmp_path_factory):
    """
    Configure the app's OIDC settings to accept test-minted JWTs.

    Writes a temporary JWKS file and sets OIDC_JWKS_URL, OIDC_ISSUER, and
    OIDC_AUDIENCE on ``src.config.settings`` for the duration of the test.
    """
    from src.config import settings
    from src.security.jwt import _JWKS_CACHE

    jwks_dir = tmp_path_factory.mktemp("jwks")
    jwks_path = jwks_dir / "jwks.json"
    write_jwks(jwks_path, _oidc_keypair["public_jwk"])

    orig_url = settings.OIDC_JWKS_URL
    orig_issuer = settings.OIDC_ISSUER
    orig_audience = settings.OIDC_AUDIENCE

    settings.OIDC_JWKS_URL = str(jwks_path)
    settings.OIDC_ISSUER = "https://test-issuer.example.com/"
    settings.OIDC_AUDIENCE = "test-api"

    # Pre-populate the JWT module's JWKS cache so no async fetch is needed
    import time
    _JWKS_CACHE[_oidc_keypair["kid"]] = (_oidc_keypair["public_jwk"], time.time() + 3600)

    yield

    settings.OIDC_JWKS_URL = orig_url
    settings.OIDC_ISSUER = orig_issuer
    settings.OIDC_AUDIENCE = orig_audience
    _JWKS_CACHE.clear()


@pytest.fixture()
def mint_token(_oidc_keypair, configure_oidc):
    """
    Factory fixture that mints RS256 JWTs accepted by the test OIDC config.

    Usage::

        token = mint_token(sub="alice@example.com", roles=["admin"])
        headers = {"Authorization": f"Bearer {token}"}
    """
    from src.config import settings

    def _mint(
        sub: str = "testuser@example.com",
        scopes=None,
        roles=None,
        lifetime_s: int = 3600,
        extra=None,
    ) -> str:
        return mint_jwt(
            _oidc_keypair["private_pem"],
            sub=sub,
            issuer=settings.OIDC_ISSUER,
            audience=settings.OIDC_AUDIENCE,
            scopes=scopes,
            roles=roles,
            lifetime_s=lifetime_s,
            extra=extra,
            kid=_oidc_keypair["kid"],
        )

    return _mint


# ---------------------------------------------------------------------------
# Shared app / client / header fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def app():
    """Return the FastAPI application instance."""
    from src.app import create_app
    return create_app()


@pytest.fixture()
def client(app):
    """FastAPI TestClient wrapping the application."""
    from fastapi.testclient import TestClient
    return TestClient(app)


@pytest.fixture()
def bearer_headers(configure_oidc, mint_token):
    """Admin bearer headers for convenience (most integration tests need admin)."""
    token = mint_token(sub="admin@test.local", roles=["admin"])
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def user_headers(configure_oidc, mint_token):
    """Regular user bearer headers."""
    token = mint_token(sub="user@test.local", roles=["user"])
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin_headers(configure_oidc, mint_token):
    """Admin bearer headers (alias kept for tests that use this name)."""
    token = mint_token(sub="admin@test.local", roles=["admin"])
    return {"Authorization": f"Bearer {token}"}


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
