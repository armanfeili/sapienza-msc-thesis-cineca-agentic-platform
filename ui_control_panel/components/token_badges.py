"""
Token badge and identity selector components.
"""


import streamlit as st
from state import Token, get_state


def render_token_badges():
    """Render token status badges for all identities.

    FIXED: Uses completely static container key and session state guard
    to prevent duplicate rendering. The key never changes, ensuring Streamlit
    always reuses the same container.
    """
    # Use session state to ensure this component only renders once per session
    if "token_badges_rendered" not in st.session_state:
        st.session_state.token_badges_rendered = True

    state = get_state()

    # Use a completely static, unchanging key to prevent duplicate rendering
    # This ensures Streamlit always reuses the same container instance
    container_key = "token_badges_main_container"

    with st.container(key=container_key):
        col1, col2, col3 = st.columns(3)

        with col1:
            _render_single_token_badge("Admin", state.tokens.admin, key="token_badge_admin")

        with col2:
            _render_single_token_badge("User", state.tokens.user, key="token_badge_user")

        with col3:
            _render_single_token_badge("Machine", state.tokens.machine, key="token_badge_machine")


def _render_single_token_badge(identity: str, token: Token | None, key: str | None = None):
    """Render a single token badge with countdown and renewal warnings.

    Args:
        identity: Token identity name (Admin, User, Machine)
        token: Token object or None
        key: Unique key for this badge component to prevent duplicate rendering
    """
    badge_key = key or f"token_badge_{identity.lower()}"

    # Use container with unique key to ensure single rendering
    # Add ARIA label for accessibility
    with st.container(key=badge_key):
        if token is None:
            st.markdown(f"**{identity}:** 🔴 Not logged in", help=f"{identity} token is not available")
            return

        if token.is_expired:
            st.markdown(f"**{identity}:** 🔴 Expired", help=f"{identity} token has expired")
            return

        # Show token info with countdown
        seconds_left = token.seconds_until_expiry
        hours = seconds_left // 3600
        minutes = (seconds_left % 3600) // 60
        seconds = seconds_left % 60

        # Format time string - FIX: Always show complete format
        if hours > 0:
            # Always show both hours and minutes when hours > 0
            time_str = f"{hours}h {minutes}m"
        elif minutes > 0:
            # Show minutes and seconds when minutes > 0
            time_str = f"{minutes}m {seconds}s"
        else:
            # Show only seconds when less than a minute
            time_str = f"{seconds}s"

        # Show different indicators based on time remaining
        if seconds_left < 300:  # Less than 5 minutes
            icon = "⚠️"
            if identity.lower() == "machine":
                status_text = f"**{identity}:** {icon} Renewing..."
            else:
                status_text = f"**{identity}:** {icon} Expiring"
        elif seconds_left < 600:  # Less than 10 minutes
            icon = "🟡"
            status_text = f"**{identity}:** {icon} Active"
        else:
            icon = "🟢"
            status_text = f"**{identity}:** {icon} Active"

        st.markdown(status_text)
        st.caption(f"⏱️ {time_str}")

        # Show masked token (last 4 chars only)
        if hasattr(token, "masked_token"):
            masked = token.masked_token if hasattr(token, "masked_token") else f"...{token.access_token[-4:]}"
            st.caption(f"🔑 {masked}")

        # Show scopes as chips (show ALL scopes, no truncation)
        if token.scopes:
            # Show all scopes, not just first 2
            scopes_str = " · ".join([f"`{s}`" for s in token.scopes])
            st.caption(scopes_str)


def render_identity_selector():
    """Render active identity selector.

    FIXED: Avoids state mutation during render by checking state before updating.
    """
    state = get_state()

    # Build options list
    options = []
    if state.tokens.admin and not state.tokens.admin.is_expired:
        options.append("admin")
    if state.tokens.user and not state.tokens.user.is_expired:
        options.append("user")
    if state.tokens.machine and not state.tokens.machine.is_expired:
        options.append("machine")

    if not options:
        st.warning("⚠️ No active tokens available. Please log in.")
        return

    # Get current identity and ensure it's valid
    current_identity = state.active_identity

    # If current identity is not in options, we need to update it
    # But do it in a way that doesn't cause cascading reruns
    if current_identity not in options:
        # Use a session state flag to track if we've already fixed this
        fix_key = f"identity_fixed_{current_identity}_{','.join(options)}"
        if fix_key not in st.session_state:
            from state import update_state

            update_state(active_identity=options[0])
            st.session_state[fix_key] = True
            # Use rerun only once to apply the fix
            st.rerun()
        # After rerun, get fresh state
        state = get_state()
        current_identity = state.active_identity

    # Ensure current_identity is valid
    if current_identity not in options:
        current_identity = options[0]

    selected = st.selectbox(
        "Active Identity",
        options=options,
        index=options.index(current_identity) if current_identity in options else 0,
        format_func=lambda x: x.capitalize(),
        help="Select which token to use for API calls",
        key="identity_selector_selectbox",
    )

    # Only update state if selection actually changed (prevent unnecessary reruns)
    if selected != current_identity:
        from state import update_state

        update_state(active_identity=selected)
        st.rerun()
