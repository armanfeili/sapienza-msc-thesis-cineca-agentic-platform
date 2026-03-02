"""
Scope-based access control components.
"""


import streamlit as st
from state import get_active_token


def has_scope(required_scope: str) -> bool:
    """
    Check if active token has required scope.

    Args:
        required_scope: Scope to check (e.g., 'admin:all', 'tools:basic')

    Returns:
        True if token has the scope, False otherwise
    """
    token = get_active_token()
    if not token:
        return False

    return required_scope in token.scopes


def has_any_scope(required_scopes: list[str]) -> bool:
    """
    Check if active token has any of the required scopes.

    Args:
        required_scopes: List of acceptable scopes

    Returns:
        True if token has at least one scope, False otherwise
    """
    token = get_active_token()
    if not token:
        return False

    return any(scope in token.scopes for scope in required_scopes)


def has_all_scopes(required_scopes: list[str]) -> bool:
    """
    Check if active token has all required scopes.

    Args:
        required_scopes: List of required scopes

    Returns:
        True if token has all scopes, False otherwise
    """
    token = get_active_token()
    if not token:
        return False

    return all(scope in token.scopes for scope in required_scopes)


def render_scope_chips(required_scopes: list[str], show_status: bool = True):
    """
    Render scope chips showing requirements and active token's status.

    Args:
        required_scopes: List of required scopes
        show_status: Whether to show ✅/❌ status indicators
    """
    token = get_active_token()
    active_scopes = token.scopes if token else []

    chips_html = []
    for scope in required_scopes:
        has_it = scope in active_scopes

        if show_status:
            if has_it:
                color = "#4caf50"
                icon = "✅"
            else:
                color = "#f44336"
                icon = "❌"

            chip = f"""
            <span style="
                display: inline-block;
                padding: 4px 10px;
                margin: 2px;
                background-color: {color}15;
                border: 1px solid {color};
                border-radius: 12px;
                font-size: 0.85em;
                color: {color};
                font-weight: 500;
            ">
                {icon} {scope}
            </span>
            """
        else:
            chip = f"""
            <span style="
                display: inline-block;
                padding: 4px 10px;
                margin: 2px;
                background-color: #e3f2fd;
                border: 1px solid #2196f3;
                border-radius: 12px;
                font-size: 0.85em;
                color: #1976d2;
                font-weight: 500;
            ">
                {scope}
            </span>
            """

        chips_html.append(chip)

    st.markdown("".join(chips_html), unsafe_allow_html=True)


def render_scope_gate(required_scopes: list[str], mode: str = "any", custom_message: str | None = None) -> bool:
    """
    Render a scope gate that shows requirements and blocks access if not met.

    Args:
        required_scopes: List of required scopes
        mode: 'any' (has at least one), 'all' (has all), or specific scope name
        custom_message: Custom message to show when access is denied

    Returns:
        True if access granted, False otherwise
    """
    if mode == "any":
        has_access = has_any_scope(required_scopes)
        requirement_text = "any of these scopes"
    elif mode == "all":
        has_access = has_all_scopes(required_scopes)
        requirement_text = "all of these scopes"
    else:
        has_access = has_scope(mode)
        requirement_text = f"the `{mode}` scope"

    if not has_access:
        message = custom_message or f"This feature requires {requirement_text}:"
        st.warning(f"🔒 {message}", icon="⚠️")

        st.markdown("**Required scopes:**")
        render_scope_chips(required_scopes, show_status=True)

        token = get_active_token()
        if token and token.scopes:
            with st.expander("🔍 Your current scopes"):
                render_scope_chips(token.scopes, show_status=False)
        else:
            st.info("💡 Please log in with an identity that has the required scopes.")

        return False

    return True


def check_admin_access() -> bool:
    """
    Check if user has admin access.
    Convenience function that checks for admin:all or admin:* scopes.
    """
    return has_any_scope(["admin:all", "admin:*"])


def check_tool_access(tool_capabilities: list[str] | None = None) -> bool:
    """
    Check if user has access to invoke tools.

    Args:
        tool_capabilities: Optional list of specific capabilities required

    Returns:
        True if user has tool access, False otherwise
    """
    # Check for general tool access
    if has_any_scope(["tools:invoke:all", "tools:all", "admin:all"]):
        return True

    # Check for basic tool access
    if has_scope("tools:invoke:basic"):
        # If specific capabilities required, check if they're "basic" level
        if tool_capabilities:
            restricted_caps = {"writes_db", "model_management", "admin"}
            if any(cap in restricted_caps for cap in tool_capabilities):
                return False
        return True

    return False
