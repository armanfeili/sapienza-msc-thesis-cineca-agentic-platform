"""
Models tab - model instances and providers management.
"""

from typing import Any

import streamlit as st
from components import render_json_drawer, render_table
from state import get_active_token

from api import (
    delete_model_instance,
    delete_provider,
    get_main_provider,
    get_model_defaults,
    get_model_instance,
    get_provider,
    list_model_instances,
    list_providers,
    register_provider,
    set_default_provider,
    set_model_defaults,
    test_model_instance,
    update_provider,
)


def _render_defaults_editor():
    """Render defaults editor modal/expander."""
    with st.expander("⚙️ Configure Default Model", expanded=True):
        st.markdown(
            """
        Set the default model instance and provider for agent runs.
        If not specified in a run request, these defaults will be used.
        """
        )

        # Fetch available instances
        success, instances_data, error = list_model_instances()

        if not success or not instances_data:
            st.error(f"Could not load instances: {error}")
            return

        instances = instances_data.get("items", [])

        if not instances:
            st.warning("⚠️ No model instances available. Please create one first.")
            return

        # Create instance selector
        instance_options = {
            "None": None,
            **{
                f"{inst.get('display_name', inst.get('instance_id'))} ({inst.get('instance_id')})": inst.get(
                    "instance_id"
                )
                for inst in instances
            },
        }

        # Get current defaults
        current_defaults, _, _ = get_model_defaults()
        current_instance = current_defaults.get("default_instance_id") if current_defaults else None

        # Find current selection key
        current_key = "None"
        for key, value in instance_options.items():
            if value == current_instance:
                current_key = key
                break

        selected_key = st.selectbox(
            "Default Model Instance",
            options=list(instance_options.keys()),
            index=list(instance_options.keys()).index(current_key),
            key="default_instance_selector",
            help="This instance will be used for agent runs when no specific model is requested",
        )

        selected_instance_id = instance_options[selected_key]

        # Show selected instance details
        if selected_instance_id:
            selected_instance = next((i for i in instances if i.get("instance_id") == selected_instance_id), None)
            if selected_instance:
                st.info(
                    f"**Provider:** {selected_instance.get('provider_id', 'N/A')} | **Model:** {selected_instance.get('model_id', 'N/A')}"
                )

        col1, col2 = st.columns(2)

        with col1:
            if st.button("💾 Save Defaults", key="save_defaults", type="primary"):
                defaults_payload = {}

                if selected_instance_id:
                    defaults_payload["default_instance_id"] = selected_instance_id

                    # Also set provider from instance
                    selected_instance = next(
                        (i for i in instances if i.get("instance_id") == selected_instance_id), None
                    )
                    if selected_instance and selected_instance.get("provider_id"):
                        defaults_payload["default_provider_id"] = selected_instance["provider_id"]

                if defaults_payload:
                    success, _data, error = set_model_defaults(defaults_payload)

                    if success:
                        st.success("✅ Defaults updated successfully!")
                        st.session_state.show_defaults_editor = False
                        st.rerun()
                    else:
                        st.error(f"❌ Failed to update defaults: {error}")
                else:
                    st.warning("Please select an instance")

        with col2:
            if st.button("❌ Cancel", key="cancel_defaults"):
                st.session_state.show_defaults_editor = False
                st.rerun()


def list_llm_models() -> tuple[bool, list[dict[str, Any]] | None, str | None]:
    """
    List available LLM models from all providers.

    Returns:
        Tuple of (success, models_list, error)
        models_list contains: [{id, name, provider, capabilities}, ...]
    """
    # Get model instances and providers
    success, instances, error = list_model_instances()

    if not success:
        return False, None, error or "Failed to fetch model instances"

    if not instances:
        return True, [], None

    # Extract models with their metadata
    models = []
    for instance in instances:
        model = {
            "id": instance.get("instance_id", "unknown"),
            "name": instance.get("display_name", instance.get("instance_id", "Unnamed Model")),
            "provider": instance.get("provider_id", "unknown"),
            "model_type": instance.get("model_id", "unknown"),
            "capabilities": instance.get("capabilities", []),
            "status": instance.get("status", "unknown"),
        }
        models.append(model)

    return True, models, None


