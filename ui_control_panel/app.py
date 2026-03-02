"""
Cineca Agentic Platform - Streamlit UI
Main application entry point.
"""

import os

import streamlit as st
from components import (
    render_api_health_banner,
    render_identity_selector,
    render_tenant_chip,
    render_tenant_selector,
    render_token_badges,
)
from state import get_state, init_state, update_state
from views import (
    render_admin_tab,
    render_agents_tab,
    render_auth_tab,
    render_cypher_tab,
    render_dashboard_tab,
    render_explore_tab,
    render_jobs_tab,
    render_models_tab,
    render_tenants_tab,
    render_tools_tab,
)

from api import get_model_defaults, run_self_test

# Page configuration
st.set_page_config(
    page_title="Cineca Agentic Platform",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS with responsive design for small screens
st.markdown(
    """
<style>
    /* Base styles */
    .main-header {
        font-size: 2rem;
        font-weight: 700;
        color: #1f77b4;
        margin-bottom: 1rem;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        padding: 0 24px;
    }
    .metric-card {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #f0f2f6;
        border-left: 4px solid #1f77b4;
    }
    
    /* Responsive design for tablets and below (< 1024px) */
    @media (max-width: 1024px) {
        .main-header {
            font-size: 1.5rem;
        }
        .stTabs [data-baseweb="tab"] {
            padding: 0 16px;
            font-size: 0.9rem;
        }
    }
    
    /* Responsive design for mobile devices (< 768px) */
    @media (max-width: 768px) {
        .main-header {
            font-size: 1.25rem;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 4px;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
        }
        .stTabs [data-baseweb="tab"] {
            height: 40px;
            padding: 0 12px;
            font-size: 0.85rem;
            white-space: nowrap;
        }
        .metric-card {
            padding: 0.75rem;
        }
        /* Ensure minimum usable width */
        .main .block-container {
            min-width: 320px;
            padding-left: 1rem;
            padding-right: 1rem;
        }
    }
    
    /* Responsive design for very small devices (< 480px) */
    @media (max-width: 480px) {
        .main-header {
            font-size: 1.1rem;
        }
        .stTabs [data-baseweb="tab"] {
            height: 36px;
            padding: 0 8px;
            font-size: 0.8rem;
        }
        /* Stack columns vertically on very small screens */
        [data-testid="column"] {
            width: 100% !important;
            flex: 1 1 100% !important;
            min-width: 100% !important;
        }
    }
</style>
""",
    unsafe_allow_html=True,
)

# Initialize state
init_state()
state = get_state()

# Check and auto-renew tokens if needed (runs every 60 seconds)
# FIXED: Only runs if enough time has passed since last check (debounced)
from components.auto_renew import check_and_renew_tokens

# This function already has debouncing logic via should_check_renewal()
check_and_renew_tokens()

# Run API self-test on first load
# FIXED: Improved error handling and retry logic
if "api_health_checked" not in st.session_state:
    st.session_state.api_health_checked = True
    with st.spinner("🔄 Checking API connectivity..."):
        is_healthy, messages = run_self_test()
        st.session_state.api_healthy = is_healthy
        st.session_state.api_health_messages = messages

        # If unhealthy, also allow manual retry
        if not is_healthy:
            st.session_state.api_health_retry_available = True

# Load model defaults on startup and when tenant changes
# FIXED: Check for active token before attempting to load defaults
current_tenant = state.tenant.current
tenant_changed = st.session_state.get("last_tenant") != current_tenant

# Check if token just became available (was None before, now available)
token_just_available = False
if "had_token_before" not in st.session_state:
    st.session_state.had_token_before = False

from state import get_active_token

active_token = get_active_token()

# Clear old permission errors when token becomes valid
# Use a flag to prevent infinite loops - only clear once per session
if active_token and not active_token.is_expired and "model_defaults_error" in st.session_state:
    old_error = st.session_state.model_defaults_error
    # Only clear if it was a permission error (403) - token might be fresh now
    # And only if we haven't already tried clearing it
    if ("403" in str(old_error) or "Forbidden" in str(old_error)) and not st.session_state.get(
        "_403_error_cleared_on_startup", False
    ):
        del st.session_state.model_defaults_error
        st.session_state._403_error_cleared_on_startup = True
        # Force retry by marking as not loaded
        state.defaults_loaded = False
        update_state(defaults_loaded=False)

if active_token and not st.session_state.had_token_before:
    token_just_available = True
    st.session_state.had_token_before = True

if not state.defaults_loaded or tenant_changed or token_just_available:
    if active_token:
        # Only show spinner if defaults not loaded yet
        if not state.defaults_loaded:
            with st.spinner("🔄 Loading model defaults..."):
                success, defaults_data, error = get_model_defaults()
        else:
            success, defaults_data, error = get_model_defaults()

        if success and defaults_data:
            state.model_defaults = defaults_data
            state.defaults_loaded = True
            update_state(model_defaults=defaults_data, defaults_loaded=True)
            # Clear any previous errors
            if "model_defaults_error" in st.session_state:
                del st.session_state.model_defaults_error
        elif error:
            # Check if it's a 403 Forbidden (permission issue)
            if "403" in str(error) or "Forbidden" in str(error):
                # Store the error for showing in the agents tab
                st.session_state.model_defaults_error = error
                # Mark as loaded to prevent retries (user needs to log in with proper token)
                state.defaults_loaded = True
                update_state(defaults_loaded=True)
            # Only show error if it's not a 404 (404 means no defaults set yet, which is okay)
            elif "404" not in str(error) and "not found" not in str(error).lower():
                # Store error in session state to show in relevant tabs
                st.session_state.model_defaults_error = error
                # Don't mark as loaded if there was an error
                if not state.defaults_loaded:
                    state.defaults_loaded = True  # Mark as attempted to prevent infinite retries
                    update_state(defaults_loaded=True)
    else:
        # No active token - skip loading defaults silently
        # This will be retried once user logs in
        if not state.defaults_loaded:
            # Mark as attempted to prevent retries until token is available
            state.defaults_loaded = False  # Keep as False so it retries when token is available
            # Don't show error if no token is available - user needs to log in first
        st.session_state.had_token_before = False

    st.session_state.last_tenant = current_tenant

# Sidebar utilities
with st.sidebar:
    st.header("🛠️ Utilities")

    # Clear cache button
    st.subheader("🗑️ Cache Management")
    if st.button("🔄 Clear All Cache", use_container_width=True, help="Clear session state and cached data"):
        # Clear specific error caches
        keys_to_clear = [
            "model_defaults_error",
            "permission_error_403",
            "api_health_checked",
            "renewal_toast_shown",
            "renewal_error_toast_shown",
        ]
        for key in keys_to_clear:
            if key in st.session_state:
                del st.session_state[key]

        # Reset defaults_loaded to trigger reload
        state.defaults_loaded = False
        update_state(defaults_loaded=False)

        st.success("✅ Cache cleared! Refreshing...")
        st.rerun()

    st.caption("Clear stuck errors or cached permission issues")

    st.divider()

    # Token expiry warnings
    st.subheader("⏱️ Token Status")
    active_token = get_active_token()
    if active_token:
        seconds_left = active_token.seconds_until_expiry
        minutes_left = seconds_left // 60
        hours_left = minutes_left // 60

        if active_token.is_expired:
            st.error("❌ Token expired - please login again")
        elif active_token.needs_renewal:
            st.warning(f"⚠️ Token expires in {minutes_left} minutes")
            st.caption("Please renew your token in the Auth tab")
        elif hours_left > 1:
            st.success(f"✅ Token valid for {hours_left}h {minutes_left % 60}m")
        else:
            st.info(f"✅ Token valid for {minutes_left} minutes")
    else:
        st.info("ℹ️ No active token - login in Auth tab")

    st.divider()

    # System info
    st.subheader("ℹ️ System Info")
    st.caption(f"**Environment:** {os.getenv('ENVIRONMENT', 'production')}")
    st.caption(f"**API:** {os.getenv('API_BASE_URL', 'http://localhost:8000')}")
    if state.tenant.current:
        st.caption(f"**Tenant:** {state.tenant.current[:8]}...")
    else:
        st.caption("**Tenant:** None selected")

# Header
st.markdown('<h1 class="main-header">🤖 Cineca Agentic Platform</h1>', unsafe_allow_html=True)

# Show API health banner if issues detected
if not st.session_state.get("api_healthy", True):
    render_api_health_banner(False, st.session_state.get("api_health_messages", []))

# Top bar with identity, tokens, and tenant
# FIXED: Use static container key to prevent duplicate rendering
with st.container(key="main_top_bar_container"):
    row1_col1, row1_col2, row1_col3 = st.columns([2, 2, 1])

    with row1_col1:
        render_token_badges()

    with row1_col2:
        render_tenant_selector()

    with row1_col3:
        render_identity_selector()

        # Developer mode toggle
        if st.checkbox("🔧 Developer Mode", value=state.developer_mode, key="dev_mode"):
            state.developer_mode = True
            st.session_state.ui_state = state
        else:
            state.developer_mode = False
            st.session_state.ui_state = state

    # Show tenant chip if tenant is selected
    if state.tenant.current:
        render_tenant_chip()

st.markdown("---")

# Main tabs
tab_labels = [
    "🔐 Auth",
    "📊 Dashboard",
    "🔍 Explore",
    "🤖 Agents",
    "📋 Jobs",
    "🔧 Tools",
    "🧠 Models",
    "🔍 NL→Cypher",
    "🏢 Tenants",
    "⚙️ Admin",
]

tabs = st.tabs(tab_labels)

with tabs[0]:  # Auth
    try:
        render_auth_tab()
    except Exception as e:
        st.error(f"❌ Error rendering Auth tab: {e!s}")
        if state.developer_mode:
            st.exception(e)
        if st.button("🔄 Retry", key="retry_auth_tab"):
            st.rerun()

with tabs[1]:  # Dashboard
    try:
        render_dashboard_tab()
    except Exception as e:
        st.error(f"❌ Error rendering Dashboard tab: {e!s}")
        if state.developer_mode:
            st.exception(e)
        if st.button("🔄 Retry", key="retry_dashboard_tab"):
            st.rerun()

with tabs[2]:  # Explore
    try:
        render_explore_tab()
    except Exception as e:
        st.error(f"❌ Error rendering Explore tab: {e!s}")
        if state.developer_mode:
            st.exception(e)
        if st.button("🔄 Retry", key="retry_explore_tab"):
            st.rerun()

with tabs[3]:  # Agents
    try:
        render_agents_tab()
    except Exception as e:
        st.error(f"❌ Error rendering Agents tab: {e!s}")
        if state.developer_mode:
            st.exception(e)
        if st.button("🔄 Retry", key="retry_agents_tab"):
            st.rerun()

with tabs[4]:  # Jobs
    try:
        render_jobs_tab()
    except Exception as e:
        st.error(f"❌ Error rendering Jobs tab: {e!s}")
        if state.developer_mode:
            st.exception(e)
        if st.button("🔄 Retry", key="retry_jobs_tab"):
            st.rerun()

with tabs[5]:  # Tools
    try:
        render_tools_tab()
    except Exception as e:
        st.error(f"❌ Error rendering Tools tab: {e!s}")
        if state.developer_mode:
            st.exception(e)
        if st.button("🔄 Retry", key="retry_tools_tab"):
            st.rerun()

with tabs[6]:  # Models
    try:
        render_models_tab()
    except Exception as e:
        st.error(f"❌ Error rendering Models tab: {e!s}")
        if state.developer_mode:
            st.exception(e)
        if st.button("🔄 Retry", key="retry_models_tab"):
            st.rerun()

with tabs[7]:  # NL→Cypher
    try:
        render_cypher_tab()
    except Exception as e:
        st.error(f"❌ Error rendering NL→Cypher tab: {e!s}")
        if state.developer_mode:
            st.exception(e)
        if st.button("🔄 Retry", key="retry_cypher_tab"):
            st.rerun()

with tabs[8]:  # Tenants
    try:
        render_tenants_tab()
    except Exception as e:
        st.error(f"❌ Error rendering Tenants tab: {e!s}")
        if state.developer_mode:
            st.exception(e)
        if st.button("🔄 Retry", key="retry_tenants_tab"):
            st.rerun()

with tabs[9]:  # Admin
    try:
        render_admin_tab()
    except Exception as e:
        st.error(f"❌ Error rendering Admin tab: {e!s}")
        if state.developer_mode:
            st.exception(e)
        if st.button("🔄 Retry", key="retry_admin_tab"):
            st.rerun()


# Footer
st.markdown("---")
st.caption("Cineca Agentic Platform UI • Built with Streamlit")
