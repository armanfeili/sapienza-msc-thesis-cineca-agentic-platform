"""
Tools tab - tool discovery and invocation with schema-driven forms.
"""

import json
import time
from typing import Any

import streamlit as st
from components import (
    check_tool_access,
    render_json_drawer,
    render_scope_chips,
)

from api import get_tool_invocation, get_tool_schema, invoke_tool, list_tools


def _get_required_scopes_for_tool(capabilities: list) -> list:
    """
    Determine required scopes based on tool capabilities.

    Args:
        capabilities: List of tool capabilities

    Returns:
        List of required scopes
    """
    restricted_caps = {"writes_db", "model_management", "admin"}

    # If tool has restricted capabilities, require admin or full tool access
    if any(cap in restricted_caps for cap in capabilities):
        return ["tools:invoke:all", "admin:all"]

    # Otherwise, basic tool access is sufficient
    return ["tools:invoke:basic", "tools:invoke:all"]


def render_tools_tab():
    """Render tools tab with discovery and schema-driven invocation."""
    st.header("🔧 Tools")

    # Tool management tabs
    tool_tabs = st.tabs(["🔍 Discover Tools", "🚀 Invoke Tool", "🧪 Test All Tools"])

    with tool_tabs[0]:
        _render_tool_discovery()

    with tool_tabs[1]:
        _render_tool_invocation()

    with tool_tabs[2]:
        _render_test_all_tools()


def _render_tool_discovery():
    """Render tool discovery with filters."""
    st.subheader("Discover Available Tools")

    # Filters
    filter_cols = st.columns([2, 2, 1])

    with filter_cols[0]:
        capability_filter = st.multiselect(
            "⚡ Filter by Capabilities",
            options=["reads_db", "writes_db", "llm_powered", "model_management", "system", "admin"],
            key="tool_capability_filter",
            help="Filter tools by their capabilities",
        )

    with filter_cols[1]:
        search_query = st.text_input(
            "🔎 Search Tools", placeholder="e.g., health, cypher, memory", key="tool_search_query"
        )

    with filter_cols[2]:
        if st.button("🔄 Refresh", key="refresh_tools"):
            st.rerun()

    # Fetch tools
    success, data, error = list_tools()

    if not success or not data:
        st.error(f"❌ Failed to load tools: {error}")
        return

    tools = data.get("items", [])

    if not tools:
        st.info("📭 No tools available")
        return

    # Filter out DEBUG tools unless developer mode is on
    from state import get_state

    state = get_state()

    if not state.developer_mode:
        tools = [
            t
            for t in tools
            if "debug" not in t.get("name", "").lower()
            and "debug" not in [cap.lower() for cap in t.get("capabilities", [])]
        ]

    # Apply user filters
    filtered_tools = tools

    if capability_filter:
        filtered_tools = [
            t for t in filtered_tools if any(cap in t.get("capabilities", []) for cap in capability_filter)
        ]

    if search_query:
        query_lower = search_query.lower()
        filtered_tools = [
            t
            for t in filtered_tools
            if query_lower in t.get("name", "").lower() or query_lower in t.get("description", "").lower()
        ]

    # Display count
    st.caption(f"Showing {len(filtered_tools)} of {len(tools)} tools")

    # Display tools
    if filtered_tools:
        for tool in filtered_tools:
            _render_tool_discovery_card(tool)
    else:
        st.info("🔍 No tools match your filters")


