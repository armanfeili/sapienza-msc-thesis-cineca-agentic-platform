"""
Tests for Central Tool Registry with Schema Validation (C.1)

Validates:
1. Registry loads all tools from manifest.json
2. All tool names are unique
3. All input_schemas are valid JSON Schema structures
4. Tool lookup and validation functions work correctly
"""

import pytest
from typing import Any


class TestToolRegistryLoading:
    """Test that the registry loads tools correctly."""
    
    def test_registry_loads_tools(self):
        """Registry should load tools from manifest."""
        from src.mcp.tool_registry import get_registry
        
        registry = get_registry(force_reload=True)
        tools = registry.get_tools()
        
        assert len(tools) > 0, "Registry should have tools"
        assert isinstance(tools, dict), "Tools should be a dict"
    
    def test_registry_has_expected_tools(self):
        """Registry should contain known tools from manifest."""
        from src.mcp.tool_registry import get_registry
        
        registry = get_registry()
        tool_names = registry.list_tool_names()
        
        # Check for some expected tools
        expected_tools = [
            "graph.query",
            "graph.secure_query",
            "graph.generate_cypher",
            "system.health",
            "security.audit",
        ]
        
        for expected in expected_tools:
            assert expected in tool_names, f"Expected tool '{expected}' not found"
    
    def test_registry_loads_categories(self):
        """Registry should load categories from manifest."""
        from src.mcp.tool_registry import get_registry
        
        registry = get_registry()
        categories = registry.get_categories()
        
        assert len(categories) > 0, "Should have categories"
        assert "graph" in categories, "Should have 'graph' category"
        assert "security" in categories, "Should have 'security' category"


class TestToolUniqueNames:
    """Test that all tool names are unique."""
    
    def test_all_tool_names_unique(self):
        """All tool names in the registry must be unique."""
        from src.mcp.tool_registry import get_registry
        
        registry = get_registry()
        tool_names = registry.list_tool_names()
        
        # Check no duplicates
        assert len(tool_names) == len(set(tool_names)), "Duplicate tool names found"
    
    def test_all_tool_ids_unique(self):
        """All tool IDs must be unique."""
        from src.mcp.tool_registry import get_registry
        
        registry = get_registry()
        tools = registry.get_tools()
        
        ids = [spec.id for spec in tools.values()]
        assert len(ids) == len(set(ids)), "Duplicate tool IDs found"


class TestSchemaValidation:
    """Test JSON schema validation for tools."""
    
    def test_all_schemas_valid(self):
        """All tool input_schemas should be valid JSON Schema structures."""
        from src.mcp.tool_registry import get_registry
        
        registry = get_registry(force_reload=True)
        result = registry.validate(strict=False)
        
        # Filter for schema-related errors
        schema_errors = [e for e in result.errors if "schema" in e.error_type.lower()]
        
        assert len(schema_errors) == 0, f"Schema validation errors: {schema_errors}"
    
    def test_validate_all_tools_no_errors(self):
        """validate_all_tools should return no errors."""
        from src.mcp.tool_registry import validate_all_tools
        
        errors = validate_all_tools(strict=False)
        
        # Should have no errors (warnings are OK)
        assert len(errors) == 0, f"Validation errors: {errors}"
    
    def test_valid_schema_structure(self):
        """Test validate_json_schema_structure with valid schema."""
        from src.mcp.tool_registry import validate_json_schema_structure
        
        valid_schema = {
            "type": "object",
            "required": ["action"],
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["run", "validate"]
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1
                }
            },
            "additionalProperties": False
        }
        
        errors = validate_json_schema_structure(valid_schema)
        assert len(errors) == 0, f"Valid schema had errors: {errors}"
    
    def test_invalid_schema_type(self):
        """Test validate_json_schema_structure catches invalid type."""
        from src.mcp.tool_registry import validate_json_schema_structure
        
        invalid_schema = {
            "type": "invalid_type"
        }
        
        errors = validate_json_schema_structure(invalid_schema)
        assert len(errors) > 0, "Should catch invalid type"
        assert any("invalid type" in e for e in errors)
    
    def test_invalid_schema_regex(self):
        """Test validate_json_schema_structure catches invalid regex pattern."""
        from src.mcp.tool_registry import validate_json_schema_structure
        
        invalid_schema = {
            "type": "string",
            "pattern": "[invalid(regex"  # Unclosed bracket
        }
        
        errors = validate_json_schema_structure(invalid_schema)
        assert len(errors) > 0, "Should catch invalid regex"
        assert any("pattern" in e.lower() or "regex" in e.lower() for e in errors)


class TestToolLookup:
    """Test tool lookup functions."""
    
    def test_get_tool_by_name(self):
        """get_tool should return tool spec by name."""
        from src.mcp.tool_registry import get_tool
        
        spec = get_tool("graph.query")
        
        assert spec is not None, "Should find graph.query"
        assert spec.name == "graph.query"
        assert spec.module == "src.mcp.tools.graph.query"
        assert spec.input_schema is not None
    
    def test_get_tool_unknown(self):
        """get_tool should return None for unknown tool."""
        from src.mcp.tool_registry import get_tool
        
        spec = get_tool("unknown.nonexistent.tool")
        
        assert spec is None, "Should return None for unknown tool"
    
    def test_list_tool_names(self):
        """list_tool_names should return all tool names."""
        from src.mcp.tool_registry import list_tool_names
        
        names = list_tool_names()
        
        assert isinstance(names, list)
        assert len(names) > 0
        assert all(isinstance(n, str) for n in names)
    
    def test_list_tools_by_capability(self):
        """Should filter tools by capability."""
        from src.mcp.tool_registry import get_registry
        
        registry = get_registry()
        db_tools = registry.list_tools_by_capability("reads_db")
        
        assert len(db_tools) > 0, "Should have tools with reads_db capability"
        for tool in db_tools:
            assert "reads_db" in tool.capabilities
    
    def test_list_tools_by_scope(self):
        """Should filter tools by scope."""
        from src.mcp.tool_registry import get_registry
        
        registry = get_registry()
        admin_tools = registry.list_tools_by_scope("admin:all")
        
        assert len(admin_tools) > 0, "Should have tools with admin:all scope"
        for tool in admin_tools:
            assert "admin:all" in tool.scopes


