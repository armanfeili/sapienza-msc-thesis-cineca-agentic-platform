"""
Global banner component for system-wide alerts.
"""


import streamlit as st


def render_api_health_banner(is_healthy: bool, messages: list[str] | None = None):
    """
    Render a global banner showing API health status.

    FIXED: Improved error display with retry option.

    Args:
        is_healthy: Whether API is healthy
        messages: List of status messages
    """
    if not is_healthy:
        with st.container():
            st.error(
                """
                ⚠️ **API Connection Issues Detected**

                The platform API is not responding correctly. This may prevent core functionality from working.
                """,
                icon="🚨",
            )

            if messages:
                with st.expander("🔍 View Details"):
                    for msg in messages:
                        # Format messages properly
                        if msg.startswith("💡") or msg.startswith("📋") or msg.startswith("🔍"):
                            st.markdown(f"**{msg}**")
                        elif msg.startswith("   "):
                            st.markdown(f"   {msg}")
                        else:
                            st.markdown(f"- {msg}")

                    st.markdown("---")

                    # Add retry button
                    col1, _col2 = st.columns([1, 3])
                    with col1:
                        if st.button("🔄 Retry Connection Test", key="retry_api_test"):
                            # Clear health check state to trigger retest
                            if "api_health_checked" in st.session_state:
                                del st.session_state.api_health_checked
                            if "api_healthy" in st.session_state:
                                del st.session_state.api_healthy
                            if "api_health_messages" in st.session_state:
                                del st.session_state.api_health_messages
                            st.rerun()

                    st.markdown("**Troubleshooting:**")
                    st.markdown("1. Check that the API service is running: `docker compose ps app`")
                    st.markdown("2. Verify API_BASE_URL environment variable/secret")
                    st.markdown("3. Ensure network connectivity to the API")
                    st.markdown("4. Check API logs: `docker compose logs app`")
                    st.markdown("5. Try rebuilding: `docker compose up -d --build --remove-orphans app`")


def render_tenant_banner(tenant_name: str | None = None):
    """
    Render a banner showing current tenant context.

    Args:
        tenant_name: Current tenant name
    """
    if tenant_name:
        st.info(f"🏢 **Tenant:** {tenant_name}", icon="ℹ️")
