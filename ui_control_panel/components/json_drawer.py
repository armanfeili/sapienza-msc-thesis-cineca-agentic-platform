"""
JSON drawer component.
"""

import json
from typing import Any

import streamlit as st


def sanitize_response(data: Any) -> Any:
    """Sanitize response data by masking sensitive fields."""
    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            # Mask tokens and secrets
            if any(sensitive in key.lower() for sensitive in ["token", "secret", "password", "key", "auth"]):
                if isinstance(value, str) and len(value) > 20:
                    sanitized[key] = f"{value[:8]}...{value[-8:]}"
                else:
                    sanitized[key] = "***"
            else:
                sanitized[key] = sanitize_response(value)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_response(item) for item in data]
    else:
        return data


def render_json_drawer(data: Any, title: str = "Response Data", show_curl: bool = True, curl_command: str = ""):
    """
    Render a JSON viewer with sanitization and copy options.

    Args:
        data: Data to display
        title: Drawer title
        show_curl: Show curl copy button
        curl_command: Pre-built curl command
    """
    with st.expander(f"🔍 {title}", expanded=False):
        # Sanitize data
        sanitized = sanitize_response(data)

        # Display JSON
        st.json(sanitized, expanded=True)

        # Copy buttons
        col1, col2 = st.columns(2)

        with col1:
            # Copy JSON
            json_str = json.dumps(sanitized, indent=2)
            st.download_button(
                label="📋 Copy JSON",
                data=json_str,
                file_name="response.json",
                mime="application/json",
                key=f"copy_json_{hash(json_str)}",
            )

        with col2:
            # Copy curl
            if show_curl and curl_command:
                st.download_button(
                    label="📋 Copy cURL",
                    data=curl_command,
                    file_name="request.sh",
                    mime="text/plain",
                    key=f"copy_curl_{hash(curl_command)}",
                )
