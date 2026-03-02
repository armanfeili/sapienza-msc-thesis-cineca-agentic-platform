"""
Agents tab - Copilot-style agent runs with rich timeline and sessions.
"""

import json
import logging

import streamlit as st
from components import render_json_drawer, render_table
from state import get_state, update_state

from api import (
    add_session_step,
    cancel_agent_session,
    create_agent_run,
    create_agent_session,
    get_agent_run,
    get_agent_session,
    list_agent_sessions,
    list_model_instances,
    list_session_steps,
    send_agent_message,
)
from utils import sleep_with_jitter

logger = logging.getLogger(__name__)


def render_agents_tab():
    """Render agents tab with Copilot-style runs and sessions."""
    st.header("🤖 AI Agents")

    # Sub-tabs for runs and sessions
    sub_tabs = st.tabs(["🚀 Agent Runs", "📂 Sessions"])

    with sub_tabs[0]:
        _render_agent_runs()

    with sub_tabs[1]:
        _render_sessions()


def _render_agent_runs():
    """Render Copilot-style agent runs interface."""
    st.subheader("Agent Run Creator")
    st.caption("Create and monitor AI agent runs with real-time progress tracking")

    # Check and auto-fetch model defaults
    state = get_state()

    # AGGRESSIVE FIX: If we have a valid token but there's a cached 403 error, clear it
    from state import get_active_token

    current_token = get_active_token()
    if current_token and not current_token.is_expired:
        if hasattr(st.session_state, "model_defaults_error"):
            old_error = st.session_state.model_defaults_error
            if "403" in str(old_error) or "Forbidden" in str(old_error):
                # We have a valid token now - clear the old error and force retry
                logger.info(f"Clearing cached 403 error - have valid token with scopes: {current_token.scopes}")
                del st.session_state.model_defaults_error
                update_state(defaults_loaded=False)

    # Auto-fetch defaults if not already loaded
    if not state.defaults_loaded:
        with st.spinner("🔄 Loading model defaults..."):
            from api import get_model_defaults

            success, defaults_data, error = get_model_defaults()

            if success and defaults_data:
                update_state(model_defaults=defaults_data, defaults_loaded=True)
            elif error and "404" not in str(error):
                # Don't show error for 404 (no defaults set yet)
                st.session_state.model_defaults_error = error
                st.warning(f"⚠️ Could not load defaults: {error}")
                # Mark as loaded to prevent infinite retries
                update_state(defaults_loaded=True)
            else:
                # 404 or no error - just mark as loaded
                update_state(defaults_loaded=True)

    # Check if there was an error loading defaults
    if hasattr(st.session_state, "model_defaults_error"):
        error_msg = st.session_state.model_defaults_error

        # Check if it's a permission error (403)
        if "403" in str(error_msg) or "Forbidden" in str(error_msg):
            # Get current token info to debug
            from state import get_active_token

            current_token = get_active_token()

            debug_info = ""
            if current_token:
                scopes_list = current_token.scopes if hasattr(current_token, "scopes") else []
                debug_info = f"""

                **Current Token Info:**
                - Active Identity: `{state.active_identity}`
                - Token Subject: `{current_token.subject}`
                - Token Scopes: `{', '.join(scopes_list) if scopes_list else 'None'}`
                - Required Scopes: `user:me` OR `admin:all`
                """

            st.warning(
                f"""
            ⚠️ **Permission Error**

            Your current token doesn't have the required permissions to access model defaults.

            **What's wrong:**
            The `/v1/models/defaults` endpoint requires either:
            - `user:me` scope (for regular users), OR
            - `admin:all` scope (for administrators)
            {debug_info}

            **To fix this:**
            1. Go to the **🔐 Auth** tab
            2. **Logout** your current identity
            3. **Login again** (this will request fresh scopes)
            4. Return to this tab

            **Technical Details:**
            {error_msg}
            """
            )

        else:
            st.error(f"❌ Error loading model defaults: {error_msg}")
            st.info("💡 Please check your configuration and try refreshing the page.")

        if st.button("🔄 Retry Loading Defaults", key="retry_defaults"):
            del st.session_state.model_defaults_error
            update_state(defaults_loaded=False)
            st.rerun()
        return

    # Check if defaults are now available
    default_instance_id = None
    if state.model_defaults:
        default_instance_id = state.model_defaults.get("default_instance_id")

    if not default_instance_id:
        st.error(
            """
        ⚠️ **No Model Defaults Configured**

        A default model instance must be configured before you can create agent runs.

        **To fix this:**
        1. Navigate to the **🧠 Models** tab
        2. Go to the **Model Instances** sub-tab
        3. Click **⚙️ Set Default Model Now** button
        4. Select a model instance and save

        Once defaults are configured, you'll be able to create agent runs here.
        """
        )

        if st.button("⚙️ Go to Models Tab", key="goto_models", type="primary"):
            st.info("👉 Navigate to the **🧠 Models** tab to set a default model instance")

        # Show sessions even if no defaults configured
        st.markdown("---")
        st.markdown("### 📂 Sessions")
        _render_sessions()
        return

    # Run creation form
    with st.form("create_agent_run_form"):
        st.markdown("### 📝 Run Configuration")

        # Prompt input
        prompt = st.text_area(
            "Prompt *",
            placeholder="What would you like the agent to do?",
            height=150,
            help="Enter your instructions for the AI agent",
        )

        col1, col2 = st.columns(2)

        with col1:
            # Model instance selector
            success, instances_data, _ = list_model_instances()
            instances = instances_data.get("items", []) if success and instances_data else []

            instance_options = {
                f"Default: {default_instance_id}": default_instance_id,
                **{
                    f"{inst.get('display_name', inst.get('instance_id'))} ({inst.get('instance_id')})": inst.get(
                        "instance_id"
                    )
                    for inst in instances
                    if inst.get("instance_id") and inst.get("instance_id") != default_instance_id
                },
            }

            selected_instance_key = st.selectbox(
                "Model Instance",
                options=list(instance_options.keys()),
                index=0,
                help="Select the model instance to use (defaults to configured default)",
            )

            selected_instance_id = instance_options[selected_instance_key]

        with col2:
            max_steps = st.number_input(
                "Max Steps",
                min_value=1,
                max_value=64,
                value=8,
                help="Maximum number of reasoning steps before stopping",
            )

        # Advanced options
        with st.expander("⚙️ Advanced Options"):
            temperature = st.slider(
                "Temperature",
                min_value=0.0,
                max_value=2.0,
                value=0.2,
                step=0.1,
                help="Higher values make output more random",
            )

            session_id = st.text_input(
                "Session ID (Optional)",
                placeholder="Leave empty for new session",
                help="Attach run to existing session",
            )

            metadata = st.text_area(
                "Metadata (JSON)", placeholder='{"key": "value"}', help="Optional metadata to attach to the run"
            )

        # Submit button
        submitted = st.form_submit_button("🚀 Create Agent Run", type="primary", use_container_width=True)

        if submitted:
            if not prompt.strip():
                st.error("❌ Please enter a prompt")
            else:
                # Parse metadata
                meta_dict = None
                if metadata.strip():
                    try:
                        meta_dict = json.loads(metadata)
                    except json.JSONDecodeError:
                        st.error("❌ Invalid JSON in metadata")
                        st.stop()

                # Create run data - match CreateRunRequest schema
                run_data = {
                    "prompt": prompt,
                    "max_steps": max_steps,
                    "temperature": temperature,
                }

                # Use manager field (not instance_id) for model selection
                # Manager is the LLM name that the backend will use
                if selected_instance_id != default_instance_id:
                    # If user explicitly selected a different instance, use it as manager
                    run_data["manager"] = selected_instance_id
                # Otherwise, backend will use the default from /v1/models/defaults

                if session_id.strip():
                    run_data["session_id"] = session_id

                if meta_dict:
                    run_data["metadata"] = meta_dict

                _execute_agent_run(run_data)

    st.markdown("---")

    # Show active runs
    _render_active_runs()


