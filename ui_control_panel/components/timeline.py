"""
Timeline component for agent runs.
"""

from typing import Any

import streamlit as st


def render_timeline(events: list[dict[str, Any]]):
    """
    Render a timeline of events (tool calls, steps).

    Expected event format:
    {
        "type": "tool_call" | "step" | "error",
        "name": str,
        "timestamp": str,
        "duration_ms": int (optional),
        "input": dict (optional),
        "output": dict (optional),
        "error": str (optional)
    }
    """
    if not events:
        st.info("No timeline events yet")
        return

    for idx, event in enumerate(events):
        event_type = event.get("type", "unknown")
        name = event.get("name", "Unknown")
        timestamp = event.get("timestamp", "")
        duration = event.get("duration_ms")

        # Choose emoji based on type
        if event_type == "tool_call":
            emoji = "🔧"
        elif event_type == "step":
            emoji = "📍"
        elif event_type == "error":
            emoji = "❌"
        else:
            emoji = "•"

        # Create event card
        with st.container():
            st.markdown(f"### {emoji} {name}")

            cols = st.columns([3, 1])
            with cols[0]:
                if timestamp:
                    st.caption(f"⏰ {timestamp}")
            with cols[1]:
                if duration:
                    st.caption(f"⏱️ {duration}ms")

            # Show input/output in expander
            if "input" in event or "output" in event or "error" in event:
                with st.expander("Details", expanded=False):
                    if "input" in event:
                        st.markdown("**Input:**")
                        st.json(event["input"], expanded=False)

                    if "output" in event:
                        st.markdown("**Output:**")
                        output = event["output"]

                        # Special handling for tabular data
                        if isinstance(output, dict) and "rows" in output:
                            st.markdown(f"*{len(output['rows'])} rows*")
                            if output["rows"]:
                                st.dataframe(output["rows"][:10])  # Show first 10
                        else:
                            st.json(output, expanded=False)

                    if "error" in event:
                        st.error(f"**Error:** {event['error']}")

            if idx < len(events) - 1:
                st.markdown("---")
