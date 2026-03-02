"""
Jobs tab - user and admin job management with event streaming.
"""

import json
import time

import streamlit as st
from components import render_json_drawer, render_table
from state import get_active_token

from api import (
    cancel_admin_job,
    cancel_job,
    create_job,
    get_job,
    get_job_events,
    list_admin_jobs,
    list_jobs,
)


def render_jobs_tab():
    """Render jobs management tab with enhanced streaming."""
    st.header("📋 Jobs")

    # Check permissions
    token = get_active_token()
    has_admin = token and "admin:all" in token.scopes if token else False

    if has_admin:
        sub_tabs = st.tabs(["📋 My Jobs", "⚙️ Admin Jobs"])

        with sub_tabs[0]:
            _render_user_jobs()

        with sub_tabs[1]:
            _render_admin_jobs()
    else:
        _render_user_jobs()


def _render_user_jobs():
    """Render user jobs interface with enhanced features."""
    st.subheader("My Jobs")
    st.caption("Create and monitor asynchronous jobs with event streaming")

    # Create new job
    with st.expander("➕ Create New Job", expanded=False):
        with st.form("create_job_form"):
            st.markdown("### Job Configuration")

            job_type = st.text_input("Job Type *", placeholder="data_processing", help="Type of job to create")

            job_params = st.text_area(
                "Parameters (JSON)",
                placeholder='{\n  "param1": "value1",\n  "param2": "value2"\n}',
                height=100,
                help="Job-specific parameters in JSON format",
            )

            col1, col2 = st.columns(2)

            with col1:
                idempotency_key = st.text_input(
                    "Idempotency Key (Optional)",
                    placeholder="unique-request-id",
                    help="Prevents duplicate job creation with the same key",
                )

            with col2:
                priority = st.selectbox(
                    "Priority", options=["normal", "high", "low"], index=0, help="Job execution priority"
                )

            submitted = st.form_submit_button("🚀 Create Job", type="primary", use_container_width=True)

            if submitted:
                if not job_type.strip():
                    st.error("❌ Job type is required")
                else:
                    job_data = {"job_type": job_type.strip()}

                    # Parse parameters
                    if job_params.strip():
                        try:
                            params = json.loads(job_params)
                            job_data["parameters"] = params
                        except json.JSONDecodeError as e:
                            st.error(f"❌ Invalid JSON in parameters: {e!s}")
                            st.stop()

                    if idempotency_key.strip():
                        job_data["idempotency_key"] = idempotency_key.strip()

                    if priority != "normal":
                        job_data["priority"] = priority

                    with st.spinner("Creating job..."):
                        success, data, error = create_job(job_data)

                    if success and data:
                        job_id = data.get("job_id")
                        st.success("✅ Job created successfully")
                        st.info(f"**Job ID:** `{job_id}`")
                        st.balloons()

                        # Save to active jobs
                        if "active_jobs" not in st.session_state:
                            st.session_state.active_jobs = []

                        if job_id and job_id not in st.session_state.active_jobs:
                            st.session_state.active_jobs.insert(0, job_id)
                            st.session_state.active_jobs = st.session_state.active_jobs[:10]  # Keep last 10

                        st.rerun()
                    else:
                        st.error(f"❌ Failed to create job: {error}")

    st.markdown("---")

    # List jobs with filters
    st.markdown("### 📊 Jobs List")

    col1, col2, col3, col4 = st.columns([2, 2, 1, 1])

    with col1:
        status_filter = st.selectbox(
            "Filter by Status",
            ["all", "pending", "running", "completed", "failed", "cancelled"],
            key="job_status_filter",
        )

    with col2:
        job_type_filter = st.text_input("Filter by Type", placeholder="All types", key="job_type_filter")

    with col3:
        page = st.number_input("Page", min_value=1, value=1, key="job_page")

    with col4:
        if st.button("🔄 Refresh", key="refresh_jobs", use_container_width=True):
            st.rerun()

    # Fetch jobs
    params = {"page": page, "size": 50}
    if status_filter != "all":
        params["status"] = status_filter
    if job_type_filter.strip():
        params["job_type"] = job_type_filter.strip()

    success, data, error = list_jobs(params)

    if success and data:
        jobs = data.get("items", [])

        if jobs:
            # Show summary stats
            col1, col2, col3, col4 = st.columns(4)

            pending_count = sum(1 for j in jobs if j.get("status") == "pending")
            running_count = sum(1 for j in jobs if j.get("status") == "running")
            completed_count = sum(1 for j in jobs if j.get("status") == "completed")
            failed_count = sum(1 for j in jobs if j.get("status") == "failed")

            with col1:
                st.metric("⏳ Pending", pending_count)
            with col2:
                st.metric("🔄 Running", running_count)
            with col3:
                st.metric("✅ Completed", completed_count)
            with col4:
                st.metric("❌ Failed", failed_count)

            st.markdown("---")

            # Jobs table
            render_table(jobs, key_prefix="jobs_table")

            # Job workspace
            st.markdown("---")
            _render_job_workspace()
        else:
            st.info(
                """
            📭 **No jobs found**

            Create your first job using the form above to get started!
            """
            )
    else:
        st.error(f"❌ Failed to list jobs: {error}")


