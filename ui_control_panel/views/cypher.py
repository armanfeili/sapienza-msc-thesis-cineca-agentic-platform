"""
NL→Cypher tab - Dedicated natural language to Cypher workflow.
"""

import json
import time
from datetime import datetime

import pandas as pd
import streamlit as st
from components import check_tool_access, render_json_drawer

from api import get_tool_invocation, invoke_tool


def render_cypher_tab():
    """Render dedicated NL→Cypher workflow tab."""
    st.header("🔍 Natural Language → Cypher")
    st.caption("Convert natural language questions into Cypher queries and execute them securely")

    # Check permissions
    has_access = check_tool_access(["reads_db", "llm_powered"])

    if not has_access:
        st.error("🔒 You don't have permission to use NL→Cypher tools")
        st.info("Required capabilities: `reads_db`, `llm_powered`")
        return

    # Main tabs
    cypher_tabs = st.tabs(["📝 Query Builder", "📊 Schema Explorer", "📜 Query History"])

    with cypher_tabs[0]:
        _render_query_builder()

    with cypher_tabs[1]:
        _render_schema_explorer()

    with cypher_tabs[2]:
        _render_query_history()


def _render_query_builder():
    """Render the NL→Cypher query builder interface."""
    st.subheader("Natural Language Query Builder")
    st.caption("Ask questions in plain English and get Cypher queries with results")

    # Quick examples
    with st.expander("💡 Example Questions"):
        st.markdown(
            """
        **Agent Queries:**
        - "What agents are in the system?"
        - "Show me all agents created in the last 7 days"
        - "Find agents with status 'active' and their capabilities"

        **Tool Queries:**
        - "List all tools with their capabilities"
        - "What tools can write to the database?"
        - "Show me tools that use LLMs"

        **Relationship Queries:**
        - "Which agents use which tools?"
        - "Show the relationship between agents and sessions"
        - "Find all connections from agent X to tools"
        """
        )

    # Query input
    with st.form("nl_cypher_form"):
        natural_language = st.text_area(
            "Your Question",
            placeholder="e.g., What agents are in the system?",
            height=100,
            help="Enter your question in natural language",
        )

        col1, col2 = st.columns([3, 1])

        with col1:
            st.caption("The query will be auto-converted to Cypher and executed safely with read-only enforcement")

        with col2:
            submitted = st.form_submit_button("🚀 Generate & Execute", type="primary", use_container_width=True)

        if submitted:
            if not natural_language.strip():
                st.error("❌ Please enter a question")
            else:
                _execute_nl_to_cypher(natural_language)


def _execute_nl_to_cypher(natural_language: str):
    """Execute NL→Cypher workflow."""
    st.markdown("---")
    st.markdown("### 🔄 Execution Progress")

    # Step 1: Invoke tool
    with st.spinner("Generating Cypher query..."):
        success, data, error = invoke_tool("memgraph.nl_to_cypher", {"natural_language": natural_language})

    if not success or not data:
        st.error(f"❌ Failed to invoke NL→Cypher: {error}")
        return

    eid = data.get("execution_id")

    if not eid:
        st.error("❌ No execution ID returned")
        return

    st.success("✅ Query generation started")
    st.info(f"**Execution ID:** `{eid}`")

    # Step 2: Poll for results
    result_data = _poll_for_cypher_result(eid)

    if not result_data:
        return

    # Step 3: Display results
    _display_cypher_execution_result(natural_language, result_data)


def _poll_for_cypher_result(eid: str, max_attempts: int = 15) -> dict | None:
    """Poll for NL→Cypher execution result."""
    st.markdown("#### ⏳ Waiting for query execution...")

    progress_bar = st.progress(0)
    status_text = st.empty()

    for attempt in range(max_attempts):
        progress = (attempt + 1) / max_attempts
        progress_bar.progress(progress)
        status_text.text(f"Polling attempt {attempt + 1}/{max_attempts}...")

        success, result_data, error = get_tool_invocation("memgraph.nl_to_cypher", eid)

        if success and result_data:
            status = result_data.get("status", "unknown")

            if status == "completed":
                progress_bar.progress(1.0)
                status_text.text("✅ Execution completed!")
                return result_data
            elif status == "failed":
                progress_bar.progress(1.0)
                status_text.text("❌ Execution failed")
                st.error(f"Execution failed: {result_data.get('error', 'Unknown error')}")
                return result_data
            elif status in ["pending", "running"]:
                time.sleep(1)
                continue

        if not success:
            st.warning(f"⚠️ Could not fetch result (attempt {attempt + 1}): {error}")
            time.sleep(1)

    # Timeout
    progress_bar.progress(1.0)
    status_text.text("⚠️ Polling timeout")
    st.warning(f"⚠️ Execution did not complete within {max_attempts} seconds")
    return None


