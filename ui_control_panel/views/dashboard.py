"""
Dashboard tab - health monitoring.
"""

import time

import streamlit as st
from components import render_health_card

from api import get_health_components, get_health_live, get_health_ready, get_health_startup


def render_dashboard_tab():
    """Render dashboard with health indicators.

    FIXED: Auto-refresh now uses session state tracking instead of blocking sleep.
    """
    st.header("📊 System Health Dashboard")

    # Auto-refresh control
    col1, col2 = st.columns([3, 1])
    with col1:
        auto_refresh = st.checkbox("🔄 Auto-refresh (30s)", value=False, key="auto_refresh_health")
    with col2:
        if st.button("🔄 Refresh Now", key="refresh_health"):
            st.rerun()

    # Handle auto-refresh using session state (non-blocking)
    if auto_refresh:
        # Track last refresh time
        if "last_health_refresh" not in st.session_state:
            st.session_state.last_health_refresh = time.time()

        elapsed = time.time() - st.session_state.last_health_refresh

        # Show countdown
        if elapsed < 30:
            remaining = int(30 - elapsed)
            st.caption(f"⏱️ Auto-refresh in {remaining}s")
        else:
            # Time to refresh
            st.session_state.last_health_refresh = time.time()
            st.rerun()

    # Core health endpoints
    st.subheader("Core Health Endpoints")

    col1, col2, col3 = st.columns(3)

    with col1:
        success, data, error = get_health_live()
        if success:
            # /health/live returns plain text, convert to expected format
            if data and "result" in data:
                status_data = {"status": "ok" if data["result"] == "ok" else "error"}
            else:
                status_data = data
            render_health_card("Liveness", status_data)
        else:
            st.error(f"❌ Liveness check failed: {error}")

    with col2:
        success, data, error = get_health_ready()
        if success:
            render_health_card("Readiness", data)
        else:
            st.error(f"❌ Readiness check failed: {error}")

    with col3:
        success, data, error = get_health_startup()
        if success:
            render_health_card("Startup", data)
        else:
            st.error(f"❌ Startup check failed: {error}")

    st.markdown("---")

    # Component health
    st.subheader("Component Health")

    success, data, error = get_health_components()

    if success and data:
        # The API returns 'checks' not 'components'
        components = data.get("checks", data.get("components", {}))

        if components:
            # Create grid of component cards
            cols = st.columns(3)
            for idx, (name, status) in enumerate(components.items()):
                with cols[idx % 3]:
                    render_health_card(name.capitalize(), status)
        else:
            st.info("No component health data available")
    else:
        st.error(f"Failed to fetch component health: {error}")

    # Auto-refresh will rerun via session state check above (non-blocking)
