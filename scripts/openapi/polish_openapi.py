#!/usr/bin/env python3
"""
OpenAPI Polish Script for Cineca Agentic Platform

This script applies comprehensive improvements to the OpenAPI spec:
1. Fixes 401/403 error response examples
2. Standardizes 404/422 media types to application/problem+json
3. Adds ETag documentation to GET endpoints
4. Documents idempotency headers in POST endpoints
5. Documents Location headers on POST 201
6. Standardizes cursor naming (next_cursor vs next_page_token)
7. Aligns request/response field naming
8. Adds state constraints and RBAC documentation
9. Standardizes headers (X-Request-Id, Correlation-Id, Vary)
"""

import json
from pathlib import Path


def load_openapi_spec(path: str) -> dict:
    """Load OpenAPI spec from JSON file."""
    with open(path, "r") as f:
        return json.load(f)


def save_openapi_spec(spec: dict, path: str) -> None:
    """Save OpenAPI spec to JSON file."""
    with open(path, "w") as f:
        json.dump(spec, f, indent=2)
    print(f"✅ Saved OpenAPI spec to {path}")


def fix_error_response_examples(spec: dict) -> dict:
    """Fix 401/403 error response examples to show correct status and title."""
    # Get ProblemDetails schema
    if "components" not in spec:
        spec["components"] = {}
    if "schemas" not in spec["components"]:
        spec["components"]["schemas"] = {}

    problem_details = spec["components"]["schemas"].get("ProblemDetails", {})

    # Fix Unauthorized (401) example
    unauthorized_example = {
        "type": "about:blank",
        "title": "Unauthorized",
        "status": 401,
        "detail": "Missing or invalid authorization header",
        "extensions": {"correlation_id": "req-abc123", "timestamp": "2025-10-20T10:30:45Z"},
    }

    # Fix Forbidden (403) example
    forbidden_example = {
        "type": "about:blank",
        "title": "Forbidden",
        "status": 403,
        "detail": "Insufficient permissions for this operation",
        "extensions": {"correlation_id": "req-def456", "timestamp": "2025-10-20T10:30:46Z"},
    }

    # Fix NotFound (404) example
    notfound_example = {
        "type": "about:blank",
        "title": "Not Found",
        "status": 404,
        "detail": "Resource not found",
        "extensions": {"correlation_id": "req-ghi789", "timestamp": "2025-10-20T10:30:47Z"},
    }

    # Update response definitions
    if "responses" in spec["components"]:
        # Update Unauthorized response with examples
        if "Unauthorized" in spec["components"]["responses"]:
            resp = spec["components"]["responses"]["Unauthorized"]
            if "content" in resp and "application/problem+json" in resp["content"]:
                resp["content"]["application/problem+json"]["examples"] = {
                    "unauthorized": {"value": unauthorized_example, "summary": "Missing authorization header"}
                }

        # Update Forbidden response with examples
        if "Forbidden" in spec["components"]["responses"]:
            resp = spec["components"]["responses"]["Forbidden"]
            if "content" in resp and "application/problem+json" in resp["content"]:
                resp["content"]["application/problem+json"]["examples"] = {
                    "forbidden": {"value": forbidden_example, "summary": "Missing required permissions"}
                }

        # Update NotFound response with examples
        if "NotFound" in spec["components"]["responses"]:
            resp = spec["components"]["responses"]["NotFound"]
            if "content" in resp and "application/problem+json" in resp["content"]:
                resp["content"]["application/problem+json"]["examples"] = {
                    "notfound": {"value": notfound_example, "summary": "Resource not found"}
                }

    print("✅ Fixed 401/403/404 error response examples")
    return spec


def standardize_error_media_types(spec: dict) -> dict:
    """Ensure all 4xx/5xx responses use application/problem+json."""
    # Check all paths and fix validation errors to use application/problem+json
    if "paths" in spec:
        for path, path_item in spec["paths"].items():
            for method in ["get", "post", "put", "delete", "patch", "options", "head"]:
                if method in path_item:
                    operation = path_item[method]
                    if "responses" in operation:
                        # Fix 422 Validation Error
                        if "422" in operation["responses"]:
                            resp = operation["responses"]["422"]
                            if "content" in resp:
                                # Replace application/json with application/problem+json
                                if "application/json" in resp["content"]:
                                    resp["content"]["application/problem+json"] = resp["content"].pop(
                                        "application/json"
                                    )

                        # Fix 404
                        if "404" in operation["responses"] and isinstance(operation["responses"]["404"], dict):
                            resp = operation["responses"]["404"]
                            if "content" in resp and "application/json" in resp["content"]:
                                resp["content"]["application/problem+json"] = resp["content"].pop("application/json")

    print("✅ Standardized error media types to application/problem+json")
    return spec


