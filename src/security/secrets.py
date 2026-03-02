"""
Centralized secrets management and validation.

Provides:
- Secret loading with validation
- Required vs optional secret classification
- Log masking for sensitive data
- Secret rotation helpers
- Startup validation
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Secret Classification
# ─────────────────────────────────────────────────────────────────────────────


class SecretType:
    """Classification of secrets by criticality."""

    # Required in production (validation fails if missing)
    REQUIRED_PRODUCTION = {
        "JWT_SECRET",
        "DB_PASSWORD",
        "REDIS_PASSWORD",  # If Redis requires auth
    }

    # Optional but recommended in production
    RECOMMENDED_PRODUCTION = {
        "OPENAI_API_KEY",
        "AUTH0_CLIENT_SECRET",
        "OIDC_JWKS_URL",
        "MG_PASSWORD",
    }

    # Allowed in development (insecure defaults OK)
    DEV_ONLY = {
        "FAKER_LOCALE",
        "DEFAULT_LOCALE",
    }

    # All sensitive fields that should NEVER appear in logs
    SENSITIVE_FIELDS = {
        "password",
        "secret",
        "token",
        "api_key",
        "apikey",
        "auth",
        "authorization",
        "credential",
        "private_key",
        "privatekey",
        "jwt",
        "bearer",
        "oauth",
        "session",
        "cookie",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Secret Masking for Logs
# ─────────────────────────────────────────────────────────────────────────────


class SecretMasker:
    """
    Masks sensitive data in logs and error messages.

    Usage:
        >>> masker = SecretMasker()
        >>> masker.mask("Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...")
        'Bearer ey***...[MASKED]'

        >>> masker.mask_dict({"password": "secret123", "username": "admin"})
        {"password": "***[MASKED]", "username": "admin"}
    """

    # Patterns for common secret formats
    PATTERNS = [
        # JWT tokens
        (re.compile(r"(eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)"), r"eyJ***...[MASKED]"),
        # API keys (common formats)
        (re.compile(r"([A-Za-z0-9]{32,})"), r"***[MASKED]"),
        # Bearer tokens
        (re.compile(r"(Bearer\s+[A-Za-z0-9_.-]+)", re.IGNORECASE), r"Bearer ***[MASKED]"),
        # Basic auth
        (re.compile(r"(Basic\s+[A-Za-z0-9+/=]+)", re.IGNORECASE), r"Basic ***[MASKED]"),
        # Connection strings with passwords
        (re.compile(r"(://[^:]+:)([^@]+)(@)"), r"\1***[MASKED]\3"),
    ]

    def __init__(self, extra_patterns: list[tuple] | None = None):
        """
        Initialize masker with optional custom patterns.

        Args:
            extra_patterns: List of (compiled_regex, replacement) tuples
        """
        self.patterns = self.PATTERNS.copy()
        if extra_patterns:
            self.patterns.extend(extra_patterns)

    def mask(self, text: str) -> str:
        """
        Mask secrets in a string.

        Args:
            text: Input text potentially containing secrets

        Returns:
            Masked text with secrets replaced
        """
        if not text or not isinstance(text, str):
            return text

        masked = text
        for pattern, replacement in self.patterns:
            masked = pattern.sub(replacement, masked)

        return masked

    def mask_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Recursively mask secrets in a dictionary.

        Args:
            data: Dictionary potentially containing secrets

        Returns:
            New dictionary with secrets masked
        """
        if not isinstance(data, dict):
            return data

        masked = {}
        for key, value in data.items():
            # Check if key name suggests sensitive data
            key_lower = key.lower()
            is_sensitive = any(sensitive_term in key_lower for sensitive_term in SecretType.SENSITIVE_FIELDS)

            if is_sensitive:
                # Mask the value
                masked[key] = "***[MASKED]"
            elif isinstance(value, dict):
                # Recursively mask nested dicts
                masked[key] = self.mask_dict(value)
            elif isinstance(value, list):
                # Mask list items
                masked[key] = [self.mask_dict(item) if isinstance(item, dict) else item for item in value]
            elif isinstance(value, str):
                # Mask string values that look like secrets
                masked[key] = self.mask(value)
            else:
                # Leave other types as-is
                masked[key] = value

        return masked

    def mask_url(self, url: str) -> str:
        """
        Mask credentials in URLs.

        Args:
            url: URL potentially containing credentials

        Returns:
            URL with credentials masked

        Example:
            >>> masker.mask_url("postgresql://user:pass123@db:5432/mydb")
            'postgresql://user:***[MASKED]@db:5432/mydb'
        """
        if not url or "://" not in url:
            return url

        # Pattern: scheme://user:password@host
        pattern = re.compile(r"(://[^:]+:)([^@]+)(@)")
        return pattern.sub(r"\1***[MASKED]\3", url)