def _render_tool_discovery_card(tool: dict):
    """Render a single tool discovery card.

    FIXED: Uses static container key to prevent duplicate rendering.
    """
    # Use static key based on tool name to prevent duplicates
    tool_name = tool.get("name", "unknown")
    container_key = f"tool_card_{tool_name}"

    with st.container(key=container_key):
        col1, col2 = st.columns([3, 1])

        with col1:
            st.markdown(f"### 🔧 {tool.get('name', 'Unknown')}")
            st.caption(tool.get("description", "No description"))

            # Capabilities badges
            capabilities = tool.get("capabilities", [])
            if capabilities:
                cap_str = " • ".join([f"`{cap}`" for cap in capabilities])
                st.markdown(f"**Capabilities:** {cap_str}")

        with col2:
            # Show required scopes
            required_scopes = _get_required_scopes_for_tool(capabilities)

            if required_scopes:
                st.markdown("**Required:**")
                render_scope_chips(required_scopes[:2], show_status=True)  # Show first 2

            # Check access
            has_access = check_tool_access(capabilities)
            if not has_access:
                st.caption("🔒 Insufficient permissions")
            # Quick invoke button
            elif st.button("⚡ Invoke", key=f"quick_invoke_{tool.get('name')}", type="secondary"):
                st.session_state.selected_tool_for_invoke = tool.get("name")
                st.session_state.active_tool_tab = 1  # Switch to invoke tab
                st.rerun()

        # Expandable schema
        with st.expander(f"📋 View Schema: {tool.get('name')}"):
            _display_tool_schema_inline(tool.get("name"))

        st.markdown("---")


def _display_tool_schema_inline(tool_name: str):
    """Display tool schema inline in an expander."""
    success, schema_data, error = get_tool_schema(tool_name)

    if success and schema_data:
        # Description
        desc = schema_data.get("description", "N/A")
        st.markdown(f"**Description:** {desc}")

        # Capabilities
        capabilities = schema_data.get("capabilities", [])
        if capabilities:
            st.markdown("**Capabilities:**")
            for cap in capabilities:
                st.markdown(f"- ⚡ {cap}")

        # Parameters schema
        params_schema = schema_data.get("parameters", {})
        if params_schema:
            st.markdown("**Parameters:**")
            st.json(params_schema)
        else:
            st.info("No parameters required")

        # Full schema in JSON drawer
        render_json_drawer(schema_data, title="Full Tool Schema")
    else:
        st.error(f"❌ Failed to load schema: {error}")


def _render_tool_invocation():
    """Render schema-driven tool invocation interface."""
    st.subheader("Invoke Tool with Schema-Driven Form")

    # Tool selector
    success, data, error = list_tools()

    if not success or not data:
        st.error(f"❌ Failed to load tools: {error}")
        return

    tools = data.get("items", [])

    if not tools:
        st.info("📭 No tools available")
        return

    # Filter out DEBUG tools unless developer mode is on
    from state import get_state

    state = get_state()

    if not state.developer_mode:
        tools = [
            t
            for t in tools
            if "debug" not in t.get("name", "").lower()
            and "debug" not in [cap.lower() for cap in t.get("capabilities", [])]
        ]

    # Create tool selector
    tool_options = {
        f"{t.get('name')} - {t.get('description', 'No description')[:50]}...": t.get("name")
        for t in tools
        if t.get("name")
    }

    # Check if coming from quick invoke
    default_index = 0
    selected_tool_from_state = st.session_state.get("selected_tool_for_invoke")
    if selected_tool_from_state:
        # FIXED: Don't mutate session_state during render - check but don't pop
        for idx, (_key, value) in enumerate(tool_options.items()):
            if value == selected_tool_from_state:
                default_index = idx
                break
        # Clear after setting index (only if button was clicked)
        if "selected_tool_for_invoke_processed" not in st.session_state:
            st.session_state.selected_tool_for_invoke_processed = True
            # Clear it for next render cycle
            st.session_state.pop("selected_tool_for_invoke", None)

    selected_key = st.selectbox(
        "Select Tool to Invoke", options=list(tool_options.keys()), index=default_index, key="tool_invoke_selector"
    )

    selected_tool_name = tool_options[selected_key]

    if not selected_tool_name:
        return

    st.markdown("---")

    # Fetch schema and render dynamic form
    _render_schema_driven_form(selected_tool_name)


