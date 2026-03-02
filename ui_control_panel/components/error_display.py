"""
Error display components with retry functionality.
"""

from collections.abc import Callable
from typing import Any

import streamlit as st


def display_error_with_retry(
    error_message: str,
    is_retryable: bool = False,
    retry_callback: Callable | None = None,
    retry_args: tuple = (),
    retry_kwargs: dict | None = None,
    key_suffix: str = "",
) -> Any | None:
    """
    Display an error message with optional retry button.

    Args:
        error_message: The error message to display
        is_retryable: Whether this error can be retried
        retry_callback: Function to call when retry is clicked
        retry_args: Positional arguments for retry_callback
        retry_kwargs: Keyword arguments for retry_callback
        key_suffix: Unique suffix for widget keys to avoid conflicts

    Returns:
        Result of retry_callback if retry was clicked and succeeded, None otherwise
    """
    # Display error in an error container
    if retry_kwargs is None:
        retry_kwargs = {}
    with st.container():
        st.error(error_message)

        if is_retryable and retry_callback:
            _col1, col2, _col3 = st.columns([1, 2, 1])
            with col2:
                if st.button("🔄 Retry", key=f"retry_{key_suffix}", type="primary", use_container_width=True):
                    with st.spinner("Retrying..."):
                        return retry_callback(*retry_args, **retry_kwargs)

    return None


def display_api_error(
    error_message: str, is_retryable: bool = False, endpoint: str = "", trace_id: str | None = None
) -> None:
    """
    Display a formatted API error with metadata.

    Args:
        error_message: The error message
        is_retryable: Whether the error is retryable
        endpoint: The API endpoint that failed
        trace_id: Optional trace ID for debugging
    """
    with st.container():
        # Main error message
        st.error(error_message)

        # Additional metadata in expander
        if endpoint or trace_id:
            with st.expander("🔍 Error Details"):
                if endpoint:
                    st.code(f"Endpoint: {endpoint}")
                if trace_id:
                    st.code(f"Trace ID: {trace_id}")
                    if st.button("📋 Copy Trace ID", key=f"copy_trace_{trace_id[:8]}"):
                        st.write(f"✅ Copied: `{trace_id}`")

        # Show retry hint if retryable
        if is_retryable:
            st.info("💡 This error may be temporary. Try again or wait a moment.")


def handle_api_response(
    success: bool,
    data: Any,
    error: str | None,
    is_retryable: bool = False,
    retry_callback: Callable | None = None,
    retry_args: tuple = (),
    retry_kwargs: dict | None = None,
    key_suffix: str = "",
) -> tuple[bool, Any]:
    """
    Handle API response with automatic error display and retry support.

    Args:
        success: Whether the API call succeeded
        data: The response data (if successful)
        error: Error message (if failed)
        is_retryable: Whether the error can be retried
        retry_callback: Function to call on retry
        retry_args: Args for retry_callback
        retry_kwargs: Kwargs for retry_callback
        key_suffix: Unique key suffix

    Returns:
        Tuple of (success, data) - data may be updated if retry succeeded

    Example:
        ```python
        from ui.api import make_request
        from ui.components.error_display import handle_api_response

        success, data, error, retryable = make_request("GET", "/models/instances")
        success, data = handle_api_response(
            success, data, error, retryable,
            retry_callback=lambda: make_request("GET", "/models/instances"),
            key_suffix="list_models"
        )
        if success:
            # Use data
            pass
        ```
    """
    if retry_kwargs is None:
        retry_kwargs = {}
    if success:
        return True, data

    # Display error with retry if applicable
    if is_retryable and retry_callback:
        retry_result = display_error_with_retry(
            error or "Unknown error",
            is_retryable=True,
            retry_callback=retry_callback,
            retry_args=retry_args,
            retry_kwargs=retry_kwargs,
            key_suffix=key_suffix,
        )

        # If retry returned a result, unpack it
        if retry_result:
            retry_success, retry_data, retry_error, _ = retry_result
            if retry_success:
                st.success("✅ Retry succeeded!")
                return True, retry_data
            else:
                st.error(f"Retry failed: {retry_error}")
                return False, None
    else:
        # Just display the error without retry option
        st.error(error or "Unknown error")

    return False, None


def display_transient_error_hint() -> None:
    """Display a helpful hint about transient errors."""
    st.info(
        "💡 **Transient errors** (5xx, timeouts, connection issues) can often be "
        "resolved by retrying. If the problem persists, check the API service health."
    )