class TestToolInputValidation:
    """Test payload validation against tool schemas."""
    
    def test_validate_valid_payload(self):
        """Valid payload should pass validation."""
        from src.mcp.tool_registry import validate_tool_input
        
        valid_payload = {
            "action": "run",
            "cypher": "MATCH (n) RETURN n LIMIT 10",
            "read_only": True
        }
        
        is_valid, error = validate_tool_input("graph.query", valid_payload)
        
        assert is_valid, f"Valid payload should pass: {error}"
        assert error is None
    
    def test_validate_missing_required_field(self):
        """Missing required field should fail validation."""
        from src.mcp.tool_registry import validate_tool_input, get_tool
        
        # Skip if jsonschema not available
        try:
            import jsonschema
        except ImportError:
            pytest.skip("jsonschema not installed")
        
        # graph.query requires 'cypher'
        spec = get_tool("graph.query")
        if spec and spec.input_schema:
            required = spec.input_schema.get("required", [])
            if "cypher" in required:
                invalid_payload = {"action": "run"}
                is_valid, error = validate_tool_input("graph.query", invalid_payload)
                
                assert not is_valid, "Missing required field should fail"
                assert error is not None
    
    def test_validate_unknown_tool(self):
        """Unknown tool should fail validation."""
        from src.mcp.tool_registry import validate_tool_input
        
        is_valid, error = validate_tool_input("unknown.tool", {"foo": "bar"})
        
        assert not is_valid
        assert "Unknown tool" in error


class TestRegistryDescribe:
    """Test registry describe function."""
    
    def test_describe_returns_summary(self):
        """describe should return registry summary."""
        from src.mcp.tool_registry import get_registry
        
        registry = get_registry()
        summary = registry.describe()
        
        assert "tool_count" in summary
        assert "categories" in summary
        assert "tool_names" in summary
        assert "validated" in summary
        
        assert summary["tool_count"] > 0
        assert isinstance(summary["tool_names"], list)


class TestToolSpecDataclass:
    """Test ToolSpec dataclass."""
    
    def test_tool_spec_from_dict(self):
        """ToolSpec.from_dict should parse manifest data."""
        from src.mcp.tool_registry import ToolSpec
        
        data = {
            "id": "test.tool@1",
            "name": "test.tool",
            "module": "src.mcp.tools.test.tool",
            "description": "A test tool",
            "capabilities": ["test_cap"],
            "scopes": ["tools:basic"],
            "namespace": False,
            "long_running": True,
            "input_schema": {
                "type": "object",
                "properties": {}
            }
        }
        
        spec = ToolSpec.from_dict(data)
        
        assert spec.id == "test.tool@1"
        assert spec.name == "test.tool"
        assert spec.module == "src.mcp.tools.test.tool"
        assert spec.description == "A test tool"
        assert "test_cap" in spec.capabilities
        assert spec.long_running is True
        assert spec.input_schema is not None


class TestValidationResult:
    """Test ValidationResult dataclass."""
    
    def test_add_error(self):
        """add_error should add error and set valid=False."""
        from src.mcp.tool_registry import ValidationResult
        
        result = ValidationResult(valid=True)
        result.add_error("test.tool", "test_error", "Something went wrong")
        
        assert not result.valid
        assert len(result.errors) == 1
        assert result.errors[0].tool_name == "test.tool"
    
    def test_add_warning(self):
        """add_warning should not change valid status."""
        from src.mcp.tool_registry import ValidationResult
        
        result = ValidationResult(valid=True)
        result.add_warning("test.tool", "test_warning", "Something might be wrong")
        
        assert result.valid  # Still valid
        assert len(result.warnings) == 1


class TestIntegrationWithManifest:
    """Integration tests with actual manifest.json."""
    
    def test_manifest_tool_count_matches(self):
        """Registry tool count should match manifest."""
        from src.mcp.tool_registry import get_registry
        from src.mcp import get_manifest
        
        registry = get_registry()
        manifest = get_manifest()
        
        manifest_tools = manifest.get("tools", [])
        registry_tools = registry.list_tool_names()
        
        assert len(registry_tools) == len(manifest_tools), \
            f"Registry has {len(registry_tools)} tools, manifest has {len(manifest_tools)}"
    
    def test_all_manifest_tools_have_valid_schemas(self):
        """Every tool in manifest with a schema should have valid schema."""
        from src.mcp.tool_registry import get_registry
        
        registry = get_registry(force_reload=True)
        result = registry.validate(strict=False)
        
        # No validation errors
        assert result.valid, f"Validation failed: {[str(e) for e in result.errors]}"
    
    def test_graph_tools_have_read_capability(self):
        """Graph query tools should have reads_db capability."""
        from src.mcp.tool_registry import get_tool
        
        query_tool = get_tool("graph.query")
        
        assert query_tool is not None
        assert "reads_db" in query_tool.capabilities or "writes_db" in query_tool.capabilities
    
    def test_security_tools_have_admin_scope(self):
        """Security audit tool should require admin scope."""
        from src.mcp.tool_registry import get_tool
        
        audit_tool = get_tool("security.audit")
        
        assert audit_tool is not None
        assert "admin:all" in audit_tool.scopes
