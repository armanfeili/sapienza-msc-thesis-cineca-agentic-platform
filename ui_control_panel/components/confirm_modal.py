"""
Confirmation modal component.
"""

from collections.abc import Callable

import streamlit as st


def confirm_action(
    action_name: str,
    action_fn: Callable,
    warning_message: str | None = None,
    button_label: str = "Confirm",
    danger: bool = False,
    key_suffix: str = "",
) -> bool:
    """
    Show a confirmation dialog for a dangerous action.

    Args:
        action_name: Name of the action
        action_fn: Function to call when confirmed
        warning_message: Optional warning message
        button_label: Label for confirm button
        danger: If True, show as danger (red) action
        key_suffix: Unique suffix for widget keys

    Returns:
        True if action was executed
    """
    confirm_key = f"confirm_{action_name}_{key_suffix}"

    # Show warning if provided
    if warning_message:
        st.warning(warning_message)

    # Checkbox for confirmation
    confirmed = st.checkbox(f"I understand and want to {action_name}", key=f"{confirm_key}_checkbox")

    # Execute button
    button_type = "primary" if not danger else "secondary"

    if st.button(button_label, disabled=not confirmed, type=button_type, key=f"{confirm_key}_button"):
        try:
            action_fn()
            st.success(f"✅ {action_name} completed successfully")
            return True
        except Exception as e:
            st.error(f"❌ {action_name} failed: {e!s}")
            return False

    return False
