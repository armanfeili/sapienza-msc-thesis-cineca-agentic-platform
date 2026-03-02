"""
Authentication tab - login/logout and token management.
"""

import os
from datetime import datetime

import streamlit as st
from state import Token, clear_token, get_active_token, get_state, set_token

from api import fetch_auth0_token, get_auth_me


def _load_tokens_from_env():
    """Load pre-fetched tokens from environment variables (machine token only)."""
    state = get_state()

    # Only auto-load machine token (service-to-service)
    # Admin and User tokens require manual login
    machine_token_str = os.getenv("AUTH0_MACHINE_TOKEN")
    if machine_token_str and not state.tokens.machine:
        try:
            import base64
            import json

            payload = machine_token_str.split(".")[1]
            padding = 4 - len(payload) % 4
            if padding != 4:
                payload += "=" * padding
            decoded = json.loads(base64.b64decode(payload))
            exp = decoded.get("exp")
            sub = decoded.get("sub", "unknown")
            scopes_str = decoded.get("scope", "")
            scopes = scopes_str.split() if scopes_str else []

            if exp:
                expires_at = datetime.fromtimestamp(exp)
                # Check if token is not expired
                if datetime.now() < expires_at:
                    # Create Token object and save it
                    token = Token(access_token=machine_token_str, expires_at=expires_at, subject=sub, scopes=scopes)
                    set_token("machine", token)
        except Exception as e:
            # Log error for debugging but don't show to user
            import sys

            print(f"Error loading machine token: {e}", file=sys.stderr)


def _auto_fetch_machine_token_on_startup():
    """
    Auto-fetch machine token on first app load if not already present.
    This ensures machine token is available without manual intervention.
    """
    state = get_state()

    # Only fetch if machine token doesn't exist or is expired
    if state.tokens.machine and not state.tokens.machine.is_expired:
        return  # Token already valid

    # Check if auto-fetch has already been attempted this session
    if "machine_token_auto_fetched" in st.session_state:
        return

    st.session_state.machine_token_auto_fetched = True

    # Try to fetch token silently
    client_id = os.getenv("AUTH0_MACHINE_CLIENT_ID")
    client_secret = os.getenv("AUTH0_MACHINE_CLIENT_SECRET")

    try:
        if not client_id:
            client_id = st.secrets.get("AUTH0_MACHINE_CLIENT_ID")
        if not client_secret:
            client_secret = st.secrets.get("AUTH0_MACHINE_CLIENT_SECRET")
    except Exception:
        pass

    if all([client_id, client_secret]):
        success, token, _error = fetch_auth0_token(
            grant_type="client_credentials", client_id=client_id, client_secret=client_secret
        )

        if success and token:
            set_token("machine", token)


def _check_token_renewal():
    """
    Check if any tokens need renewal and trigger auto-renewal for machine token.
    Should be called periodically (e.g., on each tab load).
    Returns renewal status message.
    """
    state = get_state()

    # Only auto-renew machine token (5 min before expiry)
    if state.tokens.machine and not state.tokens.machine.is_expired:
        seconds_left = state.tokens.machine.seconds_until_expiry

        # Renew if less than 5 minutes remaining
        if seconds_left < 300:  # 5 minutes
            client_id = os.getenv("AUTH0_MACHINE_CLIENT_ID")
            client_secret = os.getenv("AUTH0_MACHINE_CLIENT_SECRET")

            try:
                if not client_id:
                    client_id = st.secrets.get("AUTH0_MACHINE_CLIENT_ID")
                if not client_secret:
                    client_secret = st.secrets.get("AUTH0_MACHINE_CLIENT_SECRET")
            except Exception:
                pass

            if all([client_id, client_secret]):
                success, token, _error = fetch_auth0_token(
                    grant_type="client_credentials", client_id=client_id, client_secret=client_secret
                )

                if success and token:
                    set_token("machine", token)
                    return "🔄 Machine token auto-renewed"

    return None