def render_models_tab():
    """Render models and providers tab."""
    st.header("🧠 Models & Providers")

    # Check admin permissions
    token = get_active_token()
    has_admin = token and "admin:all" in token.scopes if token else False

    sub_tabs = st.tabs(["📦 Model Instances", "🔌 Providers (Admin)" if has_admin else "🔌 Providers"])

    with sub_tabs[0]:
        _render_model_instances()

    with sub_tabs[1]:
        if has_admin:
            _render_providers()
        else:
            st.warning("⚠️ Admin access required for provider management")


def _render_model_instances():
    """Render model instances management."""
    st.subheader("Model Instances")

    # Show current defaults with management
    st.markdown("### 🎯 Default Model Configuration")

    success, defaults_data, error = get_model_defaults()

    has_defaults = False
    if success and defaults_data:
        default_instance = defaults_data.get("default_instance_id")
        default_provider = defaults_data.get("default_provider_id")

        if default_instance or default_provider:
            has_defaults = True

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Default Instance", default_instance or "Not set")
            with col2:
                st.metric("Default Provider", default_provider or "Not set")
            with col3:
                if st.button("🔄 Change Defaults", key="change_defaults"):
                    st.session_state.show_defaults_editor = True

    # Show CTA if no defaults
    if not has_defaults:
        st.error(
            """
            ⚠️ **No Default Model Configured**

            A default model must be set before agent runs can be created.
            """,
            icon="🚫",
        )
        if st.button("⚙️ Set Default Model Now", key="set_defaults_cta", type="primary"):
            st.session_state.show_defaults_editor = True

    # Show defaults editor if requested
    if st.session_state.get("show_defaults_editor", False):
        _render_defaults_editor()

    st.markdown("---")

    # List instances
    st.markdown("### All Model Instances")

    # Enhanced Filters
    filter_cols = st.columns([2, 2, 2, 1])

    with filter_cols[0]:
        provider_filter = st.text_input(
            "🔌 Filter by Provider", key="instance_provider_filter", placeholder="e.g., openai"
        )

    with filter_cols[1]:
        status_filter = st.selectbox("📊 Status", ["all", "active", "inactive", "error"], key="instance_status_filter")

    with filter_cols[2]:
        capability_filter = st.multiselect(
            "⚡ Capabilities",
            options=["chat", "completion", "embedding", "vision", "function_calling"],
            key="instance_capability_filter",
            help="Filter instances by capabilities",
        )

    with filter_cols[3]:
        if st.button("🔄 Refresh", key="refresh_instances"):
            st.rerun()

    # Build query params
    params = {}
    if provider_filter:
        params["provider"] = provider_filter
    if status_filter != "all":
        params["status"] = status_filter
    if capability_filter:
        params["capabilities"] = ",".join(capability_filter)

    # Fetch instances
    success, data, error = list_model_instances(params)

    if success and data:
        instances = data.get("items", [])

        if instances:
            # Export button
            col1, col2 = st.columns([5, 1])
            with col1:
                st.caption(f"Found {len(instances)} instance(s)")
            with col2:
                if st.button("📥 Export CSV", key="export_instances"):
                    _export_instances_to_csv(instances)

            # Render instances table with click handlers
            _render_instances_table_with_drawer(instances)
        else:
            st.info("📭 No instances found matching your filters")
    else:
        st.error(f"❌ Failed to list instances: {error}")


