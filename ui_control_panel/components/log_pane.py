"""
Log pane component.
"""

import os

import streamlit as st


def render_log_pane(title: str = "Application Logs", log_file: str = "logs/ui.log", max_lines: int = 100):
    """
    Render a log viewer pane.

    Args:
        log_file: Path to log file
        max_lines: Maximum number of lines to show
        filter_keywords: Optional list of keywords to filter by
    """
    st.markdown("### 📜 Logs")

    # Filter controls
    with st.expander("🔍 Filter Options"):
        filter_text = st.text_input("Filter by keyword", placeholder="e.g., error, auth, jobs")
        show_all = st.checkbox("Show all lines (ignore max)", value=False)

    if not os.path.exists(log_file):
        st.warning(f"Log file not found: {log_file}")
        return

    try:
        with open(log_file) as f:
            lines = f.readlines()

        # Apply filter
        if filter_text:
            keywords = [k.strip() for k in filter_text.split(",")]
            lines = [line for line in lines if any(k.lower() in line.lower() for k in keywords)]

        # Limit lines
        if not show_all:
            lines = lines[-max_lines:]

        # Display
        if lines:
            log_content = "".join(lines)
            st.text_area("Log Content", value=log_content, height=400, disabled=True, label_visibility="collapsed")
            st.caption(f"Showing {len(lines)} lines")
        else:
            st.info("No log entries match the filter")

    except Exception as e:
        st.error(f"Error reading log file: {e!s}")
