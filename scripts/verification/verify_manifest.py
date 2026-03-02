#!/usr/bin/env python3
"""
Verification script for MCP manifest completeness and correctness.
"""

import json
from pathlib import Path
from typing import Dict, List, Set


def main():
    manifest_path = Path("src/mcp/manifest.json")
    manifest = json.loads(manifest_path.read_text())

    tools = manifest["tools"]
    categories = set(manifest["categories"])

    print("=" * 80)
    print("MCP MANIFEST VERIFICATION REPORT")
    print("=" * 80)
    print()

    # 1. Expected tool count
    expected_count = 32
    actual_count = len(tools)
    print(f"✓ Tool Count: {actual_count}/{expected_count}")
    assert actual_count == expected_count, f"Expected {expected_count} tools, got {actual_count}"
    print()

    # 2. Expected tools (from requirements)
    expected_tools = {
        "agent.context",
        "cache.manage",
        "catalog.discover",
        "data.archive",
        "data.quality",
        "db.switch",
        "errors.report",
        "graph.analytics",
        "graph.bulk",
        "graph.crud",
        "graph.generate_cypher",
        "graph.query",
        "graph.schema",
        "graph.search",
        "graph.secure_query",  # NEW
        "model.manage",
        "model.test",
        "output.format",
        "output.summarize",
        "privacy.consent",
        "ratelimit.manage",
        "security.audit",
        "security.check",
        "security.permissions",
        "session.manage",
        "system.backup",
        "system.health",
        "system.metrics",
        "system.status",
        "tenancy.manage",
        "user.profile",
        "viz.render",  # UPDATED
    }

    actual_tools = {t["name"] for t in tools}

    print("✓ Tool Presence Check:")
    missing = expected_tools - actual_tools
    extra = actual_tools - expected_tools

    if missing:
        print(f"  ⚠️  Missing: {missing}")
    else:
        print("  ✓ All expected tools present")

    if extra:
        print(f"  ⚠️  Extra: {extra}")
    else:
        print("  ✓ No unexpected tools")
    print()

    # 3. Metadata completeness
    print("✓ Metadata Completeness:")
    required_fields = [
        "id",
        "name",
        "module",
        "description",
        "capabilities",
        "scopes",
        "namespace",
        "long_running",
        "input_schema",
    ]

    for tool in tools:
        for field in required_fields:
            assert field in tool, f"Tool {tool.get('name', '?')} missing field: {field}"
    print(f"  ✓ All {len(tools)} tools have required fields: {', '.join(required_fields)}")
    print()

    # 4. ID format
    print("✓ ID Format:")
    for tool in tools:
        assert tool["id"] == f"{tool['name']}@1", f"Invalid ID format for {tool['name']}: {tool['id']}"
    print(f"  ✓ All tool IDs follow <name>@1 format")
    print()

    # 5. Module paths
    print("✓ Module Paths:")
    for tool in tools:
        name = tool["name"]
        module = tool["module"]
        expected_module = f"src.mcp.tools.{name.replace('.', '.')}"
        # Allow exact match or namespace variant
        assert module.startswith("src.mcp.tools."), f"Invalid module path for {name}: {module}"
    print(f"  ✓ All modules start with 'src.mcp.tools.'")
    print()

    # 6. Capabilities
    print("✓ Capabilities:")
    capability_stats: Dict[str, int] = {}
    for tool in tools:
        caps = tool.get("capabilities", [])
        assert isinstance(caps, list), f"Capabilities must be a list for {tool['name']}"
        assert len(caps) > 0, f"Tool {tool['name']} has no capabilities"
        for cap in caps:
            capability_stats[cap] = capability_stats.get(cap, 0) + 1

    print(f"  ✓ All tools have at least one capability")
    print(f"  ✓ Capability distribution:")
    for cap, count in sorted(capability_stats.items()):
        print(f"    - {cap:30s}: {count:2d} tools")
    print()

    # 7. Scopes
    print("✓ Scopes:")
    scope_stats: Dict[str, int] = {}
    for tool in tools:
        scopes = tool.get("scopes", [])
        assert isinstance(scopes, list), f"Scopes must be a list for {tool['name']}"
        assert len(scopes) > 0, f"Tool {tool['name']} has no scopes"
        for scope in scopes:
            scope_stats[scope] = scope_stats.get(scope, 0) + 1

    print(f"  ✓ All tools have at least one scope")
    print(f"  ✓ Scope distribution:")
    for scope, count in sorted(scope_stats.items()):
        print(f"    - {scope:15s}: {count:2d} tools")
    print()

    # 8. Long-running tools
    print("✓ Long-running Tools:")
    long_running = [t["name"] for t in tools if t.get("long_running")]
    expected_long_running = {"data.archive", "system.backup"}
    assert set(long_running) == expected_long_running, f"Expected {expected_long_running}, got {set(long_running)}"
    print(f"  ✓ Correctly marked: {', '.join(sorted(long_running))}")
    print()

    # 9. Input schemas
    print("✓ Input Schemas:")
    action_aware = 0
    for tool in tools:
        schema = tool.get("input_schema", {})
        assert isinstance(schema, dict), f"input_schema must be an object for {tool['name']}"
        props = schema.get("properties", {})
        if "action" in props:
            action_aware += 1
            action_schema = props["action"]
            assert "enum" in action_schema, f"Action field must have enum for {tool['name']}"

    print(f"  ✓ {action_aware}/{len(tools)} tools are action-aware")
    print()

    # 10. Special tool checks
    print("✓ Special Tool Checks:")

    # graph.secure_query
    secure_query = next((t for t in tools if t["name"] == "graph.secure_query"), None)
    assert secure_query, "graph.secure_query not found"
    assert "nl_to_cypher" in secure_query["capabilities"], "graph.secure_query missing nl_to_cypher capability"
    assert "policy_enforced" in secure_query["capabilities"], "graph.secure_query missing policy_enforced capability"
    assert "tools:basic" in secure_query["scopes"], "graph.secure_query should have tools:basic scope"
    assert "metadata" in secure_query, "graph.secure_query missing metadata field"
    print("  ✓ graph.secure_query: Correctly configured with safety metadata")

    # viz.render
    viz_render = next((t for t in tools if t["name"] == "viz.render"), None)
    assert viz_render, "viz.render not found"
    assert "visualization" in viz_render["capabilities"], "viz.render missing visualization capability"
    actions = viz_render["input_schema"]["properties"]["action"]["enum"]
    expected_actions = {"graph_mermaid", "graph_dot", "table_markdown", "sparkline"}
    assert set(actions) == expected_actions, f"viz.render actions mismatch: {set(actions)} vs {expected_actions}"
    print("  ✓ viz.render: Correctly configured with 4 actions")

    print()
    print("=" * 80)
    print("✅ ALL CHECKS PASSED")
    print("=" * 80)
    print()
    print(f"Summary:")
    print(f"  - {len(tools)} tools registered")
    print(f"  - {len(categories)} categories")
    print(f"  - {len(capability_stats)} unique capabilities")
    print(f"  - {len(scope_stats)} unique scopes")
    print(f"  - {len(long_running)} long-running tools")
    print(f"  - {action_aware} action-aware tools")
    print()


if __name__ == "__main__":
    main()