def _render_providers():
    """Render providers management (admin only)."""
    st.subheader("Model Providers")

    # Main/Default Provider Status
    st.markdown("### 🎯 Main Provider Status")
    _render_main_provider_status()

    st.markdown("---")

    # Provider Management Tabs
    provider_tabs = st.tabs(["📋 All Providers", "➕ Register Provider", "⚙️ Provider Actions"])

    with provider_tabs[0]:
        _render_providers_list()

    with provider_tabs[1]:
        _render_register_provider_form()

    with provider_tabs[2]:
        _render_provider_actions()


def _render_main_provider_status():
    """Display main/default provider status.

    FIXED: Improved error handling and null checks for better status display.
    """
    success, main_data, error = get_main_provider()

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Current Main Provider**")
        if success and main_data:
            provider_id = main_data.get("provider_id") or "N/A"
            provider_name = main_data.get("name") or "Unknown"
            provider_type = main_data.get("type") or "unknown"

            # Only show if we have valid data
            if provider_id != "N/A" and provider_name != "Unknown":
                st.info(f"✅ **{provider_name}** (`{provider_id}`) - Type: `{provider_type}`")

                # Show health if available
                health = main_data.get("health", {})
                if health and isinstance(health, dict):
                    health_status = health.get("status", "unknown")
                    if health_status != "unknown":
                        health_emoji = (
                            "✅" if health_status == "healthy" else "⚠️" if health_status == "degraded" else "❌"
                        )
                        st.caption(f"{health_emoji} Health: {health_status}")
            else:
                st.warning("⚠️ Main provider data is incomplete")
        elif error:
            # Show specific error message
            error_msg = str(error)
            if "404" in error_msg or "not found" in error_msg.lower():
                st.info("ℹ️ No main provider configured yet. Use the **Register Provider** tab to add one.")
            else:
                st.error(f"❌ Error loading main provider: {error_msg}")
        else:
            st.info("ℹ️ No main provider configured yet")

    with col2:
        st.markdown("**Default Provider (from Defaults)**")
        success_def, defaults_data, error_def = get_model_defaults()

        if success_def and defaults_data:
            default_provider = defaults_data.get("default_provider_id")

            if default_provider:
                st.info(f"✅ `{default_provider}`")

                # Check if main == default
                if success and main_data and main_data.get("provider_id") == default_provider:
                    st.caption("✅ Matches main provider")
                elif success and main_data:
                    st.caption("⚠️ Different from main provider")
            else:
                st.warning("⚠️ No default provider set in model defaults")
        elif error_def:
            error_msg = str(error_def)
            if "404" in error_msg or "not found" in error_msg.lower():
                st.info("ℹ️ No model defaults configured yet. Set defaults in the **Model Instances** tab.")
            else:
                st.error(f"❌ Error loading defaults: {error_msg}")
        else:
            st.info("ℹ️ No model defaults configured yet")


def _render_providers_list():
    """Display all providers in a table with actions."""
    st.markdown("### All Registered Providers")

    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption("List of all registered model providers with their status and configuration")
    with col2:
        if st.button("🔄 Refresh", key="refresh_providers"):
            st.rerun()

    success, data, error = list_providers()

    if success and data:
        providers = data.get("items", [])

        if providers:
            # Get main provider for highlighting
            main_success, main_data, _ = get_main_provider()
            main_provider_id = main_data.get("provider_id") if main_success and main_data else None

            # Get default provider for highlighting
            defaults_success, defaults_data, _ = get_model_defaults()
            default_provider_id = (
                defaults_data.get("default_provider_id") if defaults_success and defaults_data else None
            )

            # Enhance provider data with badges
            enhanced_providers = []
            for provider in providers:
                enhanced = provider.copy()
                badges = []

                if provider.get("provider_id") == main_provider_id:
                    badges.append("🌟 MAIN")
                if provider.get("provider_id") == default_provider_id:
                    badges.append("⭐ DEFAULT")

                if badges:
                    enhanced["badges"] = " | ".join(badges)
                else:
                    enhanced["badges"] = ""

                enhanced_providers.append(enhanced)

            # Render table
            render_table(enhanced_providers, key_prefix="providers_table")

            st.caption(f"Total providers: {len(providers)}")
        else:
            st.info("📭 No providers registered yet. Use the **Register Provider** tab to add one.")
    else:
        st.error(f"❌ Failed to load providers: {error}")


