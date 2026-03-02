"""
MCP Tool Policy - Tool selection, ranking, and allowlist enforcement.

This module provides policy-driven tool selection for agent sessions, including:
- Role-based tool allowlists (what tools can an agent use?)
- Tool ranking (which tools to prefer for a given task?)
- Fallback mechanisms (what to do when tools are blocked?)
- Deterministic tool selection for reproducible agent behavior

Integration Points
------------------
- src.mcp.policies.yaml: Role → tool allowlist mapping
- src.security.permissions: Permission checks for tool invocation
- src.mcp.runtime: Permission enforcement before tool execution
- src.schemas.agents: CreateSessionRequest.tools allowlist

Usage Example
-------------
    from src.mcp.tool_policy import filter_tools, rank_tools, get_fallback_tool

    # Filter tools by agent role
    allowed = filter_tools(
        available_tools=["graph.query", "graph.crud", "security.audit"],
        agent_role="analyst",
        session_tools=None  # or explicit allowlist
    )
    # => ["graph.query"]  # analyst role only gets read-only tools

    # Rank tools by task suitability
    ranked = rank_tools(
        tools=allowed,
        task_description="Find all users in the graph",
        preferences={"graph.query": 1.0, "graph.search": 0.8}
    )
    # => [("graph.query", 1.0), ("graph.search", 0.8)]

    # Get fallback tool if primary blocked
    fallback = get_fallback_tool(
        blocked_tool="graph.crud",
        task_description="Create a new user node",
        allowed_tools=allowed
    )
    # => "graph.query" (read-only fallback)

Policy Structure (src/mcp/policies.yaml)
----------------------------------------
    tool_policies:
      roles:
        analyst:
          allow:
            - "graph.query"
            - "graph.search"
            - "graph.analytics"
            - "output.*"
          deny:
            - "graph.crud"
            - "security.*"

        operator:
          allow:
            - "graph.*"
            - "cache.*"
            - "session.*"
          deny:
            - "security.audit"
            - "tenancy.*"

        admin:
          allow: ["*"]  # all tools
          deny: []

      rankings:
        # Task keywords → tool weights
        "query|search|find|lookup":
          - ["graph.query", 1.0]
          - ["graph.search", 0.9]
          - ["graph.analytics", 0.7]

        "create|insert|add|new":
          - ["graph.crud", 1.0]
          - ["graph.bulk", 0.8]

        "update|modify|change|edit":
          - ["graph.crud", 1.0]
          - ["graph.query", 0.5]

      fallbacks:
        "graph.crud": "graph.query"  # if write blocked, use read
        "graph.bulk": "graph.crud"   # if bulk blocked, use single CRUD
        "security.audit": null       # no fallback (deny operation)
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Iterable
from contextlib import suppress
from typing import Any

# ── Logging ───────────────────────────────────────────────────────────────────
with suppress(Exception):
    from src.logging_setup import get_logger  # type: ignore

    logger = get_logger(__name__)
if "logger" not in globals():
    import logging

    logger = logging.getLogger(__name__)

# ── Policy Loading ────────────────────────────────────────────────────────────
with suppress(Exception):
    from src.mcp import get_policies as _get_policies  # type: ignore

if "_get_policies" not in globals():

    def _get_policies(**_: Any) -> dict[str, Any]:  # type: ignore
        return {}


# ── MCP Manifest Loading ──────────────────────────────────────────────────────
with suppress(Exception):
    from src.mcp import get_manifest, list_tool_names  # type: ignore

if "list_tool_names" not in globals():

    def get_manifest(**_: Any) -> dict[str, Any]:  # type: ignore
        return {"tools": []}

    def list_tool_names(**_: Any) -> list[str]:  # type: ignore
        return []


# ══════════════════════════════════════════════════════════════════════════════
# Policy Helpers
# ══════════════════════════════════════════════════════════════════════════════


def _match_pattern(pattern: str, tool_name: str) -> bool:
    """
    Check if tool name matches a wildcard pattern.

    Supports:
    - Exact match: "graph.query"
    - Prefix wildcard: "graph.*"
    - Suffix wildcard: "*.query"
    - Full wildcard: "*"

    Args:
        pattern: Pattern string (e.g., "graph.*", "*", "graph.query")
        tool_name: Tool name to match (e.g., "graph.query")

    Returns:
        True if tool name matches pattern

    Examples:
        >>> _match_pattern("graph.*", "graph.query")
        True
        >>> _match_pattern("graph.*", "security.audit")
        False
        >>> _match_pattern("*", "anything")
        True
    """
    if pattern == "*":
        return True
    if "*" in pattern:
        return fnmatch.fnmatch(tool_name, pattern)
    return pattern == tool_name


def _load_role_policy(agent_role: str) -> dict[str, Any]:
    """
    Load tool policy for a given agent role.

    Args:
        agent_role: Role name (e.g., "analyst", "operator", "admin")

    Returns:
        Policy dict with keys:
            - allow: List[str] - allowed tool patterns
            - deny: List[str] - denied tool patterns

    Examples:
        >>> _load_role_policy("analyst")
        {"allow": ["graph.query", "graph.search"], "deny": ["graph.crud"]}
    """
    policies = _get_policies()
    tool_policies = policies.get("tool_policies", {})
    roles = tool_policies.get("roles", {})

    # Default: no restrictions (allow all if role not found)
    default_policy = {"allow": ["*"], "deny": []}

    role_policy = roles.get(agent_role, default_policy)
    if not isinstance(role_policy, dict):
        return default_policy

    return {
        "allow": role_policy.get("allow", ["*"]),
        "deny": role_policy.get("deny", []),
    }


def _load_tool_rankings() -> dict[str, list[tuple[str, float]]]:
    """
    Load tool rankings from policy configuration.

    Returns:
        Dict mapping task keywords (regex patterns) to ranked tool lists.
        Each tool list is a list of (tool_name, weight) tuples.

    Examples:
        >>> _load_tool_rankings()
        {
            "query|search|find": [("graph.query", 1.0), ("graph.search", 0.9)],
            "create|insert|add": [("graph.crud", 1.0), ("graph.bulk", 0.8)]
        }
    """
    policies = _get_policies()
    tool_policies = policies.get("tool_policies", {})
    rankings_raw = tool_policies.get("rankings", {})

    # Normalize rankings structure
    rankings: dict[str, list[tuple[str, float]]] = {}
    for pattern, tools in rankings_raw.items():
        if not isinstance(tools, list):
            continue

        tool_list: list[tuple[str, float]] = []
        for item in tools:
            if isinstance(item, list) and len(item) == 2:
                tool_name, weight = item
                tool_list.append((str(tool_name), float(weight)))

        if tool_list:
            rankings[str(pattern)] = tool_list

    return rankings


def _load_fallback_map() -> dict[str, str | None]:
    """
    Load fallback tool mappings from policy configuration.

    Returns:
        Dict mapping blocked tool name to fallback tool name.
        If value is None, no fallback exists (operation should fail).

    Examples:
        >>> _load_fallback_map()
        {
            "graph.crud": "graph.query",
            "graph.bulk": "graph.crud",
            "security.audit": None
        }
    """
    policies = _get_policies()
    tool_policies = policies.get("tool_policies", {})
    fallbacks = tool_policies.get("fallbacks", {})

    # Normalize to str -> Optional[str]
    result: dict[str, str | None] = {}
    for k, v in fallbacks.items():
        result[str(k)] = str(v) if v is not None else None

    return result


# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════


def filter_tools(
    available_tools: Iterable[str],
    agent_role: str | None = None,
    session_tools: list[str] | None = None,
) -> list[str]:
    """
    Filter tools based on agent role policy and explicit session allowlist.

    Filtering logic (AND combination):
    1. Agent role policy (allow/deny patterns from src/mcp/policies.yaml)
    2. Session allowlist (explicit tool names from CreateSessionRequest.tools)

    Precedence:
    - Deny rules override allow rules
    - Session allowlist overrides role policy (if provided)

    Args:
        available_tools: All tools available in the MCP manifest
        agent_role: Agent role name (e.g., "analyst", "operator", "admin")
        session_tools: Explicit allowlist of tool names for this session

    Returns:
        List of allowed tool names (subset of available_tools)

    Examples:
        # Role-based filtering
        >>> filter_tools(
        ...     available_tools=["graph.query", "graph.crud", "security.audit"],
        ...     agent_role="analyst",
        ...     session_tools=None
        ... )
        ["graph.query"]  # analyst role only gets read-only tools

        # Session allowlist overrides role policy
        >>> filter_tools(
        ...     available_tools=["graph.query", "graph.crud"],
        ...     agent_role="analyst",
        ...     session_tools=["graph.crud"]
        ... )
        ["graph.crud"]  # explicit session allowlist takes precedence

        # No role/session → allow all
        >>> filter_tools(
        ...     available_tools=["graph.query", "graph.crud"],
        ...     agent_role=None,
        ...     session_tools=None
        ... )
        ["graph.query", "graph.crud"]
    """
    available = list(available_tools)

    # If session has explicit allowlist, use that (highest precedence)
    if session_tools is not None:
        session_set = set(session_tools)
        filtered = [t for t in available if t in session_set]
        logger.debug(
            "Filtered tools by session allowlist",
            extra={
                "available": len(available),
                "session_tools": len(session_tools),
                "result": len(filtered),
            },
        )
        return filtered

    # If no agent role, allow all tools
    if not agent_role:
        logger.debug("No agent role specified, allowing all tools", extra={"count": len(available)})
        return available

    # Load role policy
    policy = _load_role_policy(agent_role)
    allow_patterns = policy.get("allow", ["*"])
    deny_patterns = policy.get("deny", [])

    filtered: list[str] = []
    for tool in available:
        # Check deny patterns first (deny overrides allow)
        denied = any(_match_pattern(pattern, tool) for pattern in deny_patterns)
        if denied:
            continue

        # Check allow patterns
        allowed = any(_match_pattern(pattern, tool) for pattern in allow_patterns)
        if allowed:
            filtered.append(tool)

    logger.debug(
        "Filtered tools by role policy",
        extra={
            "agent_role": agent_role,
            "available": len(available),
            "allow_patterns": allow_patterns,
            "deny_patterns": deny_patterns,
            "result": len(filtered),
        },
    )

    return filtered


def rank_tools(
    tools: Iterable[str],
    task_description: str | None = None,
    preferences: dict[str, float] | None = None,
) -> list[tuple[str, float]]:
    """
    Rank tools by suitability for a given task.

    Ranking algorithm:
    1. Match task description against policy ranking patterns (keyword regex)
    2. Apply explicit user preferences (higher weight = more preferred)
    3. Default weight = 0.5 for tools without explicit ranking
    4. Sort by weight descending (highest first)

    Args:
        tools: Tool names to rank
        task_description: Natural language description of task (for keyword matching)
        preferences: Explicit tool→weight mapping (overrides policy rankings)

    Returns:
        List of (tool_name, weight) tuples sorted by weight descending.
        Weight range: [0.0, 1.0] where 1.0 = highest priority

    Examples:
        # Task-based ranking
        >>> rank_tools(
        ...     tools=["graph.query", "graph.crud", "graph.search"],
        ...     task_description="Find all users in the graph",
        ...     preferences=None
        ... )
        [("graph.query", 1.0), ("graph.search", 0.9), ("graph.crud", 0.5)]

        # Explicit preferences override policy
        >>> rank_tools(
        ...     tools=["graph.query", "graph.crud"],
        ...     task_description=None,
        ...     preferences={"graph.crud": 1.0, "graph.query": 0.3}
        ... )
        [("graph.crud", 1.0), ("graph.query", 0.3)]
    """
    tool_list = list(tools)
    if not tool_list:
        return []

    # Load policy rankings
    policy_rankings = _load_tool_rankings()

    # Initialize weights
    weights: dict[str, float] = dict.fromkeys(tool_list, 0.5)  # default weight

    # Apply task-based rankings from policy
    if task_description:
        task_lower = task_description.lower()
        for pattern, ranked_tools in policy_rankings.items():
            # Check if task description matches pattern (regex)
            if re.search(pattern, task_lower, re.IGNORECASE):
                for tool_name, weight in ranked_tools:
                    if tool_name in weights:
                        # Take max weight if tool matches multiple patterns
                        weights[tool_name] = max(weights[tool_name], weight)

    # Apply explicit preferences (overrides policy)
    if preferences:
        for tool, weight in preferences.items():
            if tool in weights:
                weights[tool] = float(weight)

    # Sort by weight descending
    ranked = sorted(weights.items(), key=lambda x: x[1], reverse=True)

    logger.debug(
        "Ranked tools",
        extra={
            "tools": len(tool_list),
            "task": task_description[:50] if task_description else None,
            "top_3": ranked[:3],
        },
    )

    return ranked


def get_fallback_tool(
    blocked_tool: str,
    task_description: str | None = None,
    allowed_tools: list[str] | None = None,
) -> str | None:
    """
    Get fallback tool when primary tool is blocked by policy.

    Fallback selection algorithm:
    1. Check explicit fallback mapping in policy (blocked_tool → fallback)
    2. If no explicit mapping, try to find similar tool from allowed_tools
    3. Use task description to rank allowed tools and pick highest ranked
    4. Return None if no fallback exists (operation should fail gracefully)

    Args:
        blocked_tool: Tool name that was blocked by policy
        task_description: Task description (for ranking fallback candidates)
        allowed_tools: List of tools allowed for this session/role

    Returns:
        Fallback tool name, or None if no fallback exists

    Examples:
        # Explicit fallback mapping
        >>> get_fallback_tool(
        ...     blocked_tool="graph.crud",
        ...     task_description="Create a new user",
        ...     allowed_tools=["graph.query", "graph.search"]
        ... )
        "graph.query"  # policy maps graph.crud → graph.query

        # No fallback configured
        >>> get_fallback_tool(
        ...     blocked_tool="security.audit",
        ...     task_description="Audit user actions",
        ...     allowed_tools=["graph.query"]
        ... )
        None  # policy explicitly sets security.audit fallback to None
    """
    # Load fallback mappings
    fallback_map = _load_fallback_map()

    # Check explicit fallback mapping
    if blocked_tool in fallback_map:
        fallback = fallback_map[blocked_tool]
        if fallback:
            # Verify fallback is in allowed tools
            if allowed_tools is None or fallback in allowed_tools:
                logger.info(
                    "Using configured fallback",
                    extra={"blocked": blocked_tool, "fallback": fallback},
                )
                return fallback
            else:
                logger.warning(
                    "Configured fallback not allowed",
                    extra={"blocked": blocked_tool, "fallback": fallback, "allowed": allowed_tools},
                )
        else:
            # Explicitly no fallback (None value in policy)
            logger.info("No fallback configured", extra={"blocked": blocked_tool})
            return None

    # No explicit mapping → try to find similar tool
    if not allowed_tools:
        logger.debug("No allowed tools for fallback", extra={"blocked": blocked_tool})
        return None

    # Rank allowed tools by task suitability
    ranked = rank_tools(allowed_tools, task_description=task_description)
    if not ranked:
        return None

    # Pick highest ranked tool (best match)
    fallback_tool, weight = ranked[0]
    logger.info(
        "Using ranked fallback",
        extra={
            "blocked": blocked_tool,
            "fallback": fallback_tool,
            "weight": weight,
            "candidates": len(ranked),
        },
    )

    return fallback_tool


def validate_tool_access(
    tool_name: str,
    agent_role: str | None = None,
    session_tools: list[str] | None = None,
) -> tuple[bool, str | None]:
    """
    Validate if a tool can be accessed given role and session constraints.

    This is a convenience function that combines filter_tools with a single tool check.

    Args:
        tool_name: Tool to validate
        agent_role: Agent role name
        session_tools: Session allowlist

    Returns:
        Tuple of (allowed: bool, reason: Optional[str])
        - (True, None) if tool is allowed
        - (False, "reason") if tool is blocked

    Examples:
        >>> validate_tool_access("graph.query", agent_role="analyst")
        (True, None)

        >>> validate_tool_access("graph.crud", agent_role="analyst")
        (False, "Tool denied by role policy: analyst")

        >>> validate_tool_access("graph.crud", session_tools=["graph.query"])
        (False, "Tool not in session allowlist")
    """
    # Get all available tools from manifest
    all_tools = list_tool_names()

    # Check if tool exists
    if tool_name not in all_tools:
        return False, f"Tool not found in manifest: {tool_name}"

    # Filter tools by policy
    allowed = filter_tools(
        available_tools=all_tools,
        agent_role=agent_role,
        session_tools=session_tools,
    )

    # Check if tool is in allowed list
    if tool_name in allowed:
        return True, None

    # Determine reason for denial
    if session_tools is not None and tool_name not in session_tools:
        return False, "Tool not in session allowlist"

    if agent_role:
        return False, f"Tool denied by role policy: {agent_role}"

    return False, "Tool access denied (unknown reason)"


# ══════════════════════════════════════════════════════════════════════════════
# Module Exports
# ══════════════════════════════════════════════════════════════════════════════

__all__ = [
    "filter_tools",
    "get_fallback_tool",
    "rank_tools",
    "validate_tool_access",
]
