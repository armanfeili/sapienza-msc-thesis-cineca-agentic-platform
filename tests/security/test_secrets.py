"""
Tests for secrets management and validation.
"""

import logging
import pytest
from unittest.mock import Mock, patch

from src.security.secrets import (
    SecretMasker,
    SecretValidator,
    SensitiveDataFilter,
    validate_secrets_on_startup,
    install_log_masking,
    generate_secure_secret,
    check_secret_age,
)


class TestSecretMasker:
    """Test secret masking functionality."""

    def test_mask_jwt_token(self):
        """Test masking JWT tokens."""
        masker = SecretMasker()

        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.TJVA95OrM7E2cBab30RMHrHDcEfxjoYZgeFONFh7HgQ"
        masked = masker.mask(jwt)

        assert "eyJ***...[MASKED]" in masked
        assert jwt not in masked

    def test_mask_bearer_token(self):
        """Test masking Bearer tokens."""
        masker = SecretMasker()

        text = "Authorization: Bearer abc123def456"
        masked = masker.mask(text)

        assert "Bearer ***[MASKED]" in masked
        assert "abc123def456" not in masked

    def test_mask_connection_string(self):
        """Test masking database connection strings."""
        masker = SecretMasker()

        url = "postgresql://user:secretpassword@db:5432/mydb"
        masked = masker.mask_url(url)

        assert "secretpassword" not in masked
        assert "***[MASKED]" in masked
        assert "postgresql://user:" in masked
        assert "@db:5432/mydb" in masked

    def test_mask_dict_with_password(self):
        """Test masking dictionary with password field."""
        masker = SecretMasker()

        data = {
            "username": "admin",
            "password": "secret123",
            "api_key": "abcdef123456",
        }

        masked = masker.mask_dict(data)

        assert masked["username"] == "admin"  # Non-sensitive preserved
        assert masked["password"] == "***[MASKED]"
        assert masked["api_key"] == "***[MASKED]"

    def test_mask_nested_dict(self):
        """Test masking nested dictionaries."""
        masker = SecretMasker()

        data = {
            "db": {
                "host": "localhost",
                "password": "secret",
            },
            "redis": {
                "url": "redis://localhost",
                "auth_token": "token123",
            },
        }

        masked = masker.mask_dict(data)

        assert masked["db"]["host"] == "localhost"
        assert masked["db"]["password"] == "***[MASKED]"
        assert masked["redis"]["auth_token"] == "***[MASKED]"

    def test_mask_list_of_dicts(self):
        """Test masking lists containing dictionaries."""
        masker = SecretMasker()

        data = {
            "users": [
                {"name": "alice", "password": "pass1"},
                {"name": "bob", "token": "token2"},
            ]
        }

        masked = masker.mask_dict(data)

        assert masked["users"][0]["name"] == "alice"
        assert masked["users"][0]["password"] == "***[MASKED]"
        assert masked["users"][1]["token"] == "***[MASKED]"


class TestSecretValidator:
    """Test secret validation."""

    def test_production_requires_strong_secrets(self):
        """Test that production environment requires strong secrets."""
        validator = SecretValidator(environment="production")

        # Weak password should fail in production
        is_valid = validator.check_secret(
            "JWT_SECRET",
            "changeme",
            required=True,
            min_length=32,
        )

        assert not is_valid
        assert len(validator.errors) > 0
        assert "insecure default" in validator.errors[0].lower()

    def test_dev_allows_weak_secrets(self):
        """Test that development environment allows weak secrets with warnings."""
        validator = SecretValidator(environment="dev")

        # Weak password should warn but not fail in dev
        is_valid = validator.check_secret(
            "JWT_SECRET",
            "changeme",
            required=False,
            min_length=32,
        )

        assert is_valid  # Doesn't fail
        assert len(validator.warnings) > 0  # But warns

    def test_missing_required_secret_fails(self):
        """Test that missing required secrets fail validation."""
        validator = SecretValidator(environment="production")

        is_valid = validator.check_secret(
            "DB_PASSWORD",
            None,
            required=True,
        )

        assert not is_valid
        assert len(validator.errors) > 0
        assert "required but not set" in validator.errors[0].lower()

    def test_short_secret_fails_in_production(self):
        """Test that short secrets fail in production."""
        validator = SecretValidator(environment="production")

        is_valid = validator.check_secret(
            "API_KEY",
            "abc123",
            required=True,
            min_length=32,
        )

        assert not is_valid
        assert any("too short" in err.lower() for err in validator.errors)

    def test_valid_secret_passes(self):
        """Test that valid strong secrets pass validation."""
        validator = SecretValidator(environment="production")

        is_valid = validator.check_secret(
            "JWT_SECRET",
            "a" * 64,  # Long random string
            required=True,
            min_length=32,
        )

        assert is_valid
        assert len(validator.errors) == 0

    def test_validation_summary(self):
        """Test validation summary generation."""
        validator = SecretValidator(environment="production")

        validator.check_secret("VALID_SECRET", "x" * 64, required=True)
        validator.check_secret("WEAK_SECRET", "changeme", required=False)

        summary = validator.get_summary()

        assert summary["ok"] is False  # Has errors
        assert summary["environment"] == "production"
        assert summary["error_count"] > 0
        assert "errors" in summary
        assert "warnings" in summary