def _render_register_provider_form():
    """Form to register a new provider."""
    st.markdown("### Register New Provider")
    st.caption("Add a new LLM provider to the system")

    with st.form("register_provider_form"):
        provider_name = st.text_input(
            "Provider Name *", placeholder="e.g., OpenAI Production", help="Human-readable name for this provider"
        )

        provider_type = st.selectbox(
            "Provider Type *",
            options=["openai", "azure", "anthropic", "huggingface", "ollama", "custom"],
            help="The LLM provider type",
        )

        col1, col2 = st.columns(2)

        with col1:
            base_url = st.text_input(
                "Base URL", placeholder="https://api.openai.com/v1", help="Optional: Custom API endpoint URL"
            )

        with col2:
            api_key_hint = st.text_input(
                "API Key", type="password", placeholder="sk-...", help="Optional: API key (will be stored securely)"
            )

        provider_config = st.text_area(
            "Additional Configuration (JSON)",
            placeholder='{\n  "timeout": 30,\n  "max_retries": 3\n}',
            help="Optional: Additional provider-specific configuration as JSON",
            height=150,
        )

        set_as_default = st.checkbox(
            "Set as default provider", help="Make this the default provider for new model instances"
        )

        submitted = st.form_submit_button("✅ Register Provider", type="primary")

        if submitted:
            if not provider_name:
                st.error("❌ Provider name is required")
                return

            import json

            provider_data = {
                "name": provider_name,
                "type": provider_type,
            }

            # Build config object
            config = {}

            if base_url:
                config["base_url"] = base_url

            if api_key_hint:
                config["api_key"] = api_key_hint

            # Merge with additional config
            if provider_config:
                try:
                    additional_config = json.loads(provider_config)
                    config.update(additional_config)
                except json.JSONDecodeError as e:
                    st.error(f"❌ Invalid JSON in additional configuration: {e}")
                    return

            if config:
                provider_data["config"] = config

            # Register provider
            with st.spinner("Registering provider..."):
                success, data, error = register_provider(provider_data)

            if success and data:
                provider_id = data.get("provider_id")
                st.success(f"✅ Provider registered successfully: `{provider_id}`")

                # Set as default if requested
                if set_as_default and provider_id:
                    set_success, _, set_error = set_default_provider(provider_id)
                    if set_success:
                        st.success("✅ Set as default provider")
                    else:
                        st.warning(f"⚠️ Provider registered but failed to set as default: {set_error}")

                st.balloons()
                st.rerun()
            else:
                st.error(f"❌ Registration failed: {error}")


def _render_provider_actions():
    """Provider detail view, edit, delete, and set default actions."""
    st.markdown("### Provider Actions")
    st.caption("View, edit, test, or delete an existing provider")

    # Provider selector
    success, data, error = list_providers()

    if not success or not data:
        st.error(f"❌ Could not load providers: {error}")
        return

    providers = data.get("items", [])

    if not providers:
        st.info("📭 No providers available. Register one first.")
        return

    # Create provider selector
    provider_options = {f"{p.get('name', 'Unnamed')} ({p.get('provider_id')})": p.get("provider_id") for p in providers}

    selected_key = st.selectbox(
        "Select Provider", options=list(provider_options.keys()), key="provider_action_selector"
    )

    selected_provider_id = provider_options[selected_key]

    if not selected_provider_id:
        return

    st.markdown("---")

    # Action tabs
    action_tabs = st.tabs(["📊 View Details", "✏️ Edit", "⭐ Set Default", "🗑️ Delete"])

    with action_tabs[0]:
        _render_provider_details(selected_provider_id)

    with action_tabs[1]:
        _render_provider_edit(selected_provider_id)

    with action_tabs[2]:
        _render_set_default_provider(selected_provider_id)

    with action_tabs[3]:
        _render_delete_provider(selected_provider_id)


