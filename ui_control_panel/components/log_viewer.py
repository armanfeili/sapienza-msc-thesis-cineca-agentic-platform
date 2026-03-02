"""
Redacted log viewer component with real-time tailing and filtering.
"""

import os
import re
from datetime import datetime
from pathlib import Path

import streamlit as st


def mask_token(text: str) -> str:
    """
    Mask tokens and sensitive data in log text.

    Args:
        text: Log text that may contain sensitive data

    Returns:
        Text with masked tokens
    """
    # Mask JWT tokens (eyJ...)
    text = re.sub(r"eyJ[A-Za-z0-9_-]*\.eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*", "eyJ...<REDACTED>", text)

    # Mask Bearer tokens
    text = re.sub(r"Bearer\s+[A-Za-z0-9_-]+", "Bearer <REDACTED>", text)

    # Mask Authorization headers
    text = re.sub(r'"Authorization":\s*"[^"]*"', '"Authorization": "<REDACTED>"', text)

    # Mask client secrets
    text = re.sub(
        r'(client_secret|password|secret)[\'"]?\s*[:=]\s*[\'"]?[^\'",\s}]+',
        r'\1": "<REDACTED>"',
        text,
        flags=re.IGNORECASE,
    )

    # Mask API keys
    text = re.sub(
        r'(api[_-]?key|apikey)[\'"]?\s*[:=]\s*[\'"]?[^\'",\s}]+', r'\1": "<REDACTED>"', text, flags=re.IGNORECASE
    )

    return text


def parse_log_line(line: str) -> dict[str, str] | None:
    """
    Parse a log line into components.

    Expected format: "2025-10-30 12:34:56 - component - LEVEL - message"

    Returns:
        Dict with timestamp, component, level, message or None if parse fails
    """
    # Try to match standard Python logging format
    match = re.match(
        r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:,\d{3})?)\s+-\s+([^\s]+)\s+-\s+(DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+-\s+(.*)",
        line,
    )

    if match:
        return {
            "timestamp": match.group(1),
            "component": match.group(2),
            "level": match.group(3),
            "message": match.group(4),
        }

    # Fallback: treat entire line as message
    return {"timestamp": "", "component": "unknown", "level": "INFO", "message": line}


def tail_log_file(
    file_path: str,
    num_lines: int = 100,
    level_filter: str | None = None,
    component_filter: str | None = None,
    search_term: str | None = None,
) -> list[str]:
    """
    Read last N lines from log file with filtering.

    Args:
        file_path: Path to log file
        num_lines: Number of lines to read from end
        level_filter: Only show logs at or above this level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        component_filter: Only show logs from this component
        search_term: Only show logs containing this term (case-insensitive)

    Returns:
        List of filtered log lines (masked)
    """
    if not os.path.exists(file_path):
        return [f"⚠️ Log file not found: {file_path}"]

    try:
        # Read last N lines
        with open(file_path, encoding="utf-8", errors="ignore") as f:
            # Use efficient tail algorithm
            lines = []
            f.seek(0, os.SEEK_END)
            file_size = f.tell()

            # Start from end and read backwards
            buffer_size = 8192
            lines_found = 0
            position = file_size

            while position > 0 and lines_found < num_lines:
                # Read chunk
                chunk_size = min(buffer_size, position)
                position -= chunk_size
                f.seek(position)
                chunk = f.read(chunk_size)

                # Split into lines and prepend to our list
                chunk_lines = chunk.split("\n")
                lines = chunk_lines + lines
                lines_found = len([l for l in lines if l.strip()])

            # Take last num_lines non-empty lines
            lines = [l for l in lines if l.strip()][-num_lines:]

        # Filter by level
        level_order = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if level_filter and level_filter in level_order:
            min_level_idx = level_order.index(level_filter)
            filtered_lines = []
            for line in lines:
                parsed = parse_log_line(line)
                if parsed:
                    level = parsed.get("level", "INFO")
                    if level in level_order and level_order.index(level) >= min_level_idx:
                        filtered_lines.append(line)
            lines = filtered_lines

        # Filter by component
        if component_filter:
            filtered_lines = []
            for line in lines:
                parsed = parse_log_line(line)
                if parsed and component_filter.lower() in parsed.get("component", "").lower():
                    filtered_lines.append(line)
            lines = filtered_lines

        # Filter by search term
        if search_term:
            lines = [l for l in lines if search_term.lower() in l.lower()]

        # Mask sensitive data
        lines = [mask_token(line) for line in lines]

        return lines

    except Exception as e:
        return [f"❌ Error reading log file: {e!s}"]


