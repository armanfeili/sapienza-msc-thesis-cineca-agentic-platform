"""
Automatic token renewal component.
"""

import os

import streamlit as st
from state import (
    add_renewal_notification,
    get_state,
    set_token,
    should_check_renewal,
    update_renewal_check_time,
)

from api import fetch_auth0_token


def try_renew_machine_token() -> tuple[bool, str | None]:
    """
    Attempt to renew the machine token using client credentials.

    Returns:
        Tuple of (success, error_message)
    """
    try:
        # Get machine client credentials from environment or secrets
        client_id = os.getenv("AUTH0_MACHINE_CLIENT_ID")
        client_secret = os.getenv("AUTH0_MACHINE_CLIENT_SECRET")

        # Try secrets if env vars not available
        if not client_id or not client_secret:
            try:
                client_id = st.secrets.get("AUTH0_MACHINE_CLIENT_ID")
                client_secret = st.secrets.get("AUTH0_MACHINE_CLIENT_SECRET")
            except Exception:
                pass

        if not client_id or not client_secret:
            return False, "Machine client credentials not configured"

        # Fetch new token
        success, token, error = fetch_auth0_token(
            grant_type="client_credentials", client_id=client_id, client_secret=client_secret
        )

        if success and token:
            # Update machine token in state
            set_token("machine", token)
            return True, None
        else:
            return False, error or "Failed to renew token"

    except Exception as e:
        return False, f"Renewal error: {e!s}"


def check_and_renew_tokens() -> None:
    """
    Check if any tokens need renewal and attempt to renew them.
    This should be called periodically (e.g., every 60 seconds).

    FIXED: Already has debouncing via should_check_renewal(), but ensures
    no unnecessary state updates that could trigger reruns.
    """
    # Check if we should perform a renewal check (debounced to max once per 60 seconds)
    if not should_check_renewal():
        return

    # Update the check timestamp before doing any work
    update_renewal_check_time()

    state = get_state()

    # Check machine token (only one we can auto-renew)
    if state.tokens.machine and state.tokens.machine.needs_renewal:
        if not state.tokens.machine.is_expired:
            # Token needs renewal but hasn't expired yet
            success, error = try_renew_machine_token()

            if success:
                msg = "✅ Machine token auto-renewed successfully"
                add_renewal_notification(msg)
                # Only show toast if not in a rerun loop (check session state)
                if "renewal_toast_shown" not in st.session_state:
                    st.toast(msg, icon="✅")
                    st.session_state.renewal_toast_shown = True
            else:
                msg = f"⚠️ Failed to auto-renew machine token: {error}"
                add_renewal_notification(msg)
                # Only show toast if not in a rerun loop
                if "renewal_error_toast_shown" not in st.session_state:
                    st.toast(msg, icon="⚠️")
                    st.session_state.renewal_error_toast_shown = True


def display_renewal_notifications() -> None:
    """Display recent renewal notifications in an expander."""
    state = get_state()

    if state.renewal_notifications:
        with st.expander("🔄 Token Renewal History", expanded=False):
            for notif in reversed(state.renewal_notifications[-5:]):  # Show last 5
                timestamp = notif.get("timestamp", "")
                message = notif.get("message", "")
                if timestamp and message:
                    st.caption(f"{timestamp}: {message}")


def display_token_status_badge(identity: str = "machine") -> None:
    """
    Display a status badge for token expiry.

    Args:
        identity: Token identity to check (admin, user, or machine)
    """
    state = get_state()
    token = None

    if identity == "admin":
        token = state.tokens.admin
    elif identity == "user":
        token = state.tokens.user
    elif identity == "machine":
        token = state.tokens.machine

    if not token:
        st.warning(f"⚠️ No {identity} token")
        return

    seconds_left = token.seconds_until_expiry

    # Determine status color and message
    if token.is_expired:
        st.error(f"❌ {identity.capitalize()} token expired")
    elif token.needs_renewal:
        minutes_left = seconds_left // 60
        if identity == "machine" and state.auto_renew_tokens:
            st.warning(f"⏱️ {identity.capitalize()} token expires in {minutes_left}m (auto-renew enabled)")
        else:
            st.warning(f"⏱️ {identity.capitalize()} token expires in {minutes_left}m")
    else:
        minutes_left = seconds_left // 60
        hours_left = minutes_left // 60
        if hours_left > 1:
            st.success(f"✅ {identity.capitalize()} token valid ({hours_left}h)")
        else:
            st.info(f"✅ {identity.capitalize()} token valid ({minutes_left}m)")


def render_auto_renew_settings() -> None:
    """Render auto-renewal settings in sidebar or settings page."""
    state = get_state()

    st.subheader("🔄 Auto-Renewal Settings")

    # Toggle auto-renewal
    auto_renew = st.checkbox(
        "Enable automatic token renewal",
        value=state.auto_renew_tokens,
        help="Automatically renew machine tokens 5 minutes before expiry",
        key="auto_renew_toggle",
    )

    if auto_renew != state.auto_renew_tokens:
        state.auto_renew_tokens = auto_renew
        st.session_state["ui_state"] = state
        if auto_renew:
            st.success("✅ Auto-renewal enabled")
        else:
            st.info("ℹ️ Auto-renewal disabled")

    # Show current status
    if state.auto_renew_tokens:
        st.caption("✅ Machine tokens will auto-renew at T-5min")

        # Show last check time
        if state.last_renewal_check:
            import humanize

            try:
                last_check = humanize.naturaltime(state.last_renewal_check)
                st.caption(f"Last check: {last_check}")
            except:
                st.caption(f"Last check: {state.last_renewal_check.strftime('%H:%M:%S')}")
    else:
        st.caption("ℹ️ Manual renewal required for expired tokens")

    # Manual renewal button for machine token
    st.divider()
    st.caption("**Manual Renewal**")

    if st.button("🔄 Renew Machine Token Now", key="manual_renew_machine"):
        with st.spinner("Renewing machine token..."):
            success, error = try_renew_machine_token()

            if success:
                st.success("✅ Machine token renewed successfully")
                add_renewal_notification("✅ Manual renewal: Machine token renewed")
            else:
                st.error(f"❌ Failed to renew: {error}")
                add_renewal_notification(f"❌ Manual renewal failed: {error}")