def _render_provider_details(provider_id: str):
    """Display detailed provider information."""
    st.markdown(f"#### Provider Details: `{provider_id}`")

    success, data, error = get_provider(provider_id)

    if success and data:
        # Key metrics
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Name", data.get("name", "N/A"))

        with col2:
            st.metric("Type", data.get("type", "unknown"))

        with col3:
            health = data.get("health", {})
            health_status = health.get("status", "unknown")
            st.metric("Health", health_status)

        # Configuration (redacted)
        config = data.get("config", {})
        if config:
            st.markdown("**Configuration:**")

            # Redact sensitive fields
            redacted_config = config.copy()
            if "api_key" in redacted_config:
                redacted_config["api_key"] = "***REDACTED***"

            st.json(redacted_config)

        # Full details
        st.markdown("---")
        render_json_drawer(data, title="Full Provider Details")
    else:
        st.error(f"❌ Failed to fetch provider: {error}")


def _render_provider_edit(provider_id: str):
    """Edit provider configuration."""
    st.markdown(f"#### Edit Provider: `{provider_id}`")

    # Fetch current data
    success, current_data, error = get_provider(provider_id)

    if not success or not current_data:
        st.error(f"❌ Could not load provider: {error}")
        return

    with st.form(f"edit_provider_form_{provider_id}"):
        new_name = st.text_input("Provider Name", value=current_data.get("name", ""), help="Update the display name")

        new_config = st.text_area(
            "Configuration (JSON)",
            value="",
            placeholder='{\n  "timeout": 60\n}',
            help="Update configuration (only fields provided will be updated)",
            height=150,
        )

        submitted = st.form_submit_button("💾 Save Changes", type="primary")

        if submitted:
            import json

            update_data = {}

            if new_name and new_name != current_data.get("name"):
                update_data["name"] = new_name

            if new_config:
                try:
                    config_update = json.loads(new_config)
                    update_data["config"] = config_update
                except json.JSONDecodeError as e:
                    st.error(f"❌ Invalid JSON: {e}")
                    return

            if not update_data:
                st.warning("⚠️ No changes to save")
                return

            with st.spinner("Saving changes..."):
                success, _data, error = update_provider(provider_id, update_data)

            if success:
                st.success("✅ Provider updated successfully")
                st.rerun()
            else:
                st.error(f"❌ Update failed: {error}")


def _render_set_default_provider(provider_id: str):
    """Set a provider as the default."""
    st.markdown(f"#### Set Default Provider: `{provider_id}`")

    st.info(
        """
    Setting a provider as default will make it the primary provider for:
    - New model instance creation
    - Agent runs (when used with model defaults)
    """
    )

    if st.button(f"⭐ Set `{provider_id}` as Default", key=f"set_default_{provider_id}", type="primary"):
        with st.spinner("Setting default provider..."):
            success, _data, error = set_default_provider(provider_id)

        if success:
            st.success(f"✅ `{provider_id}` is now the default provider")
            st.rerun()
        else:
            st.error(f"❌ Failed to set default: {error}")


def _render_delete_provider(provider_id: str):
    """Delete a provider with confirmation."""
    st.markdown(f"#### Delete Provider: `{provider_id}`")

    st.error(
        """
    ⚠️ **Warning: This action cannot be undone**

    Deleting a provider will:
    - Remove all provider configuration
    - Potentially break model instances using this provider
    - Remove this provider from the system
    """
    )

    confirm_key = f"confirm_delete_provider_{provider_id}"

    if st.checkbox("I understand the consequences", key=confirm_key):
        if st.button(f"🗑️ Delete `{provider_id}`", key=f"delete_{provider_id}", type="secondary"):
            with st.spinner("Deleting provider..."):
                success, _, error = delete_provider(provider_id)

            if success:
                st.success(f"✅ Provider `{provider_id}` deleted")
                st.rerun()
            else:
                st.error(f"❌ Deletion failed: {error}")


