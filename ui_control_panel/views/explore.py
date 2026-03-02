"""
Explore tab - API explorer and root endpoints.
"""

import json
from typing import Any

import streamlit as st
from components import render_json_drawer

from api import get_openapi_spec, get_root


def nl_to_cypher(nl_query: str) -> tuple[bool, dict[str, Any] | None, str | None]:
    """
    Convert natural language query to Cypher query.

    Args:
        nl_query: Natural language query string

    Returns:
        Tuple of (success, data, error) where data contains cypher and explanation
    """
    # Simple pattern matching for demonstration
    # In production, this would use an LLM or NL-to-Cypher model
    nl_lower = nl_query.lower()

    patterns = {
        "show all users": {"cypher": "MATCH (u:User) RETURN u", "explanation": "Lists all User nodes"},
        "show all jobs": {"cypher": "MATCH (j:Job) RETURN j", "explanation": "Lists all Job nodes"},
        "show all agents": {"cypher": "MATCH (a:Agent) RETURN a", "explanation": "Lists all Agent nodes"},
        "count users": {"cypher": "MATCH (u:User) RETURN count(u) as count", "explanation": "Counts total User nodes"},
        "count jobs": {"cypher": "MATCH (j:Job) RETURN count(j) as count", "explanation": "Counts total Job nodes"},
    }

    # Try exact match first
    for pattern, result in patterns.items():
        if pattern in nl_lower:
            return True, result, None

    # No match found
    return False, None, "Could not convert query to Cypher. Try: 'show all users', 'show all jobs', 'count users', etc."


def render_explore_tab():
    """Render explore tab with API information."""
    st.header("🔍 API Explorer")

    # Root endpoint
    st.subheader("API Root")

    if st.button("🏠 Fetch Root Info", key="fetch_root"):
        success, data, error = get_root()

        if success and data:
            # Show version banner
            version = data.get("version", "unknown")
            api_name = data.get("name", "Cineca Agentic Platform")

            st.success(f"✅ {api_name} - Version {version}")

            # Show full response
            render_json_drawer(data, title="Root Response")
        else:
            st.error(f"Failed to fetch root: {error}")

    st.markdown("---")

    # OpenAPI spec
    st.subheader("OpenAPI Specification")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("📥 View OpenAPI Spec", key="view_openapi"):
            success, data, error = get_openapi_spec()

            if success and data:
                st.success("✅ OpenAPI spec fetched")

                # Show basic info
                info = data.get("info", {})
                st.markdown(f"**Title:** {info.get('title', 'N/A')}")
                st.markdown(f"**Version:** {info.get('version', 'N/A')}")
                st.markdown(f"**Description:** {info.get('description', 'N/A')}")

                # Show paths count
                paths = data.get("paths", {})
                st.metric("Total Endpoints", len(paths))

                # Full spec in drawer
                render_json_drawer(data, title="Full OpenAPI Specification")
            else:
                st.error(f"Failed to fetch spec: {error}")

    with col2:
        if st.button("📥 Download Spec", key="download_openapi"):
            success, data, error = get_openapi_spec()

            if success and data:
                spec_json = json.dumps(data, indent=2)
                st.download_button(
                    label="💾 Save openapi.json",
                    data=spec_json,
                    file_name="openapi.json",
                    mime="application/json",
                    key="download_openapi_file",
                )

    st.markdown("---")

    # Raw request inspector
    st.subheader("Raw Request Inspector")

    st.info("🔒 **Security:** Only paths under `/v1/*` are allowed to prevent SSRF attacks.", icon="ℹ️")

    method = st.selectbox("Method", ["GET", "POST", "PUT", "PATCH", "DELETE"], key="inspector_method")
    endpoint_input = st.text_input(
        "Endpoint Path",
        placeholder="health/live (will be normalized to /v1/health/live)",
        help="Enter path without base URL. /v1 prefix will be added automatically if missing.",
        key="inspector_endpoint",
    )

    if method in ["POST", "PUT", "PATCH"]:
        body = st.text_area(
            "Request Body (JSON)",
            placeholder='{"key": "value"}',
            help="Enter valid JSON. Max 1MB.",
            key="inspector_body",
        )
    else:
        body = None

    # Show resolved information before sending
    if endpoint_input:
        from state import get_active_token

        from api import get_api_base, is_safe_path, normalize_endpoint

        try:
            normalized = normalize_endpoint(endpoint_input)
            is_safe = is_safe_path(normalized)
            base_url = get_api_base()
            full_url = f"{base_url}{normalized}"

            # Show resolved URL
            col1, col2 = st.columns(2)
            with col1:
                if is_safe:
                    st.success(f"✅ **Resolved URL:** `{full_url}`")
                else:
                    st.error(f"❌ **Invalid path:** `{normalized}` - Only /v1/* paths allowed")

            # Show active identity
            with col2:
                token = get_active_token()
                if token:
                    identity_info = f"{token.subject} ({len(token.scopes)} scopes)"
                    st.info(f"🔑 **Active Identity:** {identity_info}")
                else:
                    st.warning("⚠️ **No active token** - Request will be unauthenticated")
        except Exception as e:
            st.error(f"Error normalizing path: {e!s}")

    if st.button("Send Request", key="send_inspector_request", disabled=not endpoint_input):
        import json as json_lib

        from api import get_api_base, is_safe_path, make_request, normalize_endpoint

        try:
            # Normalize and validate endpoint
            normalized = normalize_endpoint(endpoint_input)
            if not is_safe_path(normalized):
                st.error("❌ Invalid endpoint - Only /v1/* paths are allowed for security.")
                return

            # Validate and parse body
            request_data = None
            if body:
                # Content-length guard (1MB max)
                if len(body) > 1_000_000:
                    st.error("❌ Request body too large (max 1MB)")
                    return

                try:
                    request_data = json_lib.loads(body)
                except json_lib.JSONDecodeError as e:
                    st.error(f"❌ Invalid JSON: {e!s}")
                    return

            # Generate cURL command (with redacted auth)
            base_url = get_api_base()
            full_url = f"{base_url}{normalized}"

            curl_parts = [f"curl -X {method}"]
            curl_parts.append(f"'{full_url}'")
            curl_parts.append("-H 'Content-Type: application/json'")

            # Add redacted auth header if token exists
            token = get_active_token()
            if token:
                curl_parts.append("-H 'Authorization: Bearer <REDACTED>'")

            if request_data:
                json_str = json_lib.dumps(request_data)
                curl_parts.append(f"-d '{json_str}'")

            curl_command = " \\\n  ".join(curl_parts)

            # Show cURL with copy button
            with st.expander("📋 Copy as cURL"):
                st.code(curl_command, language="bash")
                st.caption("⚠️ Auth token is redacted for security")

            # Make request
            success, response, error, _ = make_request(method, normalized, data=request_data)

            if success:
                st.success("✅ Request successful")
                render_json_drawer(response, title="Response")
            else:
                st.error(f"❌ Request failed: {error}")
        except Exception as e:
            st.error(f"Error: {e!s}")