def _execute_agent_run(run_data: dict):
    """Execute an agent run and start monitoring."""
    st.markdown("---")
    st.markdown("### 🔄 Creating Agent Run...")

    with st.spinner("Submitting run request..."):
        success, data, error = create_agent_run(run_data)

    if not success or not data:
        st.error(f"❌ Failed to create run: {error}")
        return

    run_id = data.get("run_id")

    if not run_id:
        st.error("❌ No run ID returned from API")
        return

    st.success("✅ Agent run created successfully")
    st.info(f"**Run ID:** `{run_id}`")

    # Save to active runs in state
    if "active_runs" not in st.session_state:
        st.session_state.active_runs = []

    if run_id not in st.session_state.active_runs:
        st.session_state.active_runs.insert(0, run_id)  # Add to beginning

        # Limit to last 10 active runs
        st.session_state.active_runs = st.session_state.active_runs[:10]

    # Start monitoring
    _monitor_agent_run(run_id, run_data)


def _monitor_agent_run(run_id: str, run_config: dict):
    """Monitor agent run with real-time updates."""
    st.markdown("---")
    st.markdown(f"### 📊 Run Monitor: `{run_id}`")

    # Progress tracking
    progress_bar = st.progress(0)
    status_text = st.empty()

    # Result containers
    answer_container = st.empty()
    timeline_container = st.empty()
    metrics_container = st.empty()

    # Default timeout for polling (with jittered intervals to prevent thundering herd)
    timeout_seconds = 120
    base_poll_interval = 0.5  # Start with 500ms
    max_polls = int(timeout_seconds / base_poll_interval)  # Approximate max polls

    for poll_count in range(max_polls):
        success, data, error = get_agent_run(run_id)

        if not success:
            status_text.error(f"❌ Failed to fetch run status: {error}")
            break

        status = data.get("status", "unknown")
        progress = poll_count / max_polls
        progress_bar.progress(progress)

        # Update status text
        status_emoji = {"pending": "⏳", "running": "🔄", "completed": "✅", "failed": "❌", "cancelled": "🚫"}.get(
            status, "❓"
        )

        status_text.text(f"{status_emoji} Status: {status} (Poll {poll_count + 1})")

        # Display results
        _display_run_results(data, answer_container, timeline_container, metrics_container)

        # Check terminal states
        if status in ["completed", "failed", "cancelled"]:
            progress_bar.progress(1.0)
            status_text.text(f"{status_emoji} Run {status}")
            _render_run_actions(run_id, data, run_config)
            break

        # Use jittered sleep to prevent thundering herd (±20% randomization)
        sleep_with_jitter(base_poll_interval, jitter_percent=20.0)
    else:
        # Timeout
        progress_bar.progress(1.0)
        status_text.warning(f"⚠️ Monitoring timeout after {timeout_seconds}s. Run may still be executing.")
        st.info(f"**Run ID:** `{run_id}` - Check manually or refresh page")


