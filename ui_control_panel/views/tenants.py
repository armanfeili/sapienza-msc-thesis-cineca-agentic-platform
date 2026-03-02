"""
Tenants tab - tenant management.
"""

import streamlit as st
from components import confirm_action, render_json_drawer, render_table
from state import get_active_token

from api import (
    create_tenant,
    delete_tenant,
    get_tenant,
    list_tenants,
    update_tenant,
)


def render_tenants_tab():
    """Render tenants management tab."""
    st.header("🏢 Tenants")

    # Check admin permissions
    token = get_active_token()
    has_admin = token and "admin:all" in token.scopes if token else False

    if not has_admin:
        st.warning("⚠️ Admin access required for tenant management")
        return

    # Create new tenant
    with st.expander("➕ Create New Tenant"):
        tenant_name = st.text_input("Tenant Name", key="new_tenant_name")
        tenant_status = st.selectbox("Status", ["active", "inactive"], key="new_tenant_status")
        tenant_meta = st.text_area("Metadata (JSON)", key="new_tenant_meta")

        if st.button("Create Tenant", key="create_tenant"):
            import json

            tenant_data = {
                "name": tenant_name,
                "status": tenant_status,
            }

            if tenant_meta:
                try:
                    meta = json.loads(tenant_meta)
                    tenant_data["metadata"] = meta
                except:
                    st.error("Invalid JSON in metadata")
                    return

            success, data, error = create_tenant(tenant_data)

            if success:
                st.success(f"✅ Tenant created: {data.get('tenant_id')}")
                st.rerun()
            else:
                st.error(f"Failed to create tenant: {error}")

    st.markdown("---")

    # List tenants
    st.subheader("All Tenants")

    # Pagination
    col1, col2 = st.columns(2)
    with col1:
        page = st.number_input("Page", min_value=1, value=1, key="tenant_page")
    with col2:
        size = st.number_input("Page Size", min_value=10, max_value=100, value=50, key="tenant_page_size")

    if st.button("🔄 Refresh Tenants", key="refresh_tenants"):
        st.rerun()

    success, data, error = list_tenants(page, size)

    if success and data:
        tenants = data.get("items", [])

        if tenants:
            render_table(tenants, key_prefix="tenants_table")

            # Tenant actions
            st.markdown("---")
            st.subheader("Tenant Actions")

            tenant_id = st.text_input("Tenant ID", key="tenant_action_id")

            col1, col2, col3 = st.columns(3)

            with col1:
                if st.button("📊 View Details", key="view_tenant") and tenant_id:
                    _display_tenant_details(tenant_id)

            with col2:
                if st.button("✏️ Update", key="update_tenant_btn") and tenant_id:
                    _show_update_form(tenant_id)

            with col3:
                if st.button("🗑️ Delete", key="delete_tenant_btn") and tenant_id:
                    _delete_tenant(tenant_id)
        else:
            st.info("No tenants found")
    else:
        st.error(f"Failed to list tenants: {error}")


def _display_tenant_details(tenant_id: str):
    """Display detailed tenant information."""
    success, data, error = get_tenant(tenant_id)

    if success and data:
        st.success(f"✅ Tenant: {data.get('name', tenant_id)}")

        # Key info
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("ID", data.get("id", "N/A"))

        with col2:
            st.metric("Status", data.get("status", "unknown"))

        with col3:
            created = data.get("created_at", "N/A")
            st.caption(f"Created: {created}")

        # Full details
        render_json_drawer(data, title=f"Tenant {tenant_id}")
    else:
        st.error(f"Failed to fetch tenant: {error}")


def _show_update_form(tenant_id: str):
    """Show tenant update form."""
    st.markdown("### Update Tenant")

    # Fetch current data
    success, current_data, error = get_tenant(tenant_id)

    if not success:
        st.error(f"Failed to fetch tenant: {error}")
        return

    # Update form
    new_name = st.text_input("Name", value=current_data.get("name", ""), key=f"update_name_{tenant_id}")
    new_status = st.selectbox(
        "Status",
        ["active", "inactive"],
        index=0 if current_data.get("status") == "active" else 1,
        key=f"update_status_{tenant_id}",
    )

    if st.button("Save Changes", key=f"save_tenant_{tenant_id}"):
        update_data = {
            "name": new_name,
            "status": new_status,
        }

        success, _data, error = update_tenant(tenant_id, update_data)

        if success:
            st.success("✅ Tenant updated")
            st.rerun()
        else:
            st.error(f"Update failed: {error}")


def _delete_tenant(tenant_id: str):
    """Delete a tenant with confirmation."""
    st.markdown("### Delete Tenant")

    st.warning(f"⚠️ You are about to delete tenant `{tenant_id}`. This action cannot be undone.")

    def delete_action():
        success, _, error = delete_tenant(tenant_id)
        if success:
            st.success("✅ Tenant deleted")
            st.rerun()
        else:
            st.error(f"Delete failed: {error}")

    confirm_action(
        action_name=f"delete tenant {tenant_id}",
        action_fn=delete_action,
        warning_message="This will permanently delete the tenant and all associated data.",
        button_label="Delete Tenant",
        danger=True,
        key_suffix=tenant_id,
    )