def _render_job_workspace():
    """Render job workspace for monitoring and actions."""
    st.markdown("### 🔍 Job Monitor")

    # Job selector
    job_id_input = st.text_input(
        "Job ID",
        placeholder="Enter job ID to monitor",
        key="job_monitor_id",
        help="Enter the ID of the job you want to monitor",
    )

    if not job_id_input.strip():
        # Show recent jobs
        if "active_jobs" in st.session_state and st.session_state.active_jobs:
            st.caption("📌 Recent Jobs:")

            cols = st.columns(min(len(st.session_state.active_jobs), 5))
            for idx, job_id in enumerate(st.session_state.active_jobs[:5]):
                with cols[idx]:
                    if st.button(f"`{job_id[:8]}...`", key=f"select_job_{job_id}", use_container_width=True):
                        st.session_state.job_monitor_id = job_id
                        st.rerun()

        st.info("💡 Enter a job ID above or select from recent jobs to monitor")
        return

    # Tabs for different views
    job_tabs = st.tabs(["📊 Status", "📡 Events Stream", "⚙️ Actions"])

    with job_tabs[0]:
        _render_job_status(job_id_input)

    with job_tabs[1]:
        _render_job_events_stream(job_id_input)

    with job_tabs[2]:
        _render_job_actions(job_id_input)


def _render_job_status(job_id: str):
    """Display job status with real-time monitoring."""
    st.markdown("#### 📊 Job Status")

    col1, col2 = st.columns([4, 1])

    with col2:
        auto_refresh = st.checkbox("Auto-refresh", value=False, key=f"auto_refresh_{job_id}")

    with col1:
        if st.button("🔄 Refresh Status", key=f"refresh_status_{job_id}"):
            st.rerun()

    success, data, error = get_job(job_id)

    if success and data:
        # Key metrics
        col1, col2, col3, col4 = st.columns(4)

        status = data.get("status", "unknown")
        status_emoji = {"pending": "⏳", "running": "🔄", "completed": "✅", "failed": "❌", "cancelled": "🚫"}.get(
            status, "❓"
        )

        with col1:
            st.metric("Status", f"{status_emoji} {status}")

        with col2:
            progress = data.get("progress", 0)
            st.metric("Progress", f"{progress}%")

        with col3:
            job_type = data.get("job_type", "unknown")
            st.metric("Type", job_type)

        with col4:
            duration = data.get("duration_ms", 0)
            st.metric("Duration", f"{duration}ms")

        # Timestamps
        st.markdown("---")
        col1, col2, col3 = st.columns(3)

        with col1:
            created = data.get("created_at", "N/A")
            st.caption(f"📅 **Created:** {created[:19] if created != 'N/A' else 'N/A'}")

        with col2:
            started = data.get("started_at", "N/A")
            st.caption(f"▶️ **Started:** {started[:19] if started != 'N/A' else 'N/A'}")

        with col3:
            completed = data.get("completed_at", "N/A")
            st.caption(f"🏁 **Completed:** {completed[:19] if completed != 'N/A' else 'N/A'}")

        # Result or error
        if status == "completed":
            result = data.get("result")
            if result:
                st.markdown("---")
                st.markdown("#### ✅ Result")
                st.success("Job completed successfully")

                if isinstance(result, dict):
                    st.json(result)
                else:
                    st.info(str(result))

        elif status == "failed":
            error_msg = data.get("error", data.get("error_message"))
            if error_msg:
                st.markdown("---")
                st.markdown("#### ❌ Error")
                st.error(error_msg)

        # Full details
        st.markdown("---")
        render_json_drawer(data, title="Complete Job Data")

        # Auto-refresh logic (non-blocking)
        if auto_refresh and status in ["pending", "running"]:
            # Track last refresh time to avoid blocking
            refresh_key = f"last_job_refresh_{job_id}"
            if refresh_key not in st.session_state:
                st.session_state[refresh_key] = time.time()

            elapsed = time.time() - st.session_state[refresh_key]

            # Show countdown
            if elapsed < 2.0:
                remaining = int(2.0 - elapsed)
                st.caption(f"⏱️ Auto-refresh in {remaining}s")
            else:
                # Time to refresh
                st.session_state[refresh_key] = time.time()
                st.rerun()
    else:
        st.error(f"❌ Failed to fetch job: {error}")


