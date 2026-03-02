"""
Admin tab - ops, processes, manifests, and DB operations.
"""

import time
from typing import Any

import streamlit as st
from components import render_json_drawer, render_scope_gate, render_table
from components.log_viewer import render_log_viewer
from state import get_state

from api import (
    activate_builtin_manifest,
    auto_start_override,
    cancel_db_job,
    create_db_job,
    get_builtin_manifest_history,
    get_db_counts,
    get_db_job,
    get_health_components,
    get_manifest_history,
    get_process_history,
    list_builtin_manifests,
    list_processes,
    preview_staged_manifests,
    rollback_builtin_manifest,
    stage_builtin_manifest,
    stop_process,
)

# Track start time for uptime calculation
_start_time = time.time()


def get_system_stats() -> tuple[bool, dict[str, Any] | None, str | None]:
    """
    Get system statistics.

    Returns:
        Tuple of (success, stats_dict, error)
        stats_dict contains: {users, jobs, agents, processes, uptime, memgraph_healthy}
    """
    try:
        stats = {}
        memgraph_healthy = True

        # Check Memgraph health first
        success, health_data, error = get_health_components()
        if success and health_data:
            components = health_data.get("checks", health_data.get("components", {}))
            memgraph_status = components.get("memgraph", {})

            # Check if Memgraph is healthy
            if isinstance(memgraph_status, dict):
                status_value = memgraph_status.get("status", "unknown")
                memgraph_healthy = status_value in ["ok", "healthy", "ready"]
            else:
                memgraph_healthy = memgraph_status in ["ok", "healthy", "ready"]
        else:
            memgraph_healthy = False

        stats["memgraph_healthy"] = memgraph_healthy

        # Get database counts only if Memgraph is healthy
        if memgraph_healthy:
            success, db_counts, error = get_db_counts()
            if success and db_counts:
                stats["users"] = db_counts.get("User", 0)
                stats["jobs"] = db_counts.get("Job", 0)
                stats["agents"] = db_counts.get("Agent", 0)
                stats["sessions"] = db_counts.get("Session", 0)
            else:
                # Default to 0 if counts unavailable
                stats["users"] = 0
                stats["jobs"] = 0
                stats["agents"] = 0
                stats["sessions"] = 0
        else:
            # Can't get counts if Memgraph is unhealthy
            stats["users"] = "N/A"
            stats["jobs"] = "N/A"
            stats["agents"] = "N/A"
            stats["sessions"] = "N/A"

        # Get process count
        success, processes, _error = list_processes()
        stats["processes"] = len(processes) if success and processes else 0

        # Calculate uptime (seconds since module load)
        stats["uptime"] = int(time.time() - _start_time)

        return True, stats, None

    except Exception as e:
        return False, None, f"Failed to get system stats: {e!s}"


def render_admin_tab():
    """Render admin tab with ops, processes, manifests, and DB operations."""
    st.header("⚙️ Admin Operations")

    # Check admin permissions with scope gate
    if not render_scope_gate(
        required_scopes=["admin:all", "admin:*"], mode="any", custom_message="Admin operations require admin access"
    ):
        return

    # Sub-tabs
    state = get_state()

    if state.developer_mode:
        sub_tabs = st.tabs(
            ["🔧 Processes", "📦 Built-in Manifests", "⚙️ Ops", "💾 Database", "� System Logs", "�🔴 Internal (Dev)"]
        )

        with sub_tabs[0]:
            _render_processes()

        with sub_tabs[1]:
            _render_builtins()

        with sub_tabs[2]:
            _render_ops()

        with sub_tabs[3]:
            _render_database()

        with sub_tabs[4]:
            _render_system_logs()

        with sub_tabs[5]:
            _render_internal()
    else:
        sub_tabs = st.tabs(["🔧 Processes", "📦 Built-in Manifests", "⚙️ Ops", "💾 Database", "📋 System Logs"])

        with sub_tabs[0]:
            _render_processes()

        with sub_tabs[1]:
            _render_builtins()

        with sub_tabs[2]:
            _render_ops()

        with sub_tabs[3]:
            _render_database()

        with sub_tabs[4]:
            _render_system_logs()


