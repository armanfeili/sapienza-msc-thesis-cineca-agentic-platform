"""
Health status card component.
"""

from typing import Any

import streamlit as st


def render_health_card(name: str, status: dict[str, Any] | None = None):
    """
    Render a health status card for a component.

    Args:
        name: Component name
        status: Health status dict with 'status' and optional 'latency_ms'
    """
    if status is None:
        st.error(f"❌ **{name}**: No data")
        return

    health_status = status.get("status", "unknown")
    latency = status.get("latency_ms")

    # Choose emoji and color based on status
    if health_status in {"healthy", "ok"}:
        emoji = "✅"
    elif health_status == "degraded":
        emoji = "⚠️"
    elif health_status in {"unhealthy", "error"}:
        emoji = "❌"
    else:
        emoji = "❓"

    # Build card content
    with st.container():
        cols = st.columns([3, 1])
        with cols[0]:
            st.markdown(f"{emoji} **{name}**")
        with cols[1]:
            if latency:
                st.caption(f"{latency}ms")

        # Additional details if available
        if "message" in status:
            st.caption(status["message"])

        # Show version or other metadata
        if "version" in status:
            st.caption(f"Version: {status['version']}")