def _render_job_events_stream(job_id: str):
    """Display job events with streaming and resume capability."""
    st.markdown("#### 📡 Event Stream")
    st.caption("Real-time job events with resume capability using Last-Event-ID")

    # Initialize event state
    if f"last_event_id_{job_id}" not in st.session_state:
        st.session_state[f"last_event_id_{job_id}"] = None

    if f"events_{job_id}" not in st.session_state:
        st.session_state[f"events_{job_id}"] = []

    col1, col2, col3 = st.columns([2, 2, 1])

    with col1:
        auto_stream = st.checkbox("Auto-stream", value=False, key=f"auto_stream_{job_id}")

    with col2:
        if st.button("📡 Fetch New Events", key=f"fetch_events_{job_id}"):
            _fetch_job_events(job_id)

    with col3:
        if st.button("🔄 Reset", key=f"reset_events_{job_id}"):
            st.session_state[f"last_event_id_{job_id}"] = None
            st.session_state[f"events_{job_id}"] = []
            st.rerun()

    # Display last event ID
    last_event_id = st.session_state[f"last_event_id_{job_id}"]
    if last_event_id:
        st.info(f"📌 **Resume Point:** Last Event ID = `{last_event_id}`")

    # Display events
    events = st.session_state[f"events_{job_id}"]

    if events:
        st.markdown(f"**📊 Total Events:** {len(events)}")
        st.markdown("---")

        for idx, event in enumerate(events):
            _render_event(event, idx)
    else:
        st.info("📭 No events yet. Click 'Fetch New Events' to load events.")

    # Auto-streaming (non-blocking)
    if auto_stream:
        # Track last fetch time to avoid blocking
        fetch_key = f"last_event_fetch_{job_id}"
        if fetch_key not in st.session_state:
            st.session_state[fetch_key] = time.time()

        elapsed = time.time() - st.session_state[fetch_key]

        # Fetch events every 1 second (non-blocking)
        if elapsed >= 1.0:
            st.session_state[fetch_key] = time.time()
            _fetch_job_events(job_id)
            st.rerun()
        else:
            remaining = int(1.0 - elapsed)
            st.caption(f"⏱️ Auto-stream refresh in {remaining}s")


def _fetch_job_events(job_id: str):
    """Fetch job events with resume support."""
    last_event_id = st.session_state.get(f"last_event_id_{job_id}")

    success, data, error = get_job_events(job_id, last_event_id)

    if success and data:
        new_events = data.get("events", [])

        if new_events:
            # Append to existing events
            existing = st.session_state.get(f"events_{job_id}", [])
            existing.extend(new_events)
            st.session_state[f"events_{job_id}"] = existing

            # Update last event ID
            last_event = new_events[-1]
            st.session_state[f"last_event_id_{job_id}"] = last_event.get("id")

            st.success(f"✅ Fetched {len(new_events)} new event(s)")
        else:
            st.info("No new events")
    else:
        st.error(f"❌ Failed to fetch events: {error}")