def _display_instance_details(instance_id: str):
    """Display detailed instance information."""
    success, data, error = get_model_instance(instance_id)

    if success and data:
        st.success(f"✅ Instance: {instance_id}")

        # Key metrics
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Provider", data.get("provider_id", "N/A"))

        with col2:
            st.metric("Status", data.get("status", "unknown"))

        with col3:
            health = data.get("health", {})
            health_status = health.get("status", "unknown")
            st.metric("Health", health_status)

        # Full details
        render_json_drawer(data, title="Full Instance Details")
    else:
        st.error(f"Failed to fetch instance: {error}")


def _render_instances_table_with_drawer(instances: list[dict]):
    """Render instances table with click-to-open drawer functionality."""
    import pandas as pd

    # Prepare table data
    table_data = []
    for instance in instances:
        capabilities = instance.get("capabilities", [])
        cap_str = ", ".join(capabilities[:3]) if capabilities else "N/A"
        if len(capabilities) > 3:
            cap_str += f" +{len(capabilities) - 3}"

        table_data.append(
            {
                "ID": instance.get("instance_id", "N/A"),
                "Name": instance.get("display_name", instance.get("instance_id", "N/A")),
                "Provider": instance.get("provider_id", "N/A"),
                "Model": instance.get("model_id", "N/A"),
                "Status": instance.get("status", "unknown"),
                "Capabilities": cap_str,
            }
        )

    df = pd.DataFrame(table_data)

    # Display table with selection
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "ID": st.column_config.TextColumn("Instance ID", width="medium"),
            "Name": st.column_config.TextColumn("Display Name", width="medium"),
            "Provider": st.column_config.TextColumn("Provider", width="small"),
            "Model": st.column_config.TextColumn("Model", width="medium"),
            "Status": st.column_config.TextColumn("Status", width="small"),
            "Capabilities": st.column_config.TextColumn("Capabilities", width="medium"),
        },
    )

    # Instance selector for drawer
    st.markdown("---")
    st.markdown("#### 🔍 Instance Details & Actions")

    instance_ids = [inst.get("instance_id") for inst in instances if inst.get("instance_id")]

    if not instance_ids:
        st.warning("No instances available")
        return

    # Create friendly display names
    instance_options = {
        f"{inst.get('display_name', inst.get('instance_id'))} ({inst.get('instance_id')})": inst.get("instance_id")
        for inst in instances
        if inst.get("instance_id")
    }

    selected_display = st.selectbox(
        "Select instance to view details",
        options=list(instance_options.keys()),
        key="instance_detail_selector",
        help="Choose an instance to view details, test, or delete",
    )

    selected_instance_id = instance_options[selected_display]

    if selected_instance_id:
        _render_instance_detail_drawer(selected_instance_id)


def _render_instance_detail_drawer(instance_id: str):
    """Render detailed instance drawer with actions."""
    success, data, error = get_model_instance(instance_id)

    if not success or not data:
        st.error(f"❌ Could not load instance: {error}")
        return

    # Drawer tabs
    drawer_tabs = st.tabs(["📊 Overview", "🧪 Test", "⚙️ Configuration", "🗑️ Delete"])

    with drawer_tabs[0]:
        _render_instance_overview(data)

    with drawer_tabs[1]:
        _render_instance_test(instance_id)

    with drawer_tabs[2]:
        _render_instance_configuration(data)

    with drawer_tabs[3]:
        _render_instance_delete(instance_id)