def _display_run_results(run_data: dict, answer_container, timeline_container, metrics_container):
    """Display agent run results with rich formatting."""
    # Show TODOs if available (GitHub Copilot-style)
    todos = run_data.get("todos", [])
    
    if todos:
        with answer_container.container():
            st.markdown("#### 📝 Agent's TODO List")
            st.caption("The agent created this plan to accomplish your goal:")
            
            for idx, todo in enumerate(todos, 1):
                task = todo.get("task", "")
                status = todo.get("status", "pending")
                
                # Icon based on status
                icon_map = {
                    "pending": "⏳",
                    "running": "🔄",
                    "completed": "✅",
                    "failed": "❌"
                }
                icon = icon_map.get(status, "❓")
                
                # Display with appropriate formatting
                st.markdown(f"{icon} **{idx}.** {task}")
            
            st.markdown("---")
    
    # Show answer if available
    answer = run_data.get("answer") or run_data.get("result") or run_data.get("output")

    if answer:
        with answer_container.container():
            st.markdown("#### 💡 Final Answer")
            st.success(answer)
            st.markdown("---")

    # Show timeline
    timeline = run_data.get("timeline", run_data.get("steps", []))

    if timeline:
        with timeline_container.container():
            st.markdown("#### 🔄 Execution Timeline")
            _render_timeline_events(timeline)
            st.markdown("---")

    # Show metrics
    with metrics_container.container():
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            iterations = run_data.get("iterations_used", len(timeline))
            st.metric("Iterations", iterations)

        with col2:
            duration_ms = run_data.get("duration_ms") or run_data.get("latency_ms", 0)
            st.metric("Duration", f"{duration_ms}ms")

        with col3:
            tokens_used = run_data.get("tokens_used", 0)
            st.metric("Tokens", tokens_used)

        with col4:
            tools_called = sum(1 for event in timeline if event.get("type") == "tool_call")
            st.metric("Tools Called", tools_called)