def render_auth_tab():
    """Render authentication tab with login/logout controls."""
    st.header("🔐 Authentication")

    # Auto-load tokens from environment if available
    _load_tokens_from_env()

    # Auto-fetch machine token on startup if not present
    _auto_fetch_machine_token_on_startup()

    # Check for token renewal
    renewal_msg = _check_token_renewal()
    if renewal_msg:
        st.info(renewal_msg, icon="🔄")

    state = get_state()

    # Login/Logout Controls
    st.subheader("Identity Management")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Admin")
        if state.tokens.admin and not state.tokens.admin.is_expired:
            st.success("✅ Logged in")
            if st.button("🚪 Logout Admin", key="logout_admin"):
                clear_token("admin")
                st.success("Logged out successfully")
                st.rerun()
        elif st.button("🔑 Login Admin", key="login_admin"):
            _login_admin()

    with col2:
        st.markdown("### User")
        if state.tokens.user and not state.tokens.user.is_expired:
            st.success("✅ Logged in")
            if st.button("🚪 Logout User", key="logout_user"):
                clear_token("user")
                st.success("Logged out successfully")
                st.rerun()
        elif st.button("🔑 Login User", key="login_user"):
            _login_user()

    # Machine token (auto-fetch and auto-renew)
    st.markdown("### Machine Token")

    if state.tokens.machine and not state.tokens.machine.is_expired:
        seconds_left = state.tokens.machine.seconds_until_expiry
        hours = seconds_left // 3600
        minutes = (seconds_left % 3600) // 60
        seconds = seconds_left % 60

        # Show different status based on time remaining
        if seconds_left < 300:  # Less than 5 minutes
            st.warning(f"⚠️ Expiring soon: {minutes}m {seconds}s (auto-renewal pending)")
        else:
            st.success(f"✅ Active • Expires in: {hours}h {minutes}m {seconds}s")

        # Show masked token
        masked = state.tokens.machine.masked_token
        st.caption(f"Token: `{masked}`")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Renew Now", key="renew_machine"):
                _fetch_machine_token()
        with col2:
            if st.button("🗑️ Clear Token", key="clear_machine"):
                clear_token("machine")
                st.rerun()
    else:
        st.warning("⚠️ Machine token not available or expired")
        if st.button("🔄 Fetch Machine Token", key="fetch_machine"):
            _fetch_machine_token()

    st.markdown("---")

    # Auto-renewal settings
    from components.auto_renew import display_renewal_notifications, render_auto_renew_settings

    with st.expander("🔄 Auto-Renewal Settings", expanded=False):
        render_auto_renew_settings()

    # Show renewal notifications if any
    display_renewal_notifications()

    st.markdown("---")

    # Show current user claims (only for admin/user tokens, not machine)
    st.subheader("Current Identity Claims")
    token = get_active_token()
    state = get_state()

    # Machine tokens don't have user claims - they represent applications, not users
    if state.active_identity == "machine":
        st.info(
            """
        ℹ️ **Machine Token Active**

        Machine tokens (client credentials) represent applications/services, not users.
        They don't have personal claims like user tokens do.

        To view identity claims, switch to **Admin** or **User** token.
        """
        )
    elif token and not token.is_expired:
        success, data, error = get_auth_me()

        if success and data:
            st.json(data)

            # Show scopes as chips
            if "scopes" in data or "scope" in data:
                scopes = data.get("scopes") or data.get("scope", "").split()
                st.markdown("**Scopes:**")
                scope_chips = " ".join([f"`{s}`" for s in scopes])
                st.markdown(scope_chips)
        else:
            st.error(f"Failed to fetch claims: {error}")
    else:
        st.info("No active token. Please log in.")

    st.markdown("---")

    # Quick permission checks
    st.subheader("Permission Checks")

    # Explain what each token type can do
    if state.active_identity == "machine":
        st.info(
            """
        ℹ️ **Machine Token Permissions**

        Machine tokens have limited permissions by default. They typically can:
        - ✅ Access public endpoints
        - ❌ Cannot access `/v1/auth/me` (user-only endpoint)
        - ❌ Cannot access admin endpoints (unless explicitly granted)

        Machine tokens are designed for service-to-service communication, not user operations.
        """
        )
    else:
        st.markdown(
            """
        These tests verify that your active token has the correct permissions:
        - **User test**: Calls `/v1/auth/me` (requires `user:me` scope)
        - **Admin test**: Calls `/v1/admin/tenants` (requires `admin:all` or `admin:*` scope)
        """
        )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**User-only endpoint test:**")
        if st.button("Test User Access", key="test_user"):
            success, data, error = get_auth_me()
            if success:
                st.success("✅ User access OK")
                st.json(data)
            else:
                st.error(f"❌ {error}")
                if state.active_identity == "machine":
                    st.warning("Machine tokens cannot access user endpoints. Switch to Admin or User token.")
                else:
                    _show_scope_comparison(["user:me"])

    with col2:
        st.markdown("**Admin-only endpoint test:**")
        if st.button("Test Admin Access", key="test_admin"):
            from api import list_tenants

            success, data, error = list_tenants(size=1)
            if success:
                st.success("✅ Admin access OK")
                tenant_count = data.get("total", len(data.get("tenants", data.get("items", []))))
                st.metric("Tenants", tenant_count)
            else:
                st.error(f"❌ {error}")
                _show_scope_comparison(["admin:all", "admin:*"])


