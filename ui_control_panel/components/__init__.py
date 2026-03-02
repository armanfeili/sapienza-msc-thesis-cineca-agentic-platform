"""
Reusable UI components.
"""

from .confirm_modal import confirm_action
from .global_banner import render_api_health_banner, render_tenant_banner
from .health_cards import render_health_card
from .json_drawer import render_json_drawer
from .log_pane import render_log_pane
from .pagination import (
    get_page_slice,
    render_compact_pagination,
    render_pagination,
)
from .scope_checker import (
    check_admin_access,
    check_tool_access,
    has_all_scopes,
    has_any_scope,
    has_scope,
    render_scope_chips,
    render_scope_gate,
)
from .table import render_table
from .tenant_selector import render_tenant_chip, render_tenant_selector
from .timeline import render_timeline
from .token_badges import render_identity_selector, render_token_badges
from .tool_card import render_tool_card

__all__ = [
    "check_admin_access",
    "check_tool_access",
    "confirm_action",
    "get_page_slice",
    "has_all_scopes",
    "has_any_scope",
    "has_scope",
    "render_api_health_banner",
    "render_compact_pagination",
    "render_health_card",
    "render_identity_selector",
    "render_json_drawer",
    "render_log_pane",
    "render_pagination",
    "render_scope_chips",
    "render_scope_gate",
    "render_table",
    "render_tenant_banner",
    "render_tenant_chip",
    "render_tenant_selector",
    "render_timeline",
    "render_token_badges",
    "render_tool_card",
]