# ─────────────────────────────────────────────────────────────────────────────
# Secret Validation
# ─────────────────────────────────────────────────────────────────────────────


class SecretValidator:
    """
    Validates secrets on application startup.

    Usage:
        >>> validator = SecretValidator(environment="production")
        >>> validator.validate()  # Raises ValueError if required secrets missing
    """

    def __init__(self, environment: str = "dev"):
        """
        Initialize validator.

        Args:
            environment: Environment name (dev, staging, production)
        """
        self.environment = environment.lower()
        self.is_production = self.environment in ("prod", "production")
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def check_secret(
        self,
        name: str,
        value: str | None,
        required: bool = False,
        min_length: int = 8,
        allow_default: bool = False,
    ) -> bool:
        """
        Check if a secret meets requirements.

        Args:
            name: Secret name
            value: Secret value
            required: Whether secret is required
            min_length: Minimum acceptable length
            allow_default: Whether default/placeholder values are acceptable

        Returns:
            True if valid, False otherwise
        """
        # Check if present
        if not value or not str(value).strip():
            if required:
                self.errors.append(f"{name} is required but not set")
                return False
            else:
                self.warnings.append(f"{name} is not set (optional)")
                return True

        value_str = str(value).strip()

        # Check for insecure defaults
        insecure_defaults = {
            "changeme",
            "change_me",
            "change_me_now",
            "replace_me",
            "secret",
            "password",
            "admin",
            "root",
            "test",
            "demo",
            "example",
            "placeholder",
            "your-",  # Matches "your-api-key", "your-secret", etc.
        }

        value_lower = value_str.lower()
        if not allow_default and any(default in value_lower for default in insecure_defaults):
            if self.is_production:
                self.errors.append(f"{name} contains insecure default value ('{value_str[:20]}...')")
                return False
            else:
                self.warnings.append(f"{name} contains default value (OK in {self.environment})")

        # Check minimum length
        if len(value_str) < min_length:
            msg = f"{name} is too short ({len(value_str)} < {min_length} chars)"
            if self.is_production:
                self.errors.append(msg)
                return False
            else:
                self.warnings.append(msg)

        return True

    def validate_from_settings(self, settings: Any) -> bool:
        """
        Validate secrets from Settings object.

        Args:
            settings: Settings instance (from src.config)

        Returns:
            True if validation passed, False if errors found
        """
        # Required in production
        if self.is_production:
            # JWT secret
            self.check_secret(
                "JWT_SECRET",
                getattr(settings, "JWT_SECRET", None),
                required=True,
                min_length=32,
            )

            # Database password
            self.check_secret(
                "DB_PASSWORD",
                getattr(settings, "DB_PASSWORD", None),
                required=True,
                min_length=12,
            )

        # Recommended secrets (warnings only)
        # Note: OPENAI_API_KEY and AUTH0_CLIENT_SECRET are optional and loaded via environment
        # Skip validation since they're not in Settings class and are truly optional

        # Check for Redis password if Redis is used for rate limiting
        if getattr(settings, "RATE_LIMIT_BACKEND", "redis") == "redis":
            redis_url = getattr(settings, "REDIS_URL", "")
            # If Redis URL contains @, it has auth
            if "@" in redis_url:
                self.check_secret(
                    "REDIS_PASSWORD",
                    getattr(settings, "REDIS_PASSWORD", None),
                    required=False,
                )

        # Log results
        if self.errors:
            for error in self.errors:
                logger.error(f"[SECRETS] {error}")

        if self.warnings:
            for warning in self.warnings:
                logger.warning(f"[SECRETS] {warning}")

        if not self.errors and not self.warnings:
            logger.info(f"[SECRETS] All secrets validated successfully ({self.environment})")

        return len(self.errors) == 0

    def get_summary(self) -> dict[str, Any]:
        """
        Get validation summary.

        Returns:
            Dict with errors, warnings, and status
        """
        return {
            "ok": len(self.errors) == 0,
            "environment": self.environment,
            "errors": self.errors,
            "warnings": self.warnings,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Log Filter for Sensitive Data
# ─────────────────────────────────────────────────────────────────────────────


class SensitiveDataFilter(logging.Filter):
    """
    Logging filter that masks sensitive data in log records.

    Install on root logger:
        >>> logger = logging.getLogger()
        >>> logger.addFilter(SensitiveDataFilter())
    """

    def __init__(self, masker: SecretMasker | None = None):
        """
        Initialize filter.

        Args:
            masker: SecretMasker instance (creates default if None)
        """
        super().__init__()
        self.masker = masker or SecretMasker()

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter log record, masking sensitive data.

        Args:
            record: Log record to filter

        Returns:
            Always True (doesn't suppress records, just modifies them)
        """
        # Mask message
        if hasattr(record, "msg") and isinstance(record.msg, str):
            record.msg = self.masker.mask(record.msg)

        # Mask args
        if hasattr(record, "args") and record.args:
            if isinstance(record.args, dict):
                record.args = self.masker.mask_dict(record.args)
            elif isinstance(record.args, (list, tuple)):
                record.args = tuple(self.masker.mask(arg) if isinstance(arg, str) else arg for arg in record.args)

        return True


# ─────────────────────────────────────────────────────────────────────────────
# Startup Validation
# ─────────────────────────────────────────────────────────────────────────────


def validate_secrets_on_startup(settings: Any) -> dict[str, Any]:
    """
    Validate secrets when application starts.

    Args:
        settings: Settings instance

    Returns:
        Validation summary dict

    Raises:
        ValueError: If validation fails in production
    """
    environment = getattr(settings, "APP_ENV", "dev")
    validator = SecretValidator(environment=environment)

    is_valid = validator.validate_from_settings(settings)
    summary = validator.get_summary()

    # In production, fail fast on errors
    if not is_valid and validator.is_production:
        error_msg = f"Secret validation failed in production: {summary['errors']}"
        logger.critical(error_msg)
        raise ValueError(error_msg)

    return summary


def install_log_masking() -> None:
    """
    Install sensitive data filter on root logger.

    Call this early in application startup (before any logging).
    """
    root_logger = logging.getLogger()

    # Check if already installed
    for filter_obj in root_logger.filters:
        if isinstance(filter_obj, SensitiveDataFilter):
            logger.debug("[SECRETS] Log masking already installed")
            return

    # Install filter
    root_logger.addFilter(SensitiveDataFilter())
    logger.info("[SECRETS] Installed sensitive data log filter")


# ─────────────────────────────────────────────────────────────────────────────
# Secret Rotation Helpers
# ─────────────────────────────────────────────────────────────────────────────


def generate_secure_secret(length: int = 64) -> str:
    """
    Generate a cryptographically secure random secret.

    Args:
        length: Length of secret in characters

    Returns:
        Random hex string

    Example:
        >>> secret = generate_secure_secret(32)
        >>> len(secret)
        64  # hex encoding doubles length
    """
    import secrets

    return secrets.token_hex(length // 2)


def check_secret_age(secret_name: str, last_rotated_days_ago: int) -> bool:
    """
    Check if a secret needs rotation based on age.

    Args:
        secret_name: Name of secret
        last_rotated_days_ago: Days since last rotation

    Returns:
        True if rotation recommended, False otherwise
    """
    # Recommendation: rotate every 90 days
    ROTATION_INTERVAL_DAYS = 90

    if last_rotated_days_ago >= ROTATION_INTERVAL_DAYS:
        logger.warning(
            f"[SECRETS] {secret_name} is {last_rotated_days_ago} days old "
            f"(recommend rotation every {ROTATION_INTERVAL_DAYS} days)"
        )
        return True

    return False


# ─────────────────────────────────────────────────────────────────────────────
# Exports
# ─────────────────────────────────────────────────────────────────────────────

__all__ = [
    "SecretMasker",
    "SecretType",
    "SecretValidator",
    "SensitiveDataFilter",
    "check_secret_age",
    "generate_secure_secret",
    "install_log_masking",
    "validate_secrets_on_startup",
]