def _render_schema_driven_form(tool_name: str):
    """Render a dynamic form based on tool schema."""
    success, schema_data, error = get_tool_schema(tool_name)

    if not success or not schema_data:
        st.error(f"❌ Failed to load schema: {error}")
        return

    st.markdown(f"### 🔧 {tool_name}")
    st.caption(schema_data.get("description", "No description"))

    # Check permissions
    capabilities = schema_data.get("capabilities", [])
    has_access = check_tool_access(capabilities)

    if not has_access:
        st.error("🔒 You don't have permission to invoke this tool")
        required_scopes = _get_required_scopes_for_tool(capabilities)
        st.markdown("**Required scopes:**")
        render_scope_chips(required_scopes, show_status=True)
        return

    # Parameters schema
    params_schema = schema_data.get("parameters", {})

    if not params_schema:
        st.info("ℹ️ This tool requires no parameters")

        # Simple invoke button
        if st.button(f"🚀 Invoke {tool_name}", key=f"invoke_no_params_{tool_name}", type="primary"):
            _execute_tool_invocation(tool_name, {})
        return

    # Render dynamic form based on schema
    st.markdown("#### Parameters")

    with st.form(f"invoke_form_{tool_name}"):
        form_data = _render_dynamic_parameter_form(params_schema)

        submitted = st.form_submit_button(f"🚀 Invoke {tool_name}", type="primary")

        if submitted:
            _execute_tool_invocation(tool_name, form_data)


def _render_dynamic_parameter_form(params_schema: dict) -> dict[str, Any]:
    """
    Render dynamic form fields based on JSON schema.

    Args:
        params_schema: JSON schema for parameters

    Returns:
        Dictionary of form field values
    """
    form_data = {}

    # Handle JSON Schema format
    params_schema.get("type", "object")
    properties = params_schema.get("properties", {})
    required_fields = params_schema.get("required", [])

    if not properties:
        # No structured parameters, show JSON textarea
        st.info("No structured parameters defined. Use JSON input below:")
        json_input = st.text_area("Parameters (JSON)", value="{}", height=150, key="manual_params_json")

        try:
            return json.loads(json_input) if json_input.strip() else {}
        except json.JSONDecodeError:
            st.error("Invalid JSON")
            return {}

    # Render field for each property
    for param_name, param_spec in properties.items():
        is_required = param_name in required_fields
        label = f"{param_name}{'*' if is_required else ''}"

        param_type = param_spec.get("type", "string")
        description = param_spec.get("description", "")
        default_value = param_spec.get("default")
        enum_values = param_spec.get("enum")

        # Render appropriate widget based on type
        if enum_values:
            # Dropdown for enum
            value = st.selectbox(
                label,
                options=enum_values,
                index=0
                if default_value is None
                else enum_values.index(default_value)
                if default_value in enum_values
                else 0,
                help=description,
                key=f"param_{param_name}",
            )
        elif param_type == "boolean":
            value = st.checkbox(
                label,
                value=default_value if default_value is not None else False,
                help=description,
                key=f"param_{param_name}",
            )
        elif param_type == "integer":
            min_val = param_spec.get("minimum", 0)
            max_val = param_spec.get("maximum", 1000000)
            value = st.number_input(
                label,
                min_value=min_val,
                max_value=max_val,
                value=default_value if default_value is not None else min_val,
                step=1,
                help=description,
                key=f"param_{param_name}",
            )
        elif param_type == "number":
            min_val = param_spec.get("minimum", 0.0)
            max_val = param_spec.get("maximum", 1000000.0)
            value = st.number_input(
                label,
                min_value=min_val,
                max_value=max_val,
                value=default_value if default_value is not None else min_val,
                step=0.1,
                help=description,
                key=f"param_{param_name}",
            )
        elif param_type == "array":
            # Text area for array input
            default_str = json.dumps(default_value) if default_value else "[]"
            value_str = st.text_area(
                label, value=default_str, help=f"{description} (JSON array)", key=f"param_{param_name}"
            )
            try:
                value = json.loads(value_str)
            except:
                st.error(f"Invalid JSON for {param_name}")
                value = []
        elif param_type == "object":
            # Text area for object input
            default_str = json.dumps(default_value, indent=2) if default_value else "{}"
            value_str = st.text_area(
                label, value=default_str, help=f"{description} (JSON object)", height=100, key=f"param_{param_name}"
            )
            try:
                value = json.loads(value_str)
            except:
                st.error(f"Invalid JSON for {param_name}")
                value = {}
        else:
            # Default to text input for string
            value = st.text_input(
                label,
                value=default_value if default_value is not None else "",
                help=description,
                key=f"param_{param_name}",
            )

        # Only include if required or has value
        if is_required or value not in [None, "", [], {}]:
            form_data[param_name] = value

    return form_data