def _render_processes():
    """Render processes management with enhanced controls."""
    st.subheader("🔧 Process Management")
    st.caption("Monitor and manage system processes")

    # Refresh button
    col1, col2 = st.columns([5, 1])

    with col2:
        if st.button("🔄 Refresh", key="refresh_processes", use_container_width=True):
            st.rerun()

    # Fetch processes
    success, data, error = list_processes()

    if success and data:
        processes = data.get("processes", [])

        if processes:
            # Summary stats
            col1, col2, col3, col4 = st.columns(4)

            total_processes = len(processes)
            running_processes = sum(1 for p in processes if p.get("status") == "running")
            sleeping_processes = sum(1 for p in processes if p.get("status") == "sleeping")
            zombie_processes = sum(1 for p in processes if p.get("status") == "zombie")

            with col1:
                st.metric("📊 Total", total_processes)
            with col2:
                st.metric("▶️ Running", running_processes)
            with col3:
                st.metric("😴 Sleeping", sleeping_processes)
            with col4:
                st.metric("🧟 Zombie", zombie_processes)

            st.markdown("---")

            # Processes table
            st.markdown("### 📋 Active Processes")
            render_table(processes, key_prefix="processes_table")

            # Process actions
            st.markdown("---")
            st.markdown("### ⚙️ Process Actions")

            # Stop process with confirmation
            col1, col2 = st.columns([3, 1])

            with col1:
                pid_input = st.number_input(
                    "Process ID (PID)", min_value=1, key="stop_pid", help="Enter the PID of the process to stop"
                )

            with col2:
                st.markdown("")  # Spacing
                st.markdown("")  # Spacing
                stop_button = st.button(
                    "🛑 Stop Process", key="stop_process_btn", type="secondary", use_container_width=True
                )

            if stop_button:
                if pid_input:
                    # Find process details for confirmation
                    process_info = next((p for p in processes if p.get("pid") == pid_input), None)

                    if process_info:
                        process_name = process_info.get("name", "unknown")
                        process_cmd = process_info.get("cmdline", "")

                        st.warning(
                            f"""
                        ⚠️ **Confirm Process Termination**

                        - **PID:** {pid_input}
                        - **Name:** {process_name}
                        - **Command:** {process_cmd[:100]}{'...' if len(process_cmd) > 100 else ''}

                        This action cannot be undone.
                        """
                        )

                        col1, col2, col3 = st.columns([1, 1, 3])

                        with col1:
                            if st.button("✅ Confirm Stop", key=f"confirm_stop_{pid_input}", type="primary"):
                                with st.spinner(f"Stopping process {pid_input}..."):
                                    success, _, error = stop_process(int(pid_input))

                                if success:
                                    st.success(f"✅ Process {pid_input} stopped successfully")
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error(f"❌ Failed to stop process: {error}")

                        with col2:
                            if st.button("❌ Cancel", key=f"cancel_stop_{pid_input}"):
                                st.info("Operation cancelled")
                                st.rerun()
                    else:
                        st.error(f"❌ Process with PID {pid_input} not found in the current process list")
                else:
                    st.warning("⚠️ Please enter a valid PID")

            # Process details viewer
            st.markdown("---")
            st.markdown("### 🔍 Process Details")

            selected_pid = st.number_input(
                "Select PID to view details",
                min_value=1,
                key="view_process_pid",
                help="Enter PID to view detailed process information",
            )

            if st.button("👁️ View Details", key="view_process_details") and selected_pid:
                process_details = next((p for p in processes if p.get("pid") == selected_pid), None)

                if process_details:
                    # Display process details in organized sections
                    st.markdown(f"#### Process {selected_pid} Details")

                    col1, col2, col3 = st.columns(3)

                    with col1:
                        st.metric("PID", process_details.get("pid", "N/A"))
                        st.metric("PPID", process_details.get("ppid", "N/A"))

                    with col2:
                        st.metric("Status", process_details.get("status", "unknown"))
                        st.metric("User", process_details.get("username", "N/A"))

                    with col3:
                        cpu_percent = process_details.get("cpu_percent", 0)
                        mem_percent = process_details.get("memory_percent", 0)
                        st.metric("CPU %", f"{cpu_percent:.2f}")
                        st.metric("Memory %", f"{mem_percent:.2f}")

                    # Command line
                    st.markdown("**Command Line:**")
                    cmdline = process_details.get("cmdline", "")
                    st.code(cmdline if cmdline else "N/A", language="bash")

                    # Full details as JSON
                    render_json_drawer(process_details, title=f"Full Process {selected_pid} Data")
                else:
                    st.error(f"❌ Process with PID {selected_pid} not found")
        else:
            st.info(
                """
            📭 **No Processes Found**

            The system is not reporting any active processes.
            """
            )
    else:
        st.error(f"❌ Failed to list processes: {error}")

    st.markdown("---")

    # Process histories
    st.markdown("### 📜 Historical Data")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Manifest History")
        if st.button("� View Manifest History", key="view_manifest_history", use_container_width=True):
            with st.spinner("Fetching manifest history..."):
                success, data, error = get_manifest_history()

            if success:
                render_json_drawer(data, title="Manifest History Timeline")
            else:
                st.error(f"❌ Failed to fetch history: {error}")

    with col2:
        st.markdown("#### Process History")
        if st.button("� View Process History", key="view_process_history", use_container_width=True):
            with st.spinner("Fetching process history..."):
                success, data, error = get_process_history()

            if success:
                render_json_drawer(data, title="Process History Timeline")
            else:
                st.error(f"❌ Failed to fetch history: {error}")