def _render_instance_overview(instance_data: dict):
    """Render instance overview tab."""
    st.markdown("### Instance Overview")

    # Key metrics in cards
    metric_cols = st.columns(4)

    with metric_cols[0]:
        st.metric("Instance ID", instance_data.get("instance_id", "N/A"))

    with metric_cols[1]:
        st.metric("Provider", instance_data.get("provider_id", "N/A"))

    with metric_cols[2]:
        status = instance_data.get("status", "unknown")
        status_emoji = "✅" if status == "active" else "⚠️" if status == "inactive" else "❌"
        st.metric("Status", f"{status_emoji} {status}")

    with metric_cols[3]:
        health = instance_data.get("health", {})
        health_status = health.get("status", "unknown")
        health_emoji = "✅" if health_status == "healthy" else "⚠️" if health_status == "degraded" else "❌"
        st.metric("Health", f"{health_emoji} {health_status}")

    st.markdown("---")

    # Model details
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Model Information**")
        st.write(f"**Model ID:** `{instance_data.get('model_id', 'N/A')}`")
        st.write(f"**Display Name:** {instance_data.get('display_name', 'N/A')}")
        st.write(f"**Description:** {instance_data.get('description', 'No description')}")

    with col2:
        st.markdown("**Capabilities**")
        capabilities = instance_data.get("capabilities", [])
        if capabilities:
            for cap in capabilities:
                st.write(f"⚡ {cap}")
        else:
            st.write("No capabilities listed")

    # Performance metrics if available
    metrics = instance_data.get("metrics", {})
    if metrics:
        st.markdown("---")
        st.markdown("**Performance Metrics**")

        perf_cols = st.columns(4)

        with perf_cols[0]:
            avg_latency = metrics.get("avg_latency_ms", 0)
            st.metric("Avg Latency", f"{avg_latency}ms")

        with perf_cols[1]:
            total_requests = metrics.get("total_requests", 0)
            st.metric("Total Requests", total_requests)

        with perf_cols[2]:
            success_rate = metrics.get("success_rate", 0)
            st.metric("Success Rate", f"{success_rate}%")

        with perf_cols[3]:
            total_tokens = metrics.get("total_tokens", 0)
            st.metric("Total Tokens", total_tokens)


def _render_instance_test(instance_id: str):
    """Render instance test tab."""
    st.markdown("### 🧪 Test Model Instance")
    st.caption("Send a test prompt to verify the instance is working correctly")

    with st.form(f"test_instance_form_{instance_id}"):
        test_prompt = st.text_area(
            "Test Prompt",
            value="What is the capital of France?",
            height=100,
            help="Enter a prompt to test the model instance",
        )

        advanced_options = st.expander("⚙️ Advanced Options")
        with advanced_options:
            max_tokens = st.number_input("Max Tokens", min_value=1, max_value=4096, value=100)
            temperature = st.slider("Temperature", min_value=0.0, max_value=2.0, value=0.7, step=0.1)

        submitted = st.form_submit_button("🚀 Run Test", type="primary")

        if submitted:
            if not test_prompt:
                st.error("❌ Please enter a test prompt")
                return

            test_data = {"prompt": test_prompt, "max_tokens": max_tokens, "temperature": temperature}

            with st.spinner("Testing instance..."):
                success, data, error = test_model_instance(instance_id, test_data)

            if success and data:
                st.success("✅ Test completed successfully!")

                # Show results
                result_cols = st.columns(3)

                with result_cols[0]:
                    latency = data.get("latency_ms", 0)
                    st.metric("⚡ Latency", f"{latency}ms")

                with result_cols[1]:
                    tokens = data.get("tokens_used", 0)
                    st.metric("🔢 Tokens Used", tokens)

                with result_cols[2]:
                    status = data.get("status", "unknown")
                    st.metric("📊 Status", status)

                # Show output
                output = data.get("output", data.get("response", ""))
                if output:
                    st.markdown("---")
                    st.markdown("**🤖 Model Output:**")
                    st.info(output)

                # Show raw response in expander
                with st.expander("📋 Raw Response Data"):
                    st.json(data)
            else:
                st.error(f"❌ Test failed: {error}")


