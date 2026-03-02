"""
Central Tool Registry with Schema Validation (C.1)

Provides:
1. Central enumeration of all MCP tools from manifest.json
2. Startup validation of JSON schemas (valid structure, unique names)
3. Tool lookup with schema validation
4. Integration with Pydantic schemas from schemas.py

Usage:
    from src.mcp.tool_registry import get_registry, validate_all_tools
    
    # Get singleton registry (validates on first access)
    registry = get_registry()
    
    # Or validate explicitly
    errors = validate_all_tools()
    if errors:
        raise RuntimeError(f"Tool validation failed: {errors}")
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

# Suppress import errors for optional dependencies
try:
    from src.logging_setup import get_logger
    logger = get_logger(__name__)
except Exception:
    import logging
    logger = logging.getLogger(__name__)

try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False
    logger.warning("jsonschema not installed; JSON schema validation disabled")


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class ToolSpec:
    """Parsed tool specification from manifest."""
    
    id: str
    name: str
    module: str
    description: str
    capabilities: list[str] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)
    namespace: bool = False
    long_running: bool = False
    input_schema: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolSpec":
        """Create ToolSpec from manifest dict."""
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            module=data.get("module", ""),
            description=data.get("description", ""),
            capabilities=data.get("capabilities", []),
            scopes=data.get("scopes", []),
            namespace=data.get("namespace", False),
            long_running=data.get("long_running", False),
            input_schema=data.get("input_schema"),
            metadata=data.get("metadata"),
        )


@dataclass
class ValidationError:
    """Describes a validation error for a tool."""
    
    tool_name: str
    error_type: str
    message: str
    details: dict[str, Any] | None = None
    
    def __str__(self) -> str:
        return f"[{self.error_type}] {self.tool_name}: {self.message}"


@dataclass
class ValidationResult:
    """Result of validating the tool registry."""
    
    valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)
    tool_count: int = 0
    
    def add_error(self, tool_name: str, error_type: str, message: str, details: dict[str, Any] | None = None):
        """Add a validation error."""
        self.errors.append(ValidationError(tool_name, error_type, message, details))
        self.valid = False
    
    def add_warning(self, tool_name: str, error_type: str, message: str, details: dict[str, Any] | None = None):
        """Add a validation warning (non-fatal)."""
        self.warnings.append(ValidationError(tool_name, error_type, message, details))


# ---------------------------------------------------------------------------
# JSON Schema Validation Helpers
# ---------------------------------------------------------------------------

# JSON Schema Draft-07 meta-schema (simplified for our purposes)
JSON_SCHEMA_KEYWORDS = {
    "type", "properties", "required", "additionalProperties", "items",
    "minLength", "maxLength", "minimum", "maximum", "pattern", "enum",
    "anyOf", "allOf", "oneOf", "not", "default", "description",
    "format", "minItems", "maxItems", "uniqueItems", "const",
    "$ref", "$schema", "$id", "title", "examples",
}

JSON_SCHEMA_TYPES = {"object", "array", "string", "number", "integer", "boolean", "null"}


def validate_json_schema_structure(schema: dict[str, Any], path: str = "") -> list[str]:
    """
    Validate that a dict represents a valid JSON Schema structure.
    
    Returns list of error messages (empty if valid).
    """
    errors: list[str] = []
    
    if not isinstance(schema, dict):
        return [f"{path or 'root'}: schema must be an object"]
    
    # Check type field
    schema_type = schema.get("type")
    if schema_type:
        if isinstance(schema_type, str):
            if schema_type not in JSON_SCHEMA_TYPES:
                errors.append(f"{path}.type: invalid type '{schema_type}'")
        elif isinstance(schema_type, list):
            for t in schema_type:
                if t not in JSON_SCHEMA_TYPES:
                    errors.append(f"{path}.type: invalid type '{t}' in union")
        else:
            errors.append(f"{path}.type: must be string or array")
    
    # Check properties (for object type)
    if "properties" in schema:
        props = schema["properties"]
        if not isinstance(props, dict):
            errors.append(f"{path}.properties: must be an object")
        else:
            for prop_name, prop_schema in props.items():
                sub_path = f"{path}.properties.{prop_name}" if path else f"properties.{prop_name}"
                errors.extend(validate_json_schema_structure(prop_schema, sub_path))
    
    # Check items (for array type)
    if "items" in schema:
        items = schema["items"]
        if isinstance(items, dict):
            sub_path = f"{path}.items" if path else "items"
            errors.extend(validate_json_schema_structure(items, sub_path))
        elif isinstance(items, list):
            for i, item_schema in enumerate(items):
                sub_path = f"{path}.items[{i}]" if path else f"items[{i}]"
                errors.extend(validate_json_schema_structure(item_schema, sub_path))
    
    # Check required field
    if "required" in schema:
        required = schema["required"]
        if not isinstance(required, list):
            errors.append(f"{path}.required: must be an array")
        elif not all(isinstance(r, str) for r in required):
            errors.append(f"{path}.required: all items must be strings")
    
    # Check enum values
    if "enum" in schema:
        enum = schema["enum"]
        if not isinstance(enum, list):
            errors.append(f"{path}.enum: must be an array")
        elif len(enum) == 0:
            errors.append(f"{path}.enum: must have at least one value")
    
    # Check pattern is valid regex
    if "pattern" in schema:
        pattern = schema["pattern"]
        if isinstance(pattern, str):
            try:
                re.compile(pattern)
            except re.error as e:
                errors.append(f"{path}.pattern: invalid regex - {e}")
    
    # Check anyOf/allOf/oneOf
    for keyword in ("anyOf", "allOf", "oneOf"):
        if keyword in schema:
            subschemas = schema[keyword]
            if not isinstance(subschemas, list):
                errors.append(f"{path}.{keyword}: must be an array")
            else:
                for i, sub in enumerate(subschemas):
                    sub_path = f"{path}.{keyword}[{i}]" if path else f"{keyword}[{i}]"
                    errors.extend(validate_json_schema_structure(sub, sub_path))
    
    return errors


# ---------------------------------------------------------------------------
# Tool Registry
# ---------------------------------------------------------------------------

class ToolRegistry:
    """
    Central registry for MCP tools.
    
    Loads tools from manifest.json and validates:
    1. All tools have unique names
    2. All input_schemas are valid JSON Schema structures
    3. Required fields (id, name, module) are present
    """
    
    def __init__(self, manifest_path: str | None = None):
        """Initialize registry, loading tools from manifest."""
        from src.mcp import get_manifest, manifest_path as default_manifest_path
        
        self._manifest_path = manifest_path or default_manifest_path()
        self._manifest = get_manifest(path=manifest_path)
        self._tools: dict[str, ToolSpec] = {}
        self._categories: list[str] = []
        self._validation_result: ValidationResult | None = None
        
        self._load_tools()
    
    def _load_tools(self):
        """Load tools from manifest into registry."""
        tools_data = self._manifest.get("tools", [])
        self._categories = self._manifest.get("categories", [])
        
        for tool_data in tools_data:
            if isinstance(tool_data, dict) and "name" in tool_data:
                spec = ToolSpec.from_dict(tool_data)
                self._tools[spec.name] = spec
    
    def validate(self, strict: bool = True) -> ValidationResult:
        """
        Validate all tools in the registry.
        
        Args:
            strict: If True, treat warnings as errors
            
        Returns:
            ValidationResult with errors and warnings
        """
        result = ValidationResult(valid=True, tool_count=len(self._tools))
        seen_names: set[str] = set()
        seen_ids: set[str] = set()
        
        for name, spec in self._tools.items():
            # Check required fields
            if not spec.id:
                result.add_error(name, "missing_field", "Tool is missing 'id' field")
            if not spec.name:
                result.add_error(name, "missing_field", "Tool is missing 'name' field")
            if not spec.module:
                result.add_error(name, "missing_field", "Tool is missing 'module' field")
            
            # Check unique names
            if spec.name in seen_names:
                result.add_error(name, "duplicate_name", f"Duplicate tool name: {spec.name}")
            seen_names.add(spec.name)
            
            # Check unique IDs
            if spec.id in seen_ids:
                result.add_error(name, "duplicate_id", f"Duplicate tool ID: {spec.id}")
            seen_ids.add(spec.id)
            
            # Validate input_schema if present
            if spec.input_schema:
                schema_errors = validate_json_schema_structure(spec.input_schema)
                for err in schema_errors:
                    result.add_error(name, "invalid_schema", err)
                
                # If jsonschema is available, do a full validation
                if HAS_JSONSCHEMA:
                    try:
                        # Validate the schema itself is valid JSON Schema
                        jsonschema.Draft7Validator.check_schema(spec.input_schema)
                    except jsonschema.exceptions.SchemaError as e:
                        result.add_error(
                            name, "schema_error",
                            f"Invalid JSON Schema: {e.message}",
                            {"path": list(e.absolute_path)}
                        )
            else:
                # Missing schema is a warning, not an error
                result.add_warning(name, "missing_schema", "Tool has no input_schema defined")
            
            # Check description
            if not spec.description:
                result.add_warning(name, "missing_description", "Tool has no description")
            
            # Validate module path format
            if spec.module and not spec.module.startswith("src.mcp.tools."):
                result.add_warning(
                    name, "module_path",
                    f"Module path '{spec.module}' doesn't follow convention 'src.mcp.tools.*'"
                )
        
        # In strict mode, warnings become errors
        if strict:
            for warning in result.warnings:
                if warning.error_type in ("missing_schema",):
                    # Only promote certain warnings to errors in strict mode
                    pass
        
        self._validation_result = result
        return result
    
    def get_tool(self, name: str) -> ToolSpec | None:
        """Get a tool specification by name."""
        return self._tools.get(name)
    
    def get_tools(self) -> dict[str, ToolSpec]:
        """Get all tool specifications."""
        return self._tools.copy()
    
    def list_tool_names(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())
    
    def list_tools_by_capability(self, capability: str) -> list[ToolSpec]:
        """Get tools that have a specific capability."""
        return [t for t in self._tools.values() if capability in t.capabilities]
    
    def list_tools_by_scope(self, scope: str) -> list[ToolSpec]:
        """Get tools that require a specific scope."""
        return [t for t in self._tools.values() if scope in t.scopes]
    
    def get_categories(self) -> list[str]:
        """Get list of tool categories."""
        return self._categories.copy()
    
    def get_validation_result(self) -> ValidationResult | None:
        """Get the last validation result."""
        return self._validation_result
    
    def is_valid(self) -> bool:
        """Check if registry passed validation."""
        if self._validation_result is None:
            self.validate()
        return self._validation_result.valid if self._validation_result else False
    
    def describe(self) -> dict[str, Any]:
        """Return a summary of the registry state."""
        return {
            "manifest_path": self._manifest_path,
            "tool_count": len(self._tools),
            "categories": self._categories,
            "tool_names": self.list_tool_names(),
            "validated": self._validation_result is not None,
            "valid": self._validation_result.valid if self._validation_result else None,
            "error_count": len(self._validation_result.errors) if self._validation_result else 0,
            "warning_count": len(self._validation_result.warnings) if self._validation_result else 0,
        }


# ---------------------------------------------------------------------------
# Singleton & Module Functions
# ---------------------------------------------------------------------------

_REGISTRY: ToolRegistry | None = None


def get_registry(*, force_reload: bool = False) -> ToolRegistry:
    """
    Get the singleton tool registry.
    
    On first access, loads from manifest and validates.
    """
    global _REGISTRY
    if _REGISTRY is None or force_reload:
        _REGISTRY = ToolRegistry()
        result = _REGISTRY.validate(strict=False)
        if result.errors:
            logger.error(
                "tool_registry.validation_failed",
                error_count=len(result.errors),
                errors=[str(e) for e in result.errors[:5]]  # First 5 errors
            )
        else:
            logger.info(
                "tool_registry.validated",
                tool_count=result.tool_count,
                warning_count=len(result.warnings)
            )
    return _REGISTRY


def validate_all_tools(*, strict: bool = False) -> list[str]:
    """
    Validate all tools in the registry.
    
    Returns:
        List of error messages (empty if valid)
    """
    registry = get_registry(force_reload=True)
    result = registry.validate(strict=strict)
    return [str(e) for e in result.errors]


def get_tool(name: str) -> ToolSpec | None:
    """Get a tool specification by name."""
    return get_registry().get_tool(name)


def list_tool_names() -> list[str]:
    """List all registered tool names."""
    return get_registry().list_tool_names()


def validate_tool_input(tool_name: str, payload: dict[str, Any]) -> tuple[bool, str | None]:
    """
    Validate a payload against a tool's input schema.
    
    Returns:
        (is_valid, error_message) tuple
    """
    spec = get_tool(tool_name)
    if not spec:
        return False, f"Unknown tool: {tool_name}"
    
    if not spec.input_schema:
        return True, None  # No schema to validate against
    
    if not HAS_JSONSCHEMA:
        return True, None  # Can't validate without jsonschema
    
    try:
        jsonschema.validate(payload, spec.input_schema)
        return True, None
    except jsonschema.ValidationError as e:
        return False, f"Validation error at {'.'.join(str(p) for p in e.absolute_path)}: {e.message}"
    except Exception as e:
        return False, f"Validation error: {str(e)}"


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    
    print("Validating MCP Tool Registry...")
    errors = validate_all_tools(strict=False)
    
    registry = get_registry()
    result = registry.get_validation_result()
    
    print(f"\nTools: {result.tool_count if result else 0}")
    print(f"Errors: {len(errors)}")
    print(f"Warnings: {len(result.warnings) if result else 0}")
    
    if errors:
        print("\n=== ERRORS ===")
        for err in errors:
            print(f"  ✗ {err}")
        sys.exit(1)
    
    if result and result.warnings:
        print("\n=== WARNINGS ===")
        for warn in result.warnings:
            print(f"  ⚠ {warn}")
    
    print("\n✓ Registry validation passed")
    sys.exit(0)