def _render_builtins():
    """Render built-in manifests management with enhanced workflow."""
    st.subheader("📦 Built-in Manifests")
    st.caption("Manage built-in model provider manifests lifecycle")

    # Refresh button
    col1, col2 = st.columns([5, 1])

    with col2:
        if st.button("🔄 Refresh", key="refresh_manifests", use_container_width=True):
            st.rerun()

    # Fetch manifests
    success, data, error = list_builtin_manifests()

    if success and data:
        staged = data.get("staged", [])
        active = data.get("active", [])
        available = data.get("available", [])  # If API provides available list

        # Summary metrics
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("📋 Staged", len(staged))
        with col2:
            st.metric("✅ Active", len(active))
        with col3:
            if available:
                st.metric("📦 Available", len(available))

        st.markdown("---")

        # Current state display
        st.markdown("### 📊 Current State")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### 📋 Staged Manifests")
            if staged:
                for manifest in staged:
                    name = manifest.get("name", "unknown")
                    version = manifest.get("version", "unknown")
                    manifest_id = manifest.get("id", "")

                    # FIXED: Use static container key
                    container_key = f"staged_manifest_{name}_{version}"
                    with st.container(key=container_key):
                        st.markdown(
                            f"""
                        **{name}** `v{version}`
                        {f'ID: `{manifest_id}`' if manifest_id else ''}
                        """
                        )

                        # Show manifest details
                        if st.button("📄 Details", key=f"staged_details_{name}_{version}"):
                            render_json_drawer(manifest, title=f"Staged: {name} v{version}")

                        st.markdown("---")
            else:
                st.info("📭 No staged manifests")

        with col2:
            st.markdown("#### ✅ Active Manifests")
            if active:
                for manifest in active:
                    name = manifest.get("name", "unknown")
                    version = manifest.get("version", "unknown")
                    manifest_id = manifest.get("id", "")
                    activated_at = manifest.get("activated_at", "")

                    # FIXED: Use static container key
                    container_key = f"active_manifest_{name}_{version}"
                    with st.container(key=container_key):
                        st.markdown(
                            f"""
                        **{name}** `v{version}`
                        {f'ID: `{manifest_id}`' if manifest_id else ''}
                        {f'🕐 Activated: {activated_at[:19]}' if activated_at else ''}
                        """
                        )

                        # Show manifest details
                        if st.button("📄 Details", key=f"active_details_{name}_{version}"):
                            render_json_drawer(manifest, title=f"Active: {name} v{version}")

                        st.markdown("---")
            else:
                st.info("📭 No active manifests")
    else:
        st.error(f"❌ Failed to list manifests: {error}")

    st.markdown("---")

    # Manifest actions
    st.markdown("### ⚙️ Manifest Operations")

    action_tabs = st.tabs(["📥 Stage", "✅ Activate", "↩️ Rollback"])

    with action_tabs[0]:
        _render_stage_manifest()

    with action_tabs[1]:
        _render_activate_manifest()

    with action_tabs[2]:
        _render_rollback_manifest()

    st.markdown("---")

    # History timeline
    st.markdown("### 📜 Manifest History Timeline")

    if st.button("📊 View Complete History", key="view_builtin_history", use_container_width=True):
        with st.spinner("Fetching manifest history..."):
            success, history_data, error = get_builtin_manifest_history()

        if success and history_data:
            events = history_data.get("events", history_data.get("items", []))

            if events:
                st.success(f"✅ Loaded {len(events)} historical events")

                # Display timeline
                for idx, event in enumerate(events):
                    _render_manifest_event(event, idx)
            else:
                st.info("📭 No history events found")
        else:
            st.error(f"❌ Failed to fetch history: {error}")