def _render_instance_configuration(instance_data: dict):
    """Render instance configuration tab."""
    st.markdown("### ⚙️ Instance Configuration")

    # Display configuration (redacted)
    config = instance_data.get("config", {})

    if config:
        st.markdown("**Current Configuration:**")

        # Redact sensitive fields
        redacted_config = config.copy()
        sensitive_keys = ["api_key", "secret", "token", "password"]

        for key in redacted_config:
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                redacted_config[key] = "***REDACTED***"

        st.json(redacted_config)
    else:
        st.info("No configuration data available")

    # Show full instance data in drawer
    st.markdown("---")
    st.markdown("**Full Instance Details:**")
    render_json_drawer(instance_data, title="Complete Instance Data")


def _render_instance_delete(instance_id: str):
    """Render instance delete tab with confirmation."""
    st.markdown("### 🗑️ Delete Instance")

    st.error(
        """
    ⚠️ **Warning: This action cannot be undone**

    Deleting this instance will:
    - Remove the instance configuration
    - Stop all active connections
    - Make this instance unavailable for agent runs
    - Potentially break existing agents using this instance
    """
    )

    confirm_key = f"confirm_delete_instance_{instance_id}"

    st.markdown("---")

    if st.checkbox("⚠️ I understand the consequences and want to delete this instance", key=confirm_key):
        col1, _col2 = st.columns([1, 3])

        with col1:
            if st.button(f"🗑️ Delete `{instance_id}`", key=f"delete_btn_{instance_id}", type="secondary"):
                with st.spinner("Deleting instance..."):
                    success, _, error = delete_model_instance(instance_id)

                if success:
                    st.success(f"✅ Instance `{instance_id}` deleted successfully")
                    st.balloons()
                    st.session_state.pop(confirm_key, None)  # Clear confirmation
                    st.rerun()
                else:
                    st.error(f"❌ Deletion failed: {error}")


def _export_instances_to_csv(instances: list[dict]):
    """Export instances to CSV format."""
    from datetime import datetime

    import pandas as pd

    # Prepare export data
    export_data = []
    for instance in instances:
        capabilities = instance.get("capabilities", [])
        cap_str = ", ".join(capabilities) if capabilities else ""

        export_data.append(
            {
                "instance_id": instance.get("instance_id", ""),
                "display_name": instance.get("display_name", ""),
                "provider_id": instance.get("provider_id", ""),
                "model_id": instance.get("model_id", ""),
                "status": instance.get("status", ""),
                "capabilities": cap_str,
                "description": instance.get("description", ""),
            }
        )

    df = pd.DataFrame(export_data)
    csv = df.to_csv(index=False)

    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"model_instances_{timestamp}.csv"

    st.download_button(
        label="📥 Download CSV", data=csv, file_name=filename, mime="text/csv", key="download_instances_csv"
    )


def _test_instance(instance_id: str):
    """Test a model instance."""
    st.markdown("### Test Instance")

    test_prompt = st.text_input("Test Prompt", value="Hello, world!", key=f"test_prompt_{instance_id}")

    if st.button("Run Test", key=f"run_test_{instance_id}"):
        test_data = {"prompt": test_prompt}

        with st.spinner("Testing instance..."):
            success, data, error = test_model_instance(instance_id, test_data)

        if success and data:
            st.success("✅ Test completed")

            # Show results
            col1, col2, col3 = st.columns(3)

            with col1:
                latency = data.get("latency_ms", 0)
                st.metric("Latency", f"{latency}ms")

            with col2:
                tokens = data.get("tokens_used", 0)
                st.metric("Tokens", tokens)

            with col3:
                status = data.get("status", "unknown")
                st.metric("Status", status)

            # Show sample output
            output = data.get("output", "")
            if output:
                st.markdown("**Output:**")
                st.text_area("Sample Output", value=output, height=150, disabled=True)
        else:
            st.error(f"Test failed: {error}")