def _render_timeline_events(timeline: list[dict]):
    """Render timeline events with rich visualization."""
    for idx, event in enumerate(timeline):
        event_type = event.get("type", "unknown")
        timestamp = event.get("timestamp", "")

        # Event type emoji and color
        event_config = {
            "start": {"emoji": "🚀", "color": "blue"},
            "reasoning": {"emoji": "🧠", "color": "purple"},
            "tool_call": {"emoji": "🔧", "color": "green"},
            "tool_result": {"emoji": "📊", "color": "cyan"},
            "decision": {"emoji": "💭", "color": "orange"},
            "answer": {"emoji": "💡", "color": "yellow"},
            "error": {"emoji": "❌", "color": "red"},
        }.get(event_type, {"emoji": "📌", "color": "gray"})

        with st.expander(
            f"{event_config['emoji']} Step {idx + 1}: {event_type.title()} - {timestamp[:19] if timestamp else 'No time'}"
        ):
            # Event details
            if event_type == "tool_call":
                tool_name = event.get("tool_name", "unknown")
                tool_args = event.get("arguments", {})

                st.markdown(f"**Tool:** `{tool_name}`")

                if tool_args:
                    st.markdown("**Arguments:**")
                    st.json(tool_args)

            elif event_type == "tool_result":
                tool_name = event.get("tool_name", "unknown")
                result = event.get("result", {})
                success = event.get("success", False)

                status_icon = "✅" if success else "❌"
                st.markdown(f"{status_icon} **Tool:** `{tool_name}`")

                if result:
                    st.markdown("**Result:**")
                    if isinstance(result, dict):
                        st.json(result)
                    else:
                        st.info(str(result))

            elif event_type == "reasoning":
                thought = event.get("thought", event.get("content", ""))
                st.markdown("**Thought:**")
                st.info(thought)

            elif event_type == "decision":
                decision = event.get("decision", "")
                reason = event.get("reason", "")

                st.markdown(f"**Decision:** {decision}")
                if reason:
                    st.caption(reason)

            elif event_type == "error":
                error_msg = event.get("error", event.get("message", "Unknown error"))
                st.error(error_msg)

            # Show full event data
            with st.expander("📋 Full Event Data"):
                st.json(event)


def _render_run_actions(run_id: str, run_data: dict, run_config: dict):
    """Render action buttons for completed run."""
    st.markdown("---")
    st.markdown("#### 🎛️ Actions")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("🔄 Rerun", key=f"rerun_{run_id}", use_container_width=True):
            st.info("Creating new run with same configuration...")
            _execute_agent_run(run_config)

    with col2:
        answer = run_data.get("answer") or run_data.get("result", "")
        if answer:
            st.download_button(
                label="📋 Copy Answer",
                data=answer,
                file_name=f"agent_answer_{run_id}.txt",
                mime="text/plain",
                key=f"copy_answer_{run_id}",
                use_container_width=True,
            )

    with col3:
        json_str = json.dumps(run_data, indent=2)
        st.download_button(
            label="📥 Export JSON",
            data=json_str,
            file_name=f"agent_run_{run_id}.json",
            mime="application/json",
            key=f"export_json_{run_id}",
            use_container_width=True,
        )

    with col4:
        # Continue in session (if available)
        session_id = run_data.get("session_id")
        if session_id:
            if st.button("💬 Continue in Session", key=f"continue_session_{run_id}", use_container_width=True):
                st.session_state.selected_session_id = session_id
                st.info(f"Navigate to **Sessions** tab to view session `{session_id}`")