def _execute_tool_invocation(tool_name: str, params: dict):
    """Execute tool invocation and poll for results."""
    st.markdown("---")
    st.markdown("### 🔄 Execution Status")

    # Invoke tool
    with st.spinner(f"Invoking {tool_name}..."):
        success, data, error = invoke_tool(tool_name, params)

    if not success or not data:
        st.error(f"❌ Invocation failed: {error}")
        return

    eid = data.get("execution_id")

    if not eid:
        st.error("❌ No execution ID returned")
        return

    st.success("✅ Tool invoked successfully")
    st.info(f"**Execution ID:** `{eid}`")

    # Poll for results
    _poll_for_execution_result(tool_name, eid)


def _poll_for_execution_result(tool_name: str, eid: str, max_attempts: int = 10):
    """Poll for tool execution result with progress indicator."""
    st.markdown("#### ⏳ Waiting for execution result...")

    progress_bar = st.progress(0)
    status_text = st.empty()

    for attempt in range(max_attempts):
        progress = (attempt + 1) / max_attempts
        progress_bar.progress(progress)
        status_text.text(f"Attempt {attempt + 1}/{max_attempts}...")

        success, result_data, error = get_tool_invocation(tool_name, eid)

        if success and result_data:
            status = result_data.get("status", "unknown")

            if status == "completed":
                progress_bar.progress(1.0)
                status_text.text("✅ Execution completed!")
                _display_execution_result(result_data)
                return
            elif status == "failed":
                progress_bar.progress(1.0)
                status_text.text("❌ Execution failed")
                st.error(f"Execution failed: {result_data.get('error', 'Unknown error')}")
                _display_execution_result(result_data)
                return
            elif status in ["pending", "running"]:
                # Continue polling
                time.sleep(1)
                continue

        # Error fetching result
        if not success:
            st.warning(f"⚠️ Could not fetch result (attempt {attempt + 1}): {error}")
            time.sleep(1)

    # Timeout
    progress_bar.progress(1.0)
    status_text.text("⚠️ Polling timeout")
    st.warning(f"⚠️ Execution did not complete within {max_attempts} seconds. Check manually with EID: `{eid}`")


def _display_execution_result(result_data: dict):
    """Display tool execution result with appropriate formatting."""
    st.markdown("---")
    st.markdown("### 📊 Execution Result")

    # Show execution metadata
    col1, col2, col3 = st.columns(3)

    with col1:
        status = result_data.get("status", "unknown")
        status_emoji = "✅" if status == "completed" else "❌" if status == "failed" else "⏳"
        st.metric("Status", f"{status_emoji} {status}")

    with col2:
        duration_ms = result_data.get("duration_ms", 0)
        st.metric("Duration", f"{duration_ms}ms")

    with col3:
        timestamp = result_data.get("completed_at", result_data.get("started_at", "N/A"))
        st.metric("Timestamp", timestamp[:19] if isinstance(timestamp, str) else "N/A")

    # Check for NL→Cypher result
    if "cypher" in result_data or "query" in result_data:
        _display_cypher_result(result_data)
        return

    # Check for tabular result
    output = result_data.get("output", result_data.get("result", {}))

    if isinstance(output, dict) and "rows" in output:
        _display_tabular_result(output)
        return

    # General result display
    if output:
        st.markdown("**Output:**")

        if isinstance(output, (dict, list)):
            st.json(output)

            # Export options
            col1, col2 = st.columns(2)
            with col1:
                json_str = json.dumps(output, indent=2)
                st.download_button(
                    "📥 Export JSON",
                    json_str,
                    f"tool_result_{result_data.get('execution_id', 'unknown')}.json",
                    "application/json",
                )
        else:
            st.info(str(output))

    # Show full result in drawer
    render_json_drawer(result_data, title="Full Execution Result")