def _display_cypher_execution_result(natural_language: str, result_data: dict):
    """Display NL→Cypher execution results with rich formatting."""
    st.markdown("---")
    st.markdown("### 📊 Query Results")

    # Extract output
    output = result_data.get("output", result_data.get("result", {}))

    if not output:
        st.warning("No output data available")
        return

    # Execution metadata
    col1, col2, col3 = st.columns(3)

    with col1:
        status = result_data.get("status", "unknown")
        status_emoji = "✅" if status == "completed" else "❌"
        st.metric("Status", f"{status_emoji} {status}")

    with col2:
        duration_ms = result_data.get("duration_ms", output.get("duration_ms", 0))
        st.metric("Duration", f"{duration_ms}ms")

    with col3:
        row_count = len(output.get("rows", []))
        st.metric("Rows Returned", row_count)

    st.markdown("---")

    # Display generated Cypher query
    cypher_query = output.get("cypher") or output.get("query", "")

    if cypher_query:
        st.markdown("#### 🔍 Generated Cypher Query")

        col1, col2 = st.columns([4, 1])

        with col1:
            st.code(cypher_query, language="cypher")

        with col2:
            # Copy button (simulated with download)
            st.download_button(
                label="📋 Copy Query",
                data=cypher_query,
                file_name="query.cypher",
                mime="text/plain",
                key=f"copy_cypher_{hash(cypher_query)}",
            )

    # Parameters
    params = output.get("parameters", {})
    if params:
        with st.expander("🔧 Query Parameters"):
            st.json(params)

    # Safety info
    if output.get("read_only_enforced"):
        st.success("✅ Read-only enforcement: Query was validated to prevent writes")

    if output.get("unsafe_reason"):
        st.error(f"🚫 Unsafe query blocked: {output['unsafe_reason']}")
        return

    # Row limit info
    row_limit = output.get("row_limit")
    if row_limit:
        st.caption(f"⚠️ Row limit: {row_limit} (results may be truncated)")

    # Results table
    rows = output.get("rows", [])

    if rows:
        st.markdown(f"#### 📋 Results ({len(rows)} rows)")

        df = pd.DataFrame(rows)

        # Display table with column config
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Export options
        st.markdown("---")
        st.markdown("#### 💾 Export Results")

        col1, col2, col3 = st.columns(3)

        with col1:
            csv = df.to_csv(index=False)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            st.download_button(
                label="📥 Download CSV",
                data=csv,
                file_name=f"cypher_results_{timestamp}.csv",
                mime="text/csv",
                use_container_width=True,
            )

        with col2:
            json_str = json.dumps(rows, indent=2)
            st.download_button(
                label="📥 Download JSON",
                data=json_str,
                file_name=f"cypher_results_{timestamp}.json",
                mime="application/json",
                use_container_width=True,
            )

        with col3:
            # Save to history
            if st.button("💾 Save to History", use_container_width=True):
                _save_to_history(natural_language, cypher_query, rows)
                st.success("✅ Saved to history!")
    else:
        st.info("📭 No rows returned from query")

    # Full raw result in drawer
    st.markdown("---")
    render_json_drawer(result_data, title="Complete Execution Result")


def _render_schema_explorer():
    """Render Memgraph schema explorer."""
    st.subheader("Memgraph Schema Explorer")
    st.caption("Explore the graph database structure to better understand what you can query")

    if st.button("🔄 Load Schema", type="primary"):
        _fetch_and_display_schema()