def _render_active_runs():
    """Render list of active/recent runs."""
    st.markdown("### 📜 Recent Runs")

    if "active_runs" not in st.session_state or not st.session_state.active_runs:
        st.info("📭 No recent runs. Create one above to get started!")
        return

    for run_id in st.session_state.active_runs:
        with st.expander(f"🤖 Run: `{run_id}`"):
            success, data, error = get_agent_run(run_id)

            if success and data:
                status = data.get("status", "unknown")
                answer = data.get("answer") or data.get("result")

                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric("Status", status)

                with col2:
                    iterations = data.get("iterations_used", 0)
                    st.metric("Iterations", iterations)

                with col3:
                    duration = data.get("duration_ms", 0)
                    st.metric("Duration", f"{duration}ms")

                if answer:
                    st.markdown("**Answer:**")
                    st.info(answer[:200] + "..." if len(answer) > 200 else answer)

                if st.button("🔍 View Full Details", key=f"view_details_{run_id}"):
                    render_json_drawer(data, title=f"Run {run_id} Details")
            else:
                st.error(f"❌ Failed to fetch run: {error}")


def _render_sessions():
    """Render agent sessions management with full conversation history."""
    st.subheader("Agent Sessions")
    st.caption("Manage multi-turn conversation sessions with AI agents")

    # Check if user selected a session from runs tab
    if "selected_session_id" in st.session_state and st.session_state.selected_session_id:
        st.info(f"🔗 **Linked from Run:** Viewing session `{st.session_state.selected_session_id}`")

    # Create new session
    with st.expander("➕ Create New Session"), st.form("create_session_form_sessions_tab"):
        session_name = st.text_input("Session Name", placeholder="My Agent Session")
        session_description = st.text_area("Description", placeholder="What is this session for?")

        metadata = st.text_area(
            "Metadata (JSON)",
            placeholder='{"project": "demo", "user": "alice"}',
            help="Optional metadata to attach to the session",
        )

        submitted = st.form_submit_button("Create Session", type="primary")

        if submitted:
            session_data = {}

            if session_name:
                session_data["name"] = session_name
            if session_description:
                session_data["description"] = session_description

            if metadata.strip():
                try:
                    meta_dict = json.loads(metadata)
                    session_data["metadata"] = meta_dict
                except json.JSONDecodeError:
                    st.error("❌ Invalid JSON in metadata")
                    st.stop()

            with st.spinner("Creating session..."):
                success, data, error = create_agent_session(session_data)

            if success and data:
                session_id = data.get("session_id")
                st.success(f"✅ Session created: `{session_id}`")
                st.balloons()
                st.rerun()
            else:
                st.error(f"❌ Failed to create session: {error}")

    st.markdown("---")

    # List sessions
    st.markdown("### 📂 All Sessions")

    _col1, col2 = st.columns([5, 1])

    with col2:
        if st.button("🔄 Refresh", key="refresh_sessions"):
            st.rerun()

    success, data, error = list_agent_sessions()

    if success and data:
        sessions = data.get("items", [])

        if sessions:
            render_table(sessions, key_prefix="sessions_table")

            st.markdown("---")
            st.markdown("### 💬 Session Workspace")

            # Session selector
            session_options = {
                f"{s.get('name', 'Unnamed')} ({s.get('session_id')[:8]}...)": s.get("session_id")
                for s in sessions
                if s.get("session_id")
            }

            # Check if pre-selected from runs tab
            default_index = 0
            if "selected_session_id" in st.session_state and st.session_state.selected_session_id:
                matching_keys = [k for k, v in session_options.items() if v == st.session_state.selected_session_id]
                if matching_keys:
                    default_index = list(session_options.keys()).index(matching_keys[0])

            selected_key = st.selectbox(
                "Select Session", options=list(session_options.keys()), index=default_index, key="session_selector"
            )

            selected_session_id = session_options[selected_key]

            if selected_session_id:
                _render_session_workspace(selected_session_id)
        else:
            st.info("📭 No sessions found. Create one above to get started!")
    else:
        st.error(f"❌ Failed to list sessions: {error}")


def _render_session_workspace(session_id: str):
    """Render interactive session workspace with conversation history and messaging."""

    # Tabs for different views
    session_tabs = st.tabs(["💬 Conversation", "📊 Details", "⚙️ Actions"])

    with session_tabs[0]:
        _render_session_conversation(session_id)

    with session_tabs[1]:
        _render_session_details(session_id)

    with session_tabs[2]:
        _render_session_actions(session_id)