def _render_event(event: dict, index: int):
    """Render a single event."""
    event_id = event.get("id", "unknown")
    event_type = event.get("type", "unknown")
    event_data = event.get("data", {})
    timestamp = event.get("timestamp", "")

    # Event type styling
    type_emoji = {
        "created": "🆕",
        "started": "▶️",
        "progress": "📊",
        "completed": "✅",
        "failed": "❌",
        "cancelled": "🚫",
        "log": "📝",
    }.get(event_type, "📌")

    with st.expander(f"{type_emoji} Event {index + 1}: {event_type.title()} - ID: `{event_id}`"):
        col1, col2 = st.columns(2)

        with col1:
            st.markdown(f"**Event ID:** `{event_id}`")

        with col2:
            st.markdown(f"**Timestamp:** {timestamp[:19] if timestamp else 'No timestamp'}")

        if event_data:
            st.markdown("**Event Data:**")
            st.json(event_data)

        st.markdown("---")


def _render_job_actions(job_id: str):
    """Render job action controls."""
    st.markdown("#### ⚙️ Job Actions")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("##### 🛑 Cancel Job")
        st.caption("Stop the job execution")

        if st.button("🚫 Cancel Job", key=f"cancel_job_{job_id}", type="secondary", use_container_width=True):
            with st.spinner("Cancelling job..."):
                success, _, error = cancel_job(job_id)

            if success:
                st.success("✅ Job cancelled successfully")
                st.rerun()
            else:
                st.error(f"❌ Failed to cancel job: {error}")

    with col2:
        st.markdown("##### 📥 Export Data")
        st.caption("Download job data and events")

        # Fetch job data
        success, job_data, _ = get_job(job_id)

        if success and job_data:
            # Export as JSON
            events = st.session_state.get(f"events_{job_id}", [])
            export_data = {"job": job_data, "events": events}

            json_str = json.dumps(export_data, indent=2)
            st.download_button(
                label="📥 Export JSON",
                data=json_str,
                file_name=f"job_{job_id}.json",
                mime="application/json",
                key=f"export_job_{job_id}",
                use_container_width=True,
            )


def _render_admin_jobs():
    """Render admin jobs interface with enhanced management."""
    st.subheader("Admin Jobs Collection")
    st.caption("View and manage all jobs across the system")

    col1, col2 = st.columns([5, 1])

    with col2:
        if st.button("🔄 Refresh", key="refresh_admin_jobs"):
            st.rerun()

    # Filters
    params = {}

    col1, col2, col3 = st.columns(3)

    with col1:
        status_filter = st.selectbox(
            "Status", ["all", "pending", "running", "completed", "failed"], key="admin_job_status"
        )
        if status_filter != "all":
            params["status"] = status_filter

    with col2:
        user_filter = st.text_input("User ID", placeholder="Filter by user", key="admin_job_user")
        if user_filter.strip():
            params["user_id"] = user_filter.strip()

    with col3:
        limit = st.number_input("Limit", min_value=10, max_value=500, value=100, key="admin_job_limit")
        params["limit"] = limit

    success, data, error = list_admin_jobs(params)

    if success and data:
        jobs = data.get("items", [])

        if jobs:
            # Summary stats
            col1, col2, col3, col4 = st.columns(4)

            total = len(jobs)
            active = sum(1 for j in jobs if j.get("status") in ["pending", "running"])
            completed = sum(1 for j in jobs if j.get("status") == "completed")
            failed = sum(1 for j in jobs if j.get("status") == "failed")

            with col1:
                st.metric("Total", total)
            with col2:
                st.metric("Active", active)
            with col3:
                st.metric("Completed", completed)
            with col4:
                st.metric("Failed", failed)

            st.markdown("---")

            render_table(jobs, key_prefix="admin_jobs_table")

            # Admin actions
            st.markdown("---")
            st.markdown("### 🛠️ Admin Actions")

            job_id_input = st.text_input("Job ID", key="admin_job_cancel_id", placeholder="Enter job ID to cancel")

            if job_id_input.strip():
                if st.button("🛑 Cancel Job (Admin)", key="cancel_admin_job", type="secondary"):
                    with st.spinner("Cancelling job..."):
                        success, _, error = cancel_admin_job(job_id_input.strip())

                    if success:
                        st.success("✅ Job cancelled by admin")
                        st.rerun()
                    else:
                        st.error(f"❌ Failed to cancel: {error}")
        else:
            st.info("📭 No admin jobs found with the specified filters")
    else:
        st.error(f"❌ Failed to list admin jobs: {error}")
