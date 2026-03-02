"""
Tests for demo authenticator production guard.

Verifies that authenticate_demo() is disabled in production environments.

NOTE: Since authenticate_demo imports settings internally, we test the 
actual behavior using monkeypatch on the config module.
"""

import pytest
import os

from src.security.auth import UserInfo


@pytest.fixture(autouse=True)
def restore_modules_after_test():
    """Restore modules to test mode after each demo auth test.

    Demo auth tests reload src.config and src.security modules with different
    APP_ENV values. This can break subsequent tests that expect test mode.
    This fixture ensures modules are reloaded back to test mode after each test.
    """
    yield
    # After test: restore to test mode
    import importlib
    import src.config
    import src.security.auth
    import src.security.jwt
    import os

    # Ensure APP_ENV is test
    os.environ["APP_ENV"] = "test"

    # Reload modules to pick up test environment
    importlib.reload(src.config)
    importlib.reload(src.security.auth)
    importlib.reload(src.security.jwt)

    # Clear JWKS cache
    try:
        from src.security.jwt import _JWKS_CACHE

        _JWKS_CACHE.clear()
    except (ImportError, AttributeError):
        pass


class TestDemoAuthProductionGuard:
    """Test demo authenticator security."""

    def test_demo_auth_allowed_in_development(self, monkeypatch):
        """Demo auth works in development environment."""
        monkeypatch.setenv("APP_ENV", "dev")

        # Reload config and auth to pick up new env
        import importlib
        import src.config
        import src.security.auth

        importlib.reload(src.config)
        importlib.reload(src.security.auth)

        from src.security.auth import authenticate_demo

        user = authenticate_demo("testuser", "password")

        assert user.username == "testuser"
        assert "user" in user.scopes

    def test_demo_auth_allowed_in_test(self, monkeypatch):
        """Demo auth works in test environment (default)."""
        monkeypatch.setenv("APP_ENV", "test")

        # Reload config and auth to pick up new env
        import importlib
        import src.config
        import src.security.auth

        importlib.reload(src.config)
        importlib.reload(src.security.auth)

        from src.security.auth import authenticate_demo

        user = authenticate_demo("testuser", "password")

        assert user.username == "testuser"
        assert "user" in user.scopes

    def test_demo_auth_blocked_in_production(self, monkeypatch):
        """Demo auth raises RuntimeError in production."""
        monkeypatch.setenv("APP_ENV", "prod")

        # Reload config to pick up new env
        import importlib
        import src.config
        import src.security.auth

        importlib.reload(src.config)
        importlib.reload(src.security.auth)

        from src.security.auth import authenticate_demo

        with pytest.raises(RuntimeError) as exc_info:
            authenticate_demo("testuser", "password")

        assert "disabled in production" in str(exc_info.value).lower()
        assert "OIDC" in str(exc_info.value) or "real user database" in str(exc_info.value)

    def test_demo_auth_admin_in_development(self, monkeypatch):
        """Admin user gets admin scope in development."""
        monkeypatch.setenv("APP_ENV", "dev")

        # Reload config and auth to pick up new env
        import importlib
        import src.config
        import src.security.auth

        importlib.reload(src.config)
        importlib.reload(src.security.auth)

        from src.security.auth import authenticate_demo

        user = authenticate_demo("admin", "password")

        assert "user" in user.scopes
        assert "admin" in user.scopes

    def test_demo_auth_rejects_empty_username(self, monkeypatch):
        """Demo auth rejects empty username even in dev."""
        monkeypatch.setenv("APP_ENV", "dev")

        # Reload config and auth to pick up new env
        import importlib
        import src.config
        import src.security.auth

        importlib.reload(src.config)
        importlib.reload(src.security.auth)

        from src.security.auth import authenticate_demo

        with pytest.raises(ValueError) as exc_info:
            authenticate_demo("", "password")

        assert "username and password are required" in str(exc_info.value)

    def test_demo_auth_rejects_empty_password(self, monkeypatch):
        """Demo auth rejects empty password even in dev."""
        monkeypatch.setenv("APP_ENV", "dev")

        # Reload config and auth to pick up new env
        import importlib
        import src.config
        import src.security.auth

        importlib.reload(src.config)
        importlib.reload(src.security.auth)

        from src.security.auth import authenticate_demo

        with pytest.raises(ValueError) as exc_info:
            authenticate_demo("testuser", "")

        assert "username and password are required" in str(exc_info.value)