def _render_session_conversation(session_id: str):
    """Render conversation history and messaging interface."""
    st.markdown("#### 💬 Conversation History")

    # Fetch session steps
    col1, col2 = st.columns([5, 1])

    with col2:
        if st.button("🔄 Refresh History", key=f"refresh_history_{session_id}"):
            st.rerun()

    success, steps_data, error = list_session_steps(session_id)

    if success and steps_data:
        steps = steps_data.get("items", steps_data.get("steps", []))

        if steps:
            st.caption(f"📊 Total Steps: {len(steps)}")

            # Display conversation timeline
            for idx, step in enumerate(steps):
                _render_conversation_step(step, idx)

            st.markdown("---")
        else:
            st.info("📭 No conversation history yet. Send a message below to start!")
    elif error:
        st.warning(f"⚠️ Could not load conversation history: {error}")
    else:
        st.info("📭 No conversation history available")

    # Message input form
    st.markdown("---")
    st.markdown("#### ✉️ Send Message")

    with st.form(f"send_message_form_{session_id}"):
        message = st.text_area(
            "Your Message",
            placeholder="Type your message to the agent...",
            height=100,
            key=f"message_input_{session_id}",
        )

        col1, col2 = st.columns([4, 1])

        with col1:
            submitted = st.form_submit_button("📤 Send Message", type="primary", use_container_width=True)

        with col2:
            add_step_mode = st.form_submit_button("➕ Add Step", use_container_width=True)

        if submitted:
            if not message.strip():
                st.error("❌ Please enter a message")
            else:
                _send_message_to_session(session_id, message)

        if add_step_mode:
            if not message.strip():
                st.error("❌ Please enter step content")
            else:
                _add_step_to_session(session_id, message)