def _render_stage_manifest():
    """Render stage manifest form."""
    st.markdown("#### 📥 Stage a Manifest")
    st.caption("Stage a built-in manifest for activation")

    with st.form("stage_manifest_form"):
        col1, col2 = st.columns(2)

        with col1:
            stage_name = st.text_input("Manifest Name *", placeholder="openai", help="Name of the built-in manifest")

        with col2:
            stage_version = st.text_input("Version *", placeholder="1.0.0", help="Manifest version to stage")

        # Optional fields
        stage_url = st.text_input(
            "Manifest URL (optional)",
            placeholder="https://registry.example.com/manifests/openai/1.0.0",
            help="External URL to fetch manifest from",
        )

        submitted = st.form_submit_button("📥 Stage Manifest", type="primary", use_container_width=True)

        if submitted:
            if not stage_name.strip() or not stage_version.strip():
                st.error("❌ Manifest name and version are required")
            else:
                stage_data = {"name": stage_name.strip(), "version": stage_version.strip()}

                if stage_url.strip():
                    stage_data["url"] = stage_url.strip()

                with st.spinner("Staging manifest..."):
                    success, _result, error = stage_builtin_manifest(stage_data)

                if success:
                    st.success(f"✅ Manifest {stage_name} v{stage_version} staged successfully")
                    st.balloons()
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(f"❌ Staging failed: {error}")


def _render_activate_manifest():
    """Render activate manifest form."""
    st.markdown("#### ✅ Activate a Manifest")
    st.caption("Activate a staged manifest to make it live")

    with st.form("activate_manifest_form"):
        activate_name = st.text_input(
            "Manifest Name *", placeholder="openai", help="Name of the staged manifest to activate"
        )

        activate_version = st.text_input(
            "Version (optional)",
            placeholder="Latest staged version",
            help="Specific version to activate (leave empty for latest)",
        )

        force_activate = st.checkbox("Force activation", help="Override any existing active version")

        submitted = st.form_submit_button("✅ Activate Manifest", type="primary", use_container_width=True)

        if submitted:
            if not activate_name.strip():
                st.error("❌ Manifest name is required")
            else:
                activate_data = {"name": activate_name.strip()}

                if activate_version.strip():
                    activate_data["version"] = activate_version.strip()

                if force_activate:
                    activate_data["force"] = True

                st.warning(
                    f"""
                ⚠️ **Confirm Activation**

                Activating manifest **{activate_name}** {f"v{activate_version}" if activate_version else "(latest)"}
                will make it the active version for all users.
                """
                )

                col1, col2 = st.columns(2)

                with col1:
                    if st.form_submit_button("✅ Confirm Activate", type="primary", use_container_width=True):
                        with st.spinner("Activating manifest..."):
                            success, _result, error = activate_builtin_manifest(activate_data)

                        if success:
                            st.success(f"✅ Manifest {activate_name} activated successfully")
                            st.balloons()
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(f"❌ Activation failed: {error}")

                with col2:
                    if st.form_submit_button("❌ Cancel", use_container_width=True):
                        st.info("Operation cancelled")