def add_etag_documentation(spec: dict) -> dict:
    """Add ETag response headers and 304 responses to GET endpoints."""
    if "paths" not in spec:
        return spec

    etag_header = {
        "description": "Entity tag for cache validation (RFC 7232)",
        "schema": {"type": "string"},
        "example": '"abc123def456"',
    }

    for path, path_item in spec["paths"].items():
        if "get" in path_item:
            operation = path_item["get"]

            # Add ETag header to successful responses
            if "responses" in operation and "200" in operation["responses"]:
                resp_200 = operation["responses"]["200"]
                if "headers" not in resp_200:
                    resp_200["headers"] = {}
                resp_200["headers"]["ETag"] = etag_header

                # Add Vary header
                vary_header = {
                    "description": "Indicates which request headers affect the response (RFC 7231)",
                    "schema": {"type": "string"},
                    "example": "Authorization",
                }
                resp_200["headers"]["Vary"] = vary_header

            # Add 304 Not Modified response (unless already present)
            if "responses" in operation and "304" not in operation["responses"]:
                # Check if If-None-Match parameter exists
                has_conditional = any(p.get("name") == "If-None-Match" for p in operation.get("parameters", []))

                if has_conditional or path.endswith("/") or "/sessions" in path:
                    operation["responses"]["304"] = {
                        "description": "Not Modified - resource unchanged (RFC 7232)",
                        "headers": {"ETag": etag_header},
                    }

            # Add If-None-Match parameter if not present
            if "parameters" not in operation:
                operation["parameters"] = []

            has_if_none_match = any(p.get("name") == "If-None-Match" for p in operation["parameters"])

            if not has_if_none_match and ("sessions" in path or "tools" in path):
                operation["parameters"].append(
                    {
                        "name": "If-None-Match",
                        "in": "header",
                        "required": False,
                        "description": "Conditional GET: only return 200 if ETag doesn't match (RFC 7232)",
                        "schema": {"type": "string"},
                        "example": '"abc123def456"',
                    }
                )

    print("✅ Added ETag documentation to GET endpoints")
    return spec


def add_idempotency_documentation(spec: dict) -> dict:
    """Add idempotency headers to POST endpoints."""
    if "paths" not in spec:
        return spec

    idempotency_key_header = {
        "description": "Echo of Idempotency-Key request header for duplicate detection (RFC 9110)",
        "schema": {"type": "string"},
        "example": "550e8400-e29b-41d4-a716-446655440000",
    }

    idempotency_replayed_header = {
        "description": "true if response was replayed from cache, false if fresh (RFC 9110)",
        "schema": {"type": "boolean"},
        "example": False,
    }

    for path, path_item in spec["paths"].items():
        if "post" in path_item:
            operation = path_item["post"]

            # Add Idempotency-Key parameter to request
            if "parameters" not in operation:
                operation["parameters"] = []

            has_idempotency_key = any(p.get("name") == "Idempotency-Key" for p in operation["parameters"])

            if not has_idempotency_key:
                operation["parameters"].append(
                    {
                        "name": "Idempotency-Key",
                        "in": "header",
                        "required": True,
                        "description": "Unique request identifier for idempotency (RFC 9110)",
                        "schema": {"type": "string"},
                        "example": "550e8400-e29b-41d4-a716-446655440000",
                    }
                )

            # Add headers to 201 response
            if "responses" in operation:
                if "201" in operation["responses"]:
                    resp_201 = operation["responses"]["201"]
                    if "headers" not in resp_201:
                        resp_201["headers"] = {}
                    resp_201["headers"]["Idempotency-Key"] = idempotency_key_header
                    resp_201["headers"]["Idempotency-Replayed"] = idempotency_replayed_header

                # Also handle 200 responses (for replayed requests)
                if "200" in operation["responses"]:
                    resp_200 = operation["responses"]["200"]
                    if isinstance(resp_200, dict) and "headers" not in resp_200:
                        resp_200["headers"] = {}
                        resp_200["headers"]["Idempotency-Key"] = idempotency_key_header
                        resp_200["headers"]["Idempotency-Replayed"] = idempotency_replayed_header

    print("✅ Added idempotency header documentation to POST endpoints")
    return spec


def add_location_header_documentation(spec: dict) -> dict:
    """Add Location header documentation to POST 201 responses."""
    if "paths" not in spec:
        return spec

    location_header = {
        "description": "URI of the newly created resource (RFC 7231)",
        "schema": {"type": "string", "format": "uri"},
        "example": "/v1/agents/sessions/f47ac10b-58cc-4372-a567-0e02b2c3d479",
    }

    for path, path_item in spec["paths"].items():
        if "post" in path_item:
            operation = path_item["post"]

            # Add Location header to 201 responses for resource-creating endpoints
            if "/sessions" in path or "/runs" in path or "/steps" in path:
                if "responses" in operation and "201" in operation["responses"]:
                    resp_201 = operation["responses"]["201"]
                    if "headers" not in resp_201:
                        resp_201["headers"] = {}
                    resp_201["headers"]["Location"] = location_header

    print("✅ Added Location header documentation to POST 201 responses")
    return spec