def _display_tabular_result(output: dict):
    """Display tabular result with export options."""
    rows = output.get("rows", [])

    if not rows:
        st.info("No rows returned")
        return

    st.markdown(f"**Results ({len(rows)} rows):**")

    import pandas as pd

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True)

    # Export options
    col1, col2 = st.columns(2)

    with col1:
        csv = df.to_csv(index=False)
        st.download_button("📥 Export CSV", csv, "tool_result.csv", "text/csv")

    with col2:
        json_str = json.dumps(rows, indent=2)
        st.download_button("📥 Export JSON", json_str, "tool_result.json", "application/json")


def _display_cypher_result(result: dict):
    """Display NL→Cypher result with query and table."""
    st.markdown("### 🔍 NL→Cypher Result")

    # Show generated Cypher
    cypher_query = result.get("cypher") or result.get("query", "")
    if cypher_query:
        st.markdown("**Generated Cypher Query:**")
        st.code(cypher_query, language="cypher")

    # Show parameters
    params = result.get("parameters", {})
    if params:
        st.markdown("**Parameters:**")
        st.json(params)

    # Show enforcement info
    if result.get("read_only_enforced"):
        st.info("✅ Read-only enforcement active")

    # Show row limit
    row_limit = result.get("row_limit")
    if row_limit:
        st.caption(f"Row limit: {row_limit}")

    # Show results table
    rows = result.get("rows", [])
    if rows:
        st.markdown(f"**Results ({len(rows)} rows):**")

        import pandas as pd

        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True)

        # Export
        col1, col2 = st.columns(2)
        with col1:
            csv = df.to_csv(index=False)
            st.download_button("📥 Export CSV", csv, "memgraph_results.csv", "text/csv")

        with col2:
            json_str = json.dumps(rows, indent=2)
            st.download_button("📥 Export JSON", json_str, "memgraph_results.json", "application/json")
    else:
        st.info("No rows returned")

    # Show any warnings or errors
    if "unsafe_reason" in result:
        st.error(f"⚠️ Unsafe query blocked: {result['unsafe_reason']}")


def _render_test_all_tools():
    """Render bulk tool testing interface for admin validation."""
    st.subheader("🧪 Test All Tools")

    st.info(
        """
    **Bulk Tool Testing** - Validate all available tools with test payloads.

    This feature helps administrators quickly verify that all tools are functioning correctly.
    Each tool will be invoked with minimal test parameters.
    """
    )

    # Admin scope gate
    from components import render_scope_gate

    if not render_scope_gate(
        required_scopes=["admin:all", "admin:*"], mode="any", custom_message="Bulk tool testing requires admin access"
    ):
        return

    # Configuration options
    config_cols = st.columns([2, 2, 1])

    with config_cols[0]:
        test_mode = st.selectbox(
            "Test Mode", options=["Safe Tools Only", "All Tools (including writes)"], help="Choose which tools to test"
        )

    with config_cols[1]:
        concurrent = st.checkbox(
            "Concurrent Execution", value=False, help="Run tests in parallel (faster but harder to debug)"
        )

    with config_cols[2]:
        timeout_sec = st.number_input(
            "Timeout (s)", min_value=5, max_value=120, value=30, help="Maximum time per tool invocation"
        )

    # Start button
    if st.button("▶️ Run Tests", type="primary", use_container_width=True):
        _execute_tool_tests(test_mode, concurrent, timeout_sec)