def _render_rollback_manifest():
    """Render rollback manifest form."""
    st.markdown("#### ↩️ Rollback a Manifest")
    st.caption("Rollback an active manifest to a previous version")

    with st.form("rollback_manifest_form"):
        rollback_name = st.text_input("Manifest Name *", placeholder="openai", help="Name of the manifest to rollback")

        rollback_to_version = st.text_input(
            "Rollback to Version (optional)",
            placeholder="Previous version",
            help="Specific version to rollback to (leave empty for previous)",
        )

        submitted = st.form_submit_button("↩️ Rollback Manifest", type="secondary", use_container_width=True)

        if submitted:
            if not rollback_name.strip():
                st.error("❌ Manifest name is required")
            else:
                rollback_data = {"name": rollback_name.strip()}

                if rollback_to_version.strip():
                    rollback_data["to_version"] = rollback_to_version.strip()

                st.error(
                    f"""
                ⚠️ **CONFIRM ROLLBACK**

                Rolling back manifest **{rollback_name}** {f"to v{rollback_to_version}" if rollback_to_version else "to previous version"}
                will revert to the older configuration.

                This action affects all users.
                """
                )

                col1, col2 = st.columns(2)

                with col1:
                    if st.form_submit_button("✅ Confirm Rollback", type="primary", use_container_width=True):
                        with st.spinner("Rolling back manifest..."):
                            success, _result, error = rollback_builtin_manifest(rollback_data)

                        if success:
                            st.success(f"✅ Manifest {rollback_name} rolled back successfully")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(f"❌ Rollback failed: {error}")

                with col2:
                    if st.form_submit_button("❌ Cancel", use_container_width=True):
                        st.info("Operation cancelled")


def _render_manifest_event(event: dict, index: int):
    """Render a single manifest history event."""
    event_type = event.get("type", event.get("action", "unknown"))
    manifest_name = event.get("manifest_name", event.get("name", "unknown"))
    version = event.get("version", "")
    timestamp = event.get("timestamp", event.get("created_at", ""))
    user = event.get("user", event.get("triggered_by", "system"))

    # Event type styling
    type_config = {
        "staged": {"emoji": "📥", "color": "blue"},
        "activated": {"emoji": "✅", "color": "green"},
        "rolled_back": {"emoji": "↩️", "color": "orange"},
        "deleted": {"emoji": "🗑️", "color": "red"},
    }.get(event_type, {"emoji": "📌", "color": "gray"})

    with st.expander(
        f"{type_config['emoji']} Event {index + 1}: {event_type.replace('_', ' ').title()} - {manifest_name} {f'v{version}' if version else ''}"
    ):
        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown(f"**Manifest:** `{manifest_name}`")
            if version:
                st.markdown(f"**Version:** `{version}`")

        with col2:
            st.markdown(f"**Action:** {event_type.replace('_', ' ').title()}")
            st.markdown(f"**User:** {user}")

        with col3:
            st.markdown(f"**Timestamp:** {timestamp[:19] if timestamp else 'N/A'}")

        # Event details
        details = event.get("details", event.get("metadata", {}))
        if details:
            st.markdown("**Event Details:**")
            st.json(details)

        # Full event
        with st.expander("📋 Full Event Data"):
            st.json(event)


def _render_ops():
    """Render ops controls."""
    st.subheader("Operations")

    # Preview staged
    if st.button("👁️ Preview Staged Manifests", key="preview_staged"):
        success, data, error = preview_staged_manifests()

        if success and data:
            st.success("✅ Preview fetched")
            render_json_drawer(data, title="Staged Manifests Preview")
        else:
            st.error(f"Preview failed: {error}")

    st.markdown("---")

    # Auto-start override
    st.markdown("### Auto-Start Override")
    st.warning("⚠️ This will override auto-start behavior")

    override_enabled = st.checkbox("Enable Override", key="override_enabled")

    if st.button("Apply Override", key="apply_override"):
        success, _, error = auto_start_override({"enabled": override_enabled})

        if success:
            st.success("✅ Override applied")
        else:
            st.error(f"Override failed: {error}")