def _show_scope_comparison(required_scopes: list):
    """Show comparison between required and actual scopes."""
    from components import render_scope_chips

    token = get_active_token()

    st.markdown("---")
    st.markdown("**🔍 Scope Analysis:**")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Required (any of):**")
        render_scope_chips(required_scopes, show_status=False)

    with col2:
        st.markdown("**Your scopes:**")
        if token and token.scopes:
            render_scope_chips(token.scopes, show_status=False)

            # Show which required scopes are missing
            missing = [s for s in required_scopes if s not in token.scopes]
            if missing:
                st.warning(f"⚠️ Missing: {', '.join(missing)}")
        else:
            st.error("❌ No active token")


def _login_admin():
    """Login as admin user."""
    # Try environment first, then secrets
    client_id = os.getenv("AUTH0_USER_CLIENT_ID")
    client_secret = os.getenv("AUTH0_USER_CLIENT_SECRET")
    username = os.getenv("AUTH0_ADMIN_USERNAME")
    password = os.getenv("AUTH0_ADMIN_PASSWORD")

    # Fallback to secrets if env vars not set
    try:
        if not client_id:
            client_id = st.secrets.get("AUTH0_USER_CLIENT_ID")
        if not client_secret:
            client_secret = st.secrets.get("AUTH0_USER_CLIENT_SECRET")
        if not username:
            username = st.secrets.get("AUTH0_ADMIN_USERNAME")
        if not password:
            password = st.secrets.get("AUTH0_ADMIN_PASSWORD")
    except Exception:
        pass  # Secrets file may not exist

    if not all([client_id, client_secret, username, password]):
        st.error(
            "Auth0 admin credentials not configured. Please set AUTH0_USER_CLIENT_ID, AUTH0_USER_CLIENT_SECRET, AUTH0_ADMIN_USERNAME, and AUTH0_ADMIN_PASSWORD environment variables."
        )
        return

    with st.spinner("Logging in as admin..."):
        success, token, error = fetch_auth0_token(
            grant_type="password",
            client_id=client_id,
            client_secret=client_secret,
            username=username,
            password=password,
            scope="user:me tools:invoke:all admin:all",
        )

    if success and token:
        set_token("admin", token)
        st.success("✅ Logged in as admin")
        st.rerun()
    else:
        st.error(f"Login failed: {error}")


def _login_user():
    """Login as regular user."""
    # Try environment first, then secrets
    client_id = os.getenv("AUTH0_USER_CLIENT_ID")
    client_secret = os.getenv("AUTH0_USER_CLIENT_SECRET")
    username = os.getenv("AUTH0_USER_USERNAME")
    password = os.getenv("AUTH0_USER_PASSWORD")

    # Fallback to secrets if env vars not set
    try:
        if not client_id:
            client_id = st.secrets.get("AUTH0_USER_CLIENT_ID")
        if not client_secret:
            client_secret = st.secrets.get("AUTH0_USER_CLIENT_SECRET")
        if not username:
            username = st.secrets.get("AUTH0_USER_USERNAME")
        if not password:
            password = st.secrets.get("AUTH0_USER_PASSWORD")
    except Exception:
        pass  # Secrets file may not exist

    if not all([client_id, client_secret, username, password]):
        st.error(
            "Auth0 user credentials not configured. Please set AUTH0_USER_CLIENT_ID, AUTH0_USER_CLIENT_SECRET, AUTH0_USER_USERNAME, and AUTH0_USER_PASSWORD environment variables."
        )
        return

    with st.spinner("Logging in as user..."):
        success, token, error = fetch_auth0_token(
            grant_type="password",
            client_id=client_id,
            client_secret=client_secret,
            username=username,
            password=password,
            scope="user:me tools:invoke:basic",
        )

    if success and token:
        set_token("user", token)
        st.success("✅ Logged in as user")
        st.rerun()
    else:
        st.error(f"Login failed: {error}")


def _fetch_machine_token():
    """Fetch machine token using client credentials."""
    # Try environment first, then secrets
    client_id = os.getenv("AUTH0_MACHINE_CLIENT_ID")
    client_secret = os.getenv("AUTH0_MACHINE_CLIENT_SECRET")

    # Fallback to secrets if env vars not set
    try:
        if not client_id:
            client_id = st.secrets.get("AUTH0_MACHINE_CLIENT_ID")
        if not client_secret:
            client_secret = st.secrets.get("AUTH0_MACHINE_CLIENT_SECRET")
    except Exception:
        pass  # Secrets file may not exist

    if not all([client_id, client_secret]):
        st.error(
            "Auth0 machine credentials not configured. Please set AUTH0_MACHINE_CLIENT_ID and AUTH0_MACHINE_CLIENT_SECRET environment variables."
        )
        return

    with st.spinner("Fetching machine token..."):
        success, token, error = fetch_auth0_token(
            grant_type="client_credentials", client_id=client_id, client_secret=client_secret
        )

    if success and token:
        set_token("machine", token)
        st.success("✅ Machine token fetched")
        st.rerun()
    else:
        st.error(f"Token fetch failed: {error}")