def _fetch_and_display_schema():
    """Fetch and display Memgraph schema."""
    with st.spinner("Fetching schema from Memgraph..."):
        success, data, error = invoke_tool("graph.schema", {})

    if not success or not data:
        st.error(f"❌ Failed to fetch schema: {error}")
        return

    eid = data.get("execution_id")

    if not eid:
        st.error("❌ No execution ID returned")
        return

    # Poll for schema result
    progress_bar = st.progress(0)
    status_text = st.empty()

    for attempt in range(10):
        progress_bar.progress((attempt + 1) / 10)
        status_text.text(f"Loading schema... {attempt + 1}/10")

        success, result_data, error = get_tool_invocation("graph.schema", eid)

        if success and result_data and result_data.get("status") == "completed":
            progress_bar.progress(1.0)
            status_text.text("✅ Schema loaded!")

            schema_output = result_data.get("output", result_data.get("result", {}))
            _display_schema_data(schema_output)
            return

        time.sleep(1)

    progress_bar.progress(1.0)
    status_text.text("⚠️ Schema loading timeout")
    st.warning("Schema loading took too long. Try again.")


def _display_schema_data(schema_data: dict):
    """Display Memgraph schema data."""
    st.markdown("---")
    st.markdown("### 🗂️ Database Schema")

    # Node types
    node_types = schema_data.get("node_types", schema_data.get("nodes", []))

    if node_types:
        st.markdown("#### 📦 Node Types (Labels)")

        for node_type in node_types:
            if isinstance(node_type, str):
                st.markdown(f"- **{node_type}**")
            elif isinstance(node_type, dict):
                label = node_type.get("label", "Unknown")
                count = node_type.get("count", "N/A")
                properties = node_type.get("properties", [])

                with st.expander(f"**{label}** ({count} nodes)"):
                    if properties:
                        st.markdown("**Properties:**")
                        for prop in properties:
                            st.markdown(f"- `{prop}`")
                    else:
                        st.caption("No properties listed")

    # Edge types
    edge_types = schema_data.get("edge_types", schema_data.get("relationships", []))

    if edge_types:
        st.markdown("#### 🔗 Relationship Types")

        for edge_type in edge_types:
            if isinstance(edge_type, str):
                st.markdown(f"- **{edge_type}**")
            elif isinstance(edge_type, dict):
                rel_type = edge_type.get("type", "Unknown")
                count = edge_type.get("count", "N/A")
                properties = edge_type.get("properties", [])

                with st.expander(f"**{rel_type}** ({count} relationships)"):
                    if properties:
                        st.markdown("**Properties:**")
                        for prop in properties:
                            st.markdown(f"- `{prop}`")
                    else:
                        st.caption("No properties listed")

    # Statistics
    stats = schema_data.get("statistics", {})
    if stats:
        st.markdown("---")
        st.markdown("#### 📊 Database Statistics")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Total Nodes", stats.get("node_count", "N/A"))

        with col2:
            st.metric("Total Relationships", stats.get("relationship_count", "N/A"))

        with col3:
            st.metric("Node Types", len(node_types) if node_types else 0)

    # Full schema JSON
    st.markdown("---")
    render_json_drawer(schema_data, title="Complete Schema JSON")


def _render_query_history():
    """Render query history interface."""
    st.subheader("Query History")
    st.caption("View and reuse your previous NL→Cypher queries")

    # Get history from session state
    if "cypher_history" not in st.session_state:
        st.session_state.cypher_history = []

    history = st.session_state.cypher_history

    if not history:
        st.info("📭 No query history yet. Run some queries to see them here!")
        return

    # Display history (most recent first)
    for idx, entry in enumerate(reversed(history)):
        timestamp = entry.get("timestamp", "Unknown")
        nl_query = entry.get("natural_language", "")
        cypher_query = entry.get("cypher", "")
        row_count = entry.get("row_count", 0)

        with st.expander(f"🕒 {timestamp} - {nl_query[:50]}..."):
            st.markdown("**Natural Language:**")
            st.info(nl_query)

            st.markdown("**Generated Cypher:**")
            st.code(cypher_query, language="cypher")

            st.caption(f"Returned {row_count} rows")

            # Rerun button
            if st.button("🔄 Rerun Query", key=f"rerun_{idx}"):
                _execute_nl_to_cypher(nl_query)


def _save_to_history(natural_language: str, cypher_query: str, rows: list[dict]):
    """Save query to history."""
    if "cypher_history" not in st.session_state:
        st.session_state.cypher_history = []

    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "natural_language": natural_language,
        "cypher": cypher_query,
        "row_count": len(rows),
    }

    # Add to beginning of history (most recent first when reversed)
    st.session_state.cypher_history.append(entry)

    # Limit history to last 50 queries
    if len(st.session_state.cypher_history) > 50:
        st.session_state.cypher_history = st.session_state.cypher_history[-50:]