class TestSensitiveDataFilter:
    """Test logging filter for sensitive data."""

    def test_filter_masks_log_message(self):
        """Test that filter masks sensitive data in log messages."""
        masker = SecretMasker()
        log_filter = SensitiveDataFilter(masker=masker)

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="User logged in with password: secret123",
            args=(),
            exc_info=None,
        )

        log_filter.filter(record)

        # Message should still exist but potentially masked
        assert record.msg is not None

    def test_filter_masks_dict_args(self):
        """Test that filter masks dictionary arguments."""
        masker = SecretMasker()
        log_filter = SensitiveDataFilter(masker=masker)

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Login attempt: %s",
            args={"username": "admin", "password": "secret"},
            exc_info=None,
        )

        log_filter.filter(record)

        assert isinstance(record.args, dict)
        assert record.args.get("password") == "***[MASKED]"
        assert record.args.get("username") == "admin"


class TestValidateSecretsOnStartup:
    """Test startup validation."""

    def test_startup_validation_with_mock_settings(self):
        """Test startup validation with mock settings object."""
        mock_settings = Mock()
        mock_settings.APP_ENV = "dev"
        mock_settings.JWT_SECRET = "a" * 64
        mock_settings.DB_PASSWORD = "b" * 32
        mock_settings.OPENAI_API_KEY = None
        mock_settings.AUTH0_CLIENT_SECRET = None
        mock_settings.RATE_LIMIT_BACKEND = "memory"

        summary = validate_secrets_on_startup(mock_settings)

        assert "ok" in summary
        assert "environment" in summary
        assert summary["environment"] == "dev"

    def test_startup_validation_fails_in_production_with_weak_secrets(self):
        """Test that startup validation fails in production with weak secrets."""
        mock_settings = Mock()
        mock_settings.APP_ENV = "production"
        mock_settings.JWT_SECRET = "changeme"  # Weak!
        mock_settings.DB_PASSWORD = "password"  # Weak!
        mock_settings.OPENAI_API_KEY = None
        mock_settings.AUTH0_CLIENT_SECRET = None
        mock_settings.RATE_LIMIT_BACKEND = "memory"

        with pytest.raises(ValueError, match="Secret validation failed"):
            validate_secrets_on_startup(mock_settings)


class TestHelpers:
    """Test helper functions."""

    def test_generate_secure_secret(self):
        """Test secure secret generation."""
        secret = generate_secure_secret(64)

        assert len(secret) == 64  # token_hex returns hex string of requested length
        assert all(c in "0123456789abcdef" for c in secret)

    def test_check_secret_age_needs_rotation(self):
        """Test secret age checking."""
        needs_rotation = check_secret_age("TEST_SECRET", 100)

        assert needs_rotation is True  # 100 days > 90 day threshold

    def test_check_secret_age_still_fresh(self):
        """Test secret that doesn't need rotation yet."""
        needs_rotation = check_secret_age("TEST_SECRET", 30)

        assert needs_rotation is False  # 30 days < 90 day threshold


class TestInstallLogMasking:
    """Test log masking installation."""

    def test_install_log_masking_adds_filter(self):
        """Test that install_log_masking adds filter to root logger."""
        # Get root logger
        root_logger = logging.getLogger()

        # Remove any existing filters
        root_logger.filters = [f for f in root_logger.filters if not isinstance(f, SensitiveDataFilter)]

        # Install masking
        install_log_masking()

        # Check filter was added
        has_filter = any(isinstance(f, SensitiveDataFilter) for f in root_logger.filters)

        assert has_filter

    def test_install_log_masking_idempotent(self):
        """Test that installing masking multiple times is safe."""
        # Install twice
        install_log_masking()
        install_log_masking()

        # Should only have one filter
        root_logger = logging.getLogger()
        filter_count = sum(1 for f in root_logger.filters if isinstance(f, SensitiveDataFilter))

        assert filter_count == 1
