"""
Tool card component.
"""

from typing import Any

import streamlit as st


def render_tool_card(tool: dict[str, Any]):
    """
    Render a card for a tool.

    Expected format:
    {
        "name": str,
        "description": str,
        "capabilities": List[str],
        "safe": bool (optional)
    }
    """
    name = tool.get("name", "Unknown")
    description = tool.get("description", "No description")
    capabilities = tool.get("capabilities", [])
    is_safe = tool.get("safe", False)

    with st.container():
        # Header with safety indicator
        header_cols = st.columns([4, 1])
        with header_cols[0]:
            st.markdown(f"### 🔧 {name}")
        with header_cols[1]:
            if is_safe:
                st.success("Safe")
            else:
                st.warning("Admin")

        # Description
        st.markdown(description)

        # Capabilities
        if capabilities:
            st.caption("**Capabilities:**")
            for cap in capabilities:
                st.markdown(f"- {cap}")
