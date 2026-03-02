"""
Views package - tab implementations.
"""

from .admin import render_admin_tab
from .agents import render_agents_tab
from .auth import render_auth_tab
from .cypher import render_cypher_tab
from .dashboard import render_dashboard_tab
from .explore import render_explore_tab
from .jobs import render_jobs_tab
from .models import render_models_tab
from .tenants import render_tenants_tab
from .tools import render_tools_tab

__all__ = [
    "render_admin_tab",
    "render_agents_tab",
    "render_auth_tab",
    "render_cypher_tab",
    "render_dashboard_tab",
    "render_explore_tab",
    "render_jobs_tab",
    "render_models_tab",
    "render_tenants_tab",
    "render_tools_tab",
]
