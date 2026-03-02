"""
Tenant selector component for multi-tenant context.
"""

import streamlit as st
from state import get_state, update_state

from api import list_tenants


def render_tenant_selector():
    """
    Render tenant selector dropdown.
    Loads tenants from API and updates session state.
    """
    state = get_state()

    # Fetch tenants if not already loaded or if refresh is requested
    if "tenants_loaded" not in st.session_state or st.session_state.get("refresh_tenants", False):
        with st.spinner("Loading tenants..."):
            success, data, error = list_tenants(size=100)

            if success and data:
                # Handle paginated response
                tenants = data.get("tenants", data.get("items", []))
                st.session_state.available_tenants = tenants
                st.session_state.tenants_loaded = True
                st.session_state.refresh_tenants = False
            else:
                st.session_state.available_tenants = []
                if error:
                    st.warning(f"⚠️ Could not load tenants: {error}")

    available_tenants = st.session_state.get("available_tenants", [])

    if not available_tenants:
        st.caption("🏢 No tenant context")
        return None

    # Create options: (tenant_id, display_name)
    tenant_options = {
        "None": None,
        **{
            f"{t.get('name', t.get('tenant_id', 'Unknown'))} ({t.get('tenant_id', 'N/A')})": t.get("tenant_id")
            or t.get("id")
            for t in available_tenants
        },
    }

    # Get current selection
    current_tenant_id = state.tenant.current
    current_key = "None"
    for key, value in tenant_options.items():
        if value == current_tenant_id:
            current_key = key
            break

    # Render selector
    selected_key = st.selectbox(
        "🏢 Tenant Context",
        options=list(tenant_options.keys()),
        index=list(tenant_options.keys()).index(current_key),
        key="tenant_selector",
        help="Select tenant context for API calls. Leave as 'None' for cross-tenant operations.",
    )

    selected_tenant_id = tenant_options[selected_key]

    # Update state if changed
    if selected_tenant_id != current_tenant_id:
        state.tenant.current = selected_tenant_id
        update_state(tenant=state.tenant)
        st.rerun()

    return selected_tenant_id


def render_tenant_chip():
    """
    Render a small chip showing current tenant context.
    """
    state = get_state()
    tenant_id = state.tenant.current

    if tenant_id:
        # Find tenant name
        available_tenants = st.session_state.get("available_tenants", [])
        tenant_name = None
        for t in available_tenants:
            if t.get("tenant_id") == tenant_id or t.get("id") == tenant_id:
                tenant_name = t.get("name", tenant_id)
                break

        display = tenant_name or tenant_id
        st.markdown(
            f"""
            <div style="
                display: inline-block;
                padding: 4px 12px;
                background-color: #e3f2fd;
                border-radius: 12px;
                border: 1px solid #2196f3;
                font-size: 0.85em;
                font-weight: 500;
                color: #1976d2;
            ">
                🏢 Tenant: {display}
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <div style="
                display: inline-block;
                padding: 4px 12px;
                background-color: #f5f5f5;
                border-radius: 12px;
                border: 1px solid #9e9e9e;
                font-size: 0.85em;
                color: #616161;
            ">
                🏢 No tenant context
            </div>
            """,
            unsafe_allow_html=True,
        )