def _render_conversation_step(step: dict, index: int):
    """Render a single conversation step."""
    step.get("type", "message")
    role = step.get("role", "user")
    content = step.get("content", step.get("message", ""))
    timestamp = step.get("timestamp", step.get("created_at", ""))

    # Determine styling based on role
    if role == "user":
        icon = "👤"
        bg_color = "#e3f2fd"  # Light blue
    elif role == "assistant":
        icon = "🤖"
        bg_color = "#f1f8e9"  # Light green
    elif role == "system":
        icon = "⚙️"
        bg_color = "#fafafa"  # Light gray
    else:
        icon = "💬"
        bg_color = "#fff9e6"  # Light yellow

    # FIXED: Use static container key to prevent duplicate rendering
    container_key = f"conversation_step_{index}_{hash(str(step))}"
    with st.container(key=container_key):
        st.markdown(
            f"""
        <div style="background-color: {bg_color}; padding: 15px; border-radius: 8px; margin-bottom: 10px;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                <strong>{icon} {role.title()}</strong>
                <small style="color: #666;">{timestamp[:19] if timestamp else f'Step {index + 1}'}</small>
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )

        st.markdown(content)

        # Show additional metadata if available
        metadata = step.get("metadata", {})
        if metadata:
            with st.expander("📋 Step Metadata"):
                st.json(metadata)

        st.markdown("---")


def _send_message_to_session(session_id: str, message: str):
    """Send a message to the session."""
    with st.spinner("📤 Sending message..."):
        success, data, error = send_agent_message(session_id, message)

    if success:
        st.success("✅ Message sent successfully!")

        # Show response if available
        response = data.get("response") if data else None
        if response:
            st.markdown("**Agent Response:**")
            st.info(response)

        st.rerun()
    else:
        st.error(f"❌ Failed to send message: {error}")


def _add_step_to_session(session_id: str, content: str):
    """Add a step to the session manually."""
    step_data = {"type": "message", "role": "user", "content": content}

    with st.spinner("➕ Adding step..."):
        success, _data, error = add_session_step(session_id, step_data)

    if success:
        st.success("✅ Step added successfully!")
        st.rerun()
    else:
        st.error(f"❌ Failed to add step: {error}")


def _render_session_details(session_id: str):
    """Render detailed session view."""
    success, data, error = get_agent_session(session_id)

    if not success or not data:
        st.error(f"❌ Failed to fetch session: {error}")
        return

    # Session metadata
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Session ID", session_id[:16] + "...")

    with col2:
        status = data.get("status", "unknown")
        st.metric("Status", status)

    with col3:
        created_at = data.get("created_at", "N/A")
        st.metric("Created", created_at[:10] if created_at != "N/A" else "N/A")

    # Session name and description
    name = data.get("name", "Unnamed Session")
    description = data.get("description", "")

    st.markdown(f"**Name:** {name}")
    if description:
        st.markdown(f"**Description:** {description}")

    # Additional metadata
    metadata = data.get("metadata", {})
    if metadata:
        st.markdown("---")
        st.markdown("#### 📋 Session Metadata")
        st.json(metadata)

    # Full session data
    st.markdown("---")
    render_json_drawer(data, title="Complete Session Data")


def _render_session_actions(session_id: str):
    """Render session action controls."""
    st.markdown("#### 🎛️ Session Actions")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("##### 🗑️ Cancel Session")
        st.caption("Stop the session and mark it as cancelled")

        if st.button(
            "🚫 Cancel Session", key=f"cancel_session_{session_id}", type="secondary", use_container_width=True
        ):
            with st.spinner("Cancelling session..."):
                cancel_success, _, cancel_error = cancel_agent_session(session_id)

            if cancel_success:
                st.success("✅ Session cancelled")
                st.rerun()
            else:
                st.error(f"❌ Failed to cancel: {cancel_error}")

    with col2:
        st.markdown("##### 📥 Export Session")
        st.caption("Download session data and conversation history")

        # Fetch full session data
        success, session_data, _ = get_agent_session(session_id)
        steps_success, steps_data, _ = list_session_steps(session_id)

        if success and session_data:
            # Export as JSON
            export_data = {
                "session": session_data,
                "conversation": steps_data.get("items", []) if steps_success and steps_data else [],
            }

            json_str = json.dumps(export_data, indent=2)
            st.download_button(
                label="📥 Export JSON",
                data=json_str,
                file_name=f"session_{session_id}.json",
                mime="application/json",
                key=f"export_json_{session_id}",
                use_container_width=True,
            )

            # Export as transcript
            if steps_success and steps_data:
                transcript = _generate_session_transcript(session_data, steps_data.get("items", []))

                st.download_button(
                    label="📄 Export Transcript",
                    data=transcript,
                    file_name=f"session_{session_id}_transcript.txt",
                    mime="text/plain",
                    key=f"export_transcript_{session_id}",
                    use_container_width=True,
                )


def _generate_session_transcript(session_data: dict, steps: list[dict]) -> str:
    """Generate a readable transcript of the session."""
    lines = []

    # Header
    lines.append("=" * 80)
    lines.append("SESSION TRANSCRIPT")
    lines.append("=" * 80)
    lines.append(f"Session ID: {session_data.get('session_id', 'N/A')}")
    lines.append(f"Name: {session_data.get('name', 'Unnamed Session')}")
    lines.append(f"Status: {session_data.get('status', 'unknown')}")
    lines.append(f"Created: {session_data.get('created_at', 'N/A')}")

    description = session_data.get("description", "")
    if description:
        lines.append(f"Description: {description}")

    lines.append("=" * 80)
    lines.append("")

    # Conversation
    if steps:
        lines.append("CONVERSATION HISTORY:")
        lines.append("-" * 80)
        lines.append("")

        for idx, step in enumerate(steps):
            role = step.get("role", "unknown")
            content = step.get("content", step.get("message", ""))
            timestamp = step.get("timestamp", step.get("created_at", ""))

            lines.append(f"[{idx + 1}] {role.upper()} - {timestamp[:19] if timestamp else 'No timestamp'}")
            lines.append("")
            lines.append(content)
            lines.append("")
            lines.append("-" * 80)
            lines.append("")
    else:
        lines.append("No conversation history available.")
        lines.append("")

    lines.append("=" * 80)
    lines.append(f"End of transcript - {len(steps)} total steps")
    lines.append("=" * 80)

    return "\n".join(lines)