def get_log_files(log_dir: str = "logs") -> list[str]:
    """
    Get list of available log files.

    Args:
        log_dir: Directory containing log files

    Returns:
        List of log file paths
    """
    if not os.path.exists(log_dir):
        return []

    log_files = []
    for file in Path(log_dir).glob("*.log"):
        log_files.append(str(file))

    return sorted(log_files)


def render_log_viewer(default_log_file: str = "logs/ui.log") -> None:
    """
    Render interactive log viewer component.

    Args:
        default_log_file: Default log file to display
    """
    st.subheader("📜 Log Viewer")

    # Get available log files
    log_files = get_log_files()

    if not log_files:
        st.warning("⚠️ No log files found in logs/ directory")
        return

    # File selector
    col1, col2 = st.columns([3, 1])

    with col1:
        selected_file = st.selectbox(
            "Select Log File",
            options=log_files,
            index=log_files.index(default_log_file) if default_log_file in log_files else 0,
            key="log_file_selector",
        )

    with col2:
        auto_refresh = st.checkbox(
            "🔄 Auto-refresh", value=False, help="Refresh logs every 5 seconds", key="log_auto_refresh"
        )

    # Filters
    filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)

    with filter_col1:
        num_lines = st.slider("Lines to show", min_value=10, max_value=500, value=100, step=10, key="log_num_lines")

    with filter_col2:
        level_filter = st.selectbox(
            "Min Level",
            options=["ALL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            index=2,  # Default to INFO
            key="log_level_filter",
        )

    with filter_col3:
        component_filter = st.text_input("Component", placeholder="e.g., api, ui", key="log_component_filter")

    with filter_col4:
        search_term = st.text_input("Search", placeholder="Search logs...", key="log_search_term")

    # Fetch and display logs
    level = None if level_filter == "ALL" else level_filter
    component = component_filter if component_filter.strip() else None
    search = search_term if search_term.strip() else None

    log_lines = tail_log_file(
        selected_file, num_lines=num_lines, level_filter=level, component_filter=component, search_term=search
    )

    # Display log stats
    info_col1, info_col2, info_col3 = st.columns(3)
    with info_col1:
        st.metric("Total Lines", len(log_lines))
    with info_col2:
        errors = sum(1 for line in log_lines if "ERROR" in line or "CRITICAL" in line)
        st.metric("Errors", errors, delta=None if errors == 0 else "⚠️")
    with info_col3:
        warnings = sum(1 for line in log_lines if "WARNING" in line)
        st.metric("Warnings", warnings)

    # Display logs in code block
    st.markdown("### Log Output")

    if log_lines:
        # Color-code log levels
        log_text = "\n".join(log_lines)
        st.code(log_text, language="log", line_numbers=True)

        # Download button
        st.download_button(
            label="📥 Download Filtered Logs",
            data=log_text,
            file_name=f"filtered_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
            mime="text/plain",
            key="download_filtered_logs",
        )
    else:
        st.info("ℹ️ No logs match the current filters")

    # Auto-refresh logic
    if auto_refresh:
        import time

        time.sleep(5)
        st.rerun()


def render_compact_log_viewer(log_file: str = "logs/ui.log", num_lines: int = 20, height: int = 300) -> None:
    """
    Render a compact log viewer for use in dashboards.

    Args:
        log_file: Log file to display
        num_lines: Number of recent lines to show
        height: Height of the log container in pixels
    """
    st.markdown("**Recent Logs**")

    log_lines = tail_log_file(log_file, num_lines=num_lines)

    if log_lines:
        log_text = "\n".join(log_lines)
        st.text_area("", value=log_text, height=height, key=f"compact_log_{log_file}", label_visibility="collapsed")
    else:
        st.info("No recent logs")