def _render_database():
    """Render database operations."""
    st.subheader("Database Operations")

    # Check Memgraph health before showing DB counts
    memgraph_healthy = True
    health_warning = None

    success, health_data, error = get_health_components()
    if success and health_data:
        components = health_data.get("checks", health_data.get("components", {}))
        memgraph_status = components.get("memgraph", {})

        # Check if Memgraph is healthy
        if isinstance(memgraph_status, dict):
            status_value = memgraph_status.get("status", "unknown")
            if status_value not in ["ok", "healthy", "ready"]:
                memgraph_healthy = False
                health_warning = f"Memgraph is {status_value}"
        elif memgraph_status not in ["ok", "healthy", "ready"]:
            memgraph_healthy = False
            health_warning = f"Memgraph is {memgraph_status}"

    # DB counts dashboard
    if not memgraph_healthy:
        st.error(
            f"❌ **Database Unavailable**\n\n{health_warning or 'Memgraph is not healthy'}. "
            "DB counts cannot be retrieved until the database is ready.",
            icon="🚫",
        )

        if st.button("🔄 Refresh Health Status", key="refresh_db_health"):
            st.rerun()
    elif st.button("📊 View DB Counts", key="view_db_counts"):
        success, data, error = get_db_counts()

        if success and data:
            st.success("✅ DB counts fetched")

            # Display as metrics
            cols = st.columns(min(len(data), 4))  # Max 4 columns for better layout
            for idx, (key, value) in enumerate(data.items()):
                with cols[idx % 4]:
                    st.metric(key.replace("_", " ").title(), value)

            render_json_drawer(data, title="Full DB Counts")
        else:
            st.error(f"Failed to fetch counts: {error}")

    st.markdown("---")

    # Create maintenance job
    st.markdown("### Maintenance Jobs")

    job_type = st.selectbox("Job Type", ["vacuum", "analyze", "reindex", "backup"], key="db_job_type")
    job_params = st.text_area("Parameters (JSON)", key="db_job_params")

    if st.button("Create DB Job", key="create_db_job_btn"):
        import json

        job_data = {"job_type": job_type}

        if job_params:
            try:
                params = json.loads(job_params)
                job_data["parameters"] = params
            except:
                st.error("Invalid JSON in parameters")
                return

        success, data, error = create_db_job(job_data)

        if success:
            job_id = data.get("job_id")
            st.success(f"✅ DB job created: {job_id}")
        else:
            st.error(f"Job creation failed: {error}")

    # Job status
    st.markdown("---")
    db_job_id = st.text_input("Job ID", key="db_job_status_id")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("📊 View Job Status", key="view_db_job_status") and db_job_id:
            success, data, error = get_db_job(db_job_id)
            if success:
                render_json_drawer(data, title=f"DB Job {db_job_id}")
            else:
                st.error(f"Failed to fetch job: {error}")

    with col2:
        if st.button("🛑 Cancel Job", key="cancel_db_job_btn") and db_job_id:
            success, _, error = cancel_db_job(db_job_id)
            if success:
                st.success("✅ Job cancelled")
            else:
                st.error(f"Cancel failed: {error}")


def _render_internal():
    """Render internal/developer endpoints."""
    st.subheader("🔴 Internal Endpoints (Developer Mode)")

    st.error("⚠️ WARNING: These endpoints are for development only and may affect system stability!")

    st.markdown("Internal endpoints are identical to the admin endpoints above but use the `/internal/*` prefix.")
    st.markdown("Use the standard admin controls in the other tabs.")

    # Show confirmation requirement
    st.info("💡 Internal endpoints require explicit confirmation before invocation.")


def _render_system_logs():
    """Render system logs viewer with filtering and redaction."""
    st.subheader("📋 System Logs")

    st.info("🔒 All sensitive tokens, secrets, and credentials are automatically redacted")

    # Render the full log viewer component
    render_log_viewer(default_log_file="logs/ui.log")