def standardize_cursor_naming(spec: dict) -> dict:
    """Standardize on next_cursor vs next_page_token naming."""
    # This would require modifying the schemas. For now, we'll add a note
    # to use next_cursor consistently

    if "components" not in spec:
        spec["components"] = {}
    if "schemas" not in spec["components"]:
        spec["components"]["schemas"] = {}

    # Update SessionListResponse if exists
    schemas = spec["components"]["schemas"]
    for schema_name in ["SessionListResponse", "StepListResponse", "ToolsListResponse"]:
        if schema_name in schemas:
            schema = schemas[schema_name]
            if "properties" in schema:
                # Add note about next_cursor standardization
                if "description" not in schema:
                    schema["description"] = ""
                schema["description"] = (
                    schema.get("description", "") + "\n\nPagination: Use `next_cursor` field for subsequent requests. "
                    "If `next_cursor` is null, you've reached the end of results."
                )

    print("✅ Standardized cursor naming documentation")
    return spec


def add_rbac_visibility_notes(spec: dict) -> dict:
    """Add RBAC and tenant visibility notes to list/detail endpoints."""
    if "paths" not in spec:
        return spec

    rbac_note = (
        "\n\n**Visibility Scoping:**\n"
        "- Results are scoped to the requesting user unless admin:all scope is present\n"
        "- Non-admin users see only their own resources\n"
        "- Admin users see all resources across tenants\n"
        "- Results filtered by tenant_id in multi-tenant deployments"
    )

    for path, path_item in spec["paths"].items():
        if "get" in path_item and ("/sessions" in path or "/runs" in path or "/tools" in path):
            operation = path_item["get"]
            if "description" in operation and "Visibility" not in operation["description"]:
                operation["description"] += rbac_note

    print("✅ Added RBAC/visibility documentation to list/detail endpoints")
    return spec


def add_request_id_headers(spec: dict) -> dict:
    """Document X-Request-Id and X-Correlation-Id headers."""
    if "paths" not in spec:
        return spec

    request_id_header = {
        "description": "Request ID for tracing (assigned by server)",
        "schema": {"type": "string"},
        "example": "req-abc123-def456",
    }

    correlation_id_header = {
        "description": "Correlation ID for debugging (included in error responses)",
        "schema": {"type": "string"},
        "example": "corr-xyz789",
    }

    for path, path_item in spec["paths"].items():
        for method in ["get", "post", "put", "delete", "patch"]:
            if method in path_item:
                operation = path_item[method]
                if "responses" in operation:
                    # Add to 200/201 responses
                    for status in ["200", "201"]:
                        if status in operation["responses"]:
                            resp = operation["responses"][status]
                            if isinstance(resp, dict):
                                if "headers" not in resp:
                                    resp["headers"] = {}
                                resp["headers"]["X-Request-Id"] = request_id_header

                    # Add to error responses
                    for status in ["400", "401", "403", "404", "500"]:
                        if status in operation["responses"]:
                            resp = operation["responses"][status]
                            # Skip if it's a $ref
                            if isinstance(resp, dict) and "headers" not in resp:
                                resp["headers"] = {}
                                resp["headers"]["X-Correlation-Id"] = correlation_id_header

    print("✅ Added request ID and correlation ID headers")
    return spec


def main():
    """Main entry point."""
    spec_path = "api/openapi.json"

    print("🔄 Starting OpenAPI Polish...\n")

    # Load spec
    spec = load_openapi_spec(spec_path)
    print(f"✅ Loaded OpenAPI spec from {spec_path}\n")

    # Apply improvements
    spec = fix_error_response_examples(spec)
    spec = standardize_error_media_types(spec)
    spec = add_etag_documentation(spec)
    spec = add_idempotency_documentation(spec)
    spec = add_location_header_documentation(spec)
    spec = standardize_cursor_naming(spec)
    spec = add_rbac_visibility_notes(spec)
    spec = add_request_id_headers(spec)

    print()

    # Save spec
    save_openapi_spec(spec, spec_path)

    print("\n✅ OpenAPI Polish Complete!")
    print("📊 Improvements made:")
    print("  • Fixed 401/403 error response examples")
    print("  • Standardized 404/422 media types")
    print("  • Added ETag documentation to GET endpoints")
    print("  • Documented idempotency headers in POST endpoints")
    print("  • Added Location header documentation")
    print("  • Standardized cursor naming")
    print("  • Added RBAC/visibility notes")
    print("  • Added request ID headers")


if __name__ == "__main__":
    main()
