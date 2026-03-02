"""
Typed session state management for the Streamlit UI.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import streamlit as st


@dataclass
class Token:
    """Token with metadata."""

    access_token: str
    expires_at: datetime
    subject: str = ""
    scopes: list[str] = field(default_factory=list)

    @property
    def is_expired(self) -> bool:
        """Check if token is expired or close to expiry."""
        return datetime.now() >= self.expires_at

    @property
    def seconds_until_expiry(self) -> int:
        """Seconds until expiry."""
        delta = self.expires_at - datetime.now()
        return max(0, int(delta.total_seconds()))

    @property
    def needs_renewal(self) -> bool:
        """Check if token should be renewed (less than 5 minutes until expiry)."""
        return self.seconds_until_expiry < 300  # 5 minutes

    @property
    def masked_token(self) -> str:
        """Return masked token for display."""
        if len(self.access_token) < 20:
            return "***"
        return f"{self.access_token[:8]}...{self.access_token[-8:]}"

    def has_scope(self, scope: str) -> bool:
        """Check if token has a specific scope."""
        return scope in self.scopes


@dataclass
class TokenSet:
    """Set of tokens for different identities."""

    admin: Token | None = None
    user: Token | None = None
    machine: Token | None = None


@dataclass
class TenantInfo:
    """Tenant information."""

    # Support both old and new field names for backward compatibility
    tenant_id: str | None = None
    id: str | None = None  # Alias for tenant_id
    name: str = ""
    description: str = ""
    admin_name: str = ""
    admin_email: str = ""

    def __post_init__(self):
        """Sync id and tenant_id fields."""
        if self.id and not self.tenant_id:
            self.tenant_id = self.id
        elif self.tenant_id and not self.id:
            self.id = self.tenant_id


@dataclass
class TenantContext:
    """Current tenant context."""

    current: str | None = None
    available: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class UIState:
    """Complete UI session state."""

    # Authentication
    active_identity: str = "machine"  # admin, user, or machine
    tokens: TokenSet = field(default_factory=TokenSet)

    # Tenant context
    tenant: TenantContext = field(default_factory=TenantContext)
    selected_tenant: TenantInfo | None = None

    # Cached data
    providers: list[dict[str, Any]] = field(default_factory=list)
    models: list[dict[str, Any]] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)
    sessions: list[dict[str, Any]] = field(default_factory=list)

    # Model defaults
    model_defaults: dict[str, Any] | None = None
    defaults_loaded: bool = False

    # Agent runs
    active_run: str | None = None
    runs_history: list[dict[str, Any]] = field(default_factory=list)

    # UI settings
    developer_mode: bool = False
    auto_refresh_health: bool = False
    dark_mode: bool = False
    auto_renew_tokens: bool = True  # Enable auto-renewal by default
    last_renewal_check: datetime | None = None
    renewal_notifications: list[str] = field(default_factory=list)

    # Error tracking
    errors: list[dict[str, Any]] = field(default_factory=list)

    # Log file path
    log_file: str = "logs/ui.log"


def init_state() -> UIState:
    """Initialize or retrieve session state."""
    if "ui_state" not in st.session_state:
        st.session_state["ui_state"] = UIState()
    return st.session_state["ui_state"]


def get_state() -> UIState:
    """Get current UI state."""
    return st.session_state.get("ui_state", UIState())


def update_state(**kwargs):
    """Update UI state with provided kwargs."""
    state = get_state()
    for key, value in kwargs.items():
        if hasattr(state, key):
            setattr(state, key, value)
    st.session_state["ui_state"] = state


def get_active_token() -> Token | None:
    """Get the currently active token based on identity selection."""
    state = get_state()
    token = None
    if state.active_identity == "admin":
        token = state.tokens.admin
    elif state.active_identity == "user":
        token = state.tokens.user
    elif state.active_identity == "machine":
        token = state.tokens.machine

    # Return None if token is expired
    if token and token.is_expired:
        return None

    return token


def set_token(identity: str, token: Token):
    """Set token for a specific identity."""
    state = get_state()
    if identity == "admin":
        state.tokens.admin = token
    elif identity == "user":
        state.tokens.user = token
    elif identity == "machine":
        state.tokens.machine = token
    st.session_state["ui_state"] = state


def clear_token(identity: str):
    """Clear token for a specific identity."""
    state = get_state()
    if identity == "admin":
        state.tokens.admin = None
    elif identity == "user":
        state.tokens.user = None
    elif identity == "machine":
        state.tokens.machine = None
    st.session_state["ui_state"] = state


def add_error(message: str, details: str | None = None, trace_id: str | None = None):
    """Add an error to the error log."""
    state = get_state()
    error = {
        "timestamp": datetime.now().isoformat(),
        "message": message,
        "details": details,
        "trace_id": trace_id,
    }
    state.errors.append(error)
    # Keep only last 50 errors
    if len(state.errors) > 50:
        state.errors = state.errors[-50:]
    st.session_state["ui_state"] = state


def clear_errors():
    """Clear all errors from the error log."""
    state = get_state()
    state.errors = []
    st.session_state["ui_state"] = state


def has_model_defaults() -> bool:
    """
    Check if model defaults are configured.

    Returns:
        True if default instance is set, False otherwise
    """
    state = get_state()

    if state.model_defaults:
        return bool(state.model_defaults.get("default_instance_id"))

    return False


def get_default_instance_id() -> str | None:
    """
    Get the default model instance ID.

    Returns:
        Default instance ID or None if not configured
    """
    state = get_state()

    if state.model_defaults:
        return state.model_defaults.get("default_instance_id")

    return None


def add_renewal_notification(message: str):
    """Add a renewal notification message."""
    state = get_state()
    notification = {"timestamp": datetime.now().isoformat(), "message": message}
    state.renewal_notifications.append(notification)
    # Keep only last 10 notifications
    if len(state.renewal_notifications) > 10:
        state.renewal_notifications = state.renewal_notifications[-10:]
    st.session_state["ui_state"] = state


def clear_renewal_notifications():
    """Clear all renewal notifications."""
    state = get_state()
    state.renewal_notifications = []
    st.session_state["ui_state"] = state


def should_check_renewal() -> bool:
    """
    Check if enough time has passed to check for token renewal.
    Returns True if no check in last 60 seconds or never checked.
    """
    state = get_state()

    if not state.auto_renew_tokens:
        return False

    if state.last_renewal_check is None:
        return True

    seconds_since_check = (datetime.now() - state.last_renewal_check).total_seconds()
    return seconds_since_check >= 60  # Check every 60 seconds


def update_renewal_check_time():
    """Update the last renewal check timestamp."""
    state = get_state()
    state.last_renewal_check = datetime.now()
    st.session_state["ui_state"] = state