def _execute_tool_tests(test_mode: str, concurrent: bool, timeout_sec: int):
    """Execute tool tests and display results."""

    # Fetch all tools
    success, data, error = list_tools()

    if not success or not data:
        st.error(f"❌ Failed to fetch tools: {error or 'Unknown error'}")
        return

    tools = data.get("tools", [])
    if not tools:
        st.warning("No tools found to test")
        return

    # Filter tools based on test mode
    if test_mode == "Safe Tools Only":
        restricted_caps = {"writes_db", "model_management", "admin"}
        tools = [t for t in tools if not any(cap in restricted_caps for cap in t.get("capabilities", []))]

    st.markdown(f"**Testing {len(tools)} tools...**")

    # Progress tracking
    progress_bar = st.progress(0)
    status_text = st.empty()

    # Results storage
    results = {"success": [], "failed": [], "timeout": [], "total": len(tools)}

    # Test each tool
    for idx, tool in enumerate(tools):
        tool_name = tool.get("name", "unknown")
        status_text.text(f"Testing {idx + 1}/{len(tools)}: {tool_name}")

        # Get test payload
        test_payload = _get_test_payload_for_tool(tool)

        # Invoke tool
        start_time = time.time()
        success, data, error = invoke_tool(tool_name, test_payload)
        elapsed = time.time() - start_time

        # Check timeout
        if elapsed > timeout_sec:
            results["timeout"].append({"tool": tool_name, "elapsed": elapsed, "error": "Timeout exceeded"})
        elif success:
            results["success"].append({"tool": tool_name, "elapsed": elapsed, "output": data})
        else:
            results["failed"].append({"tool": tool_name, "elapsed": elapsed, "error": error or "Unknown error"})

        # Update progress
        progress_bar.progress((idx + 1) / len(tools))

        # Small delay to avoid overwhelming the server
        if not concurrent:
            time.sleep(0.1)

    status_text.text("✅ Testing complete")
    progress_bar.progress(1.0)

    # Display results
    _display_test_results(results)


def _get_test_payload_for_tool(tool: dict) -> dict[str, Any]:
    """Generate minimal test payload for a tool."""
    tool_name = tool.get("name", "")

    # Known test payloads for specific tools
    test_payloads = {
        "health.components": {},
        "health.deep": {},
        "list_providers": {},
        "list_tools": {},
        "list_tenants": {},
        "list_processes": {},
        "list_sessions": {},
        "list_jobs": {},
        "get_db_counts": {},
        "memgraph.schema": {},
        "memgraph.stats": {},
        # Add more specific test payloads as needed
    }

    # Return known payload or empty dict
    return test_payloads.get(tool_name, {})


def _display_test_results(results: dict):
    """Display test results in a formatted view."""

    # Summary metrics
    total = results["total"]
    success_count = len(results["success"])
    failed_count = len(results["failed"])
    timeout_count = len(results["timeout"])

    st.markdown("---")
    st.markdown("### 📊 Test Summary")

    # Metrics row
    metric_cols = st.columns(4)

    with metric_cols[0]:
        st.metric("Total Tools", total)

    with metric_cols[1]:
        st.metric("✅ Passed", success_count, delta=f"{(success_count/total)*100:.1f}%")

    with metric_cols[2]:
        st.metric("❌ Failed", failed_count, delta=f"{(failed_count/total)*100:.1f}%")

    with metric_cols[3]:
        st.metric("⏱️ Timeout", timeout_count, delta=f"{(timeout_count/total)*100:.1f}%")

    # Detailed results in tabs
    result_tabs = st.tabs(["✅ Passed", "❌ Failed", "⏱️ Timeout"])

    with result_tabs[0]:
        if results["success"]:
            st.markdown(f"**{len(results['success'])} tools passed testing:**")

            for result in results["success"]:
                with st.expander(f"✅ {result['tool']} ({result['elapsed']:.2f}s)"):
                    st.json(result["output"])
        else:
            st.info("No tools passed")

    with result_tabs[1]:
        if results["failed"]:
            st.markdown(f"**{len(results['failed'])} tools failed:**")

            for result in results["failed"]:
                with st.expander(f"❌ {result['tool']} ({result['elapsed']:.2f}s)"):
                    st.error(result["error"])
        else:
            st.success("No failures! 🎉")

    with result_tabs[2]:
        if results["timeout"]:
            st.markdown(f"**{len(results['timeout'])} tools timed out:**")

            for result in results["timeout"]:
                with st.expander(f"⏱️ {result['tool']} ({result['elapsed']:.2f}s)"):
                    st.warning(result["error"])
        else:
            st.success("No timeouts! 🎉")

    # Download full report
    st.markdown("---")
    report_json = json.dumps(results, indent=2)
    st.download_button(
        "📥 Download Full Report", report_json, "tool_test_report.json", "application/json", use_container_width=True
    )
