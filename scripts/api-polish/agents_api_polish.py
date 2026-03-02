#!/usr/bin/env python3
"""
Agents API – Final Polish Script

Fixes 8 remaining TODO items:
1. Status codes & Location headers (POST → 201 with Location)
2. Error payload standardization (RFC 7807)
3. Field naming & schema alignment (metadata, enum types)
4. ETag & 304 semantics on agent-runs
5. Common Headers catalog
6. DELETE semantics (204 No Content)
7. Pagination consistency (cursor naming)
8. Rate-limit headers documentation
"""

import json
import re
from pathlib import Path
from typing import Dict, Any, Optional


def load_openapi():
    """Load OpenAPI spec."""
    with open("api/openapi.json", "r") as f:
        return json.load(f)


def save_openapi(spec: Dict[str, Any]):
    """Save OpenAPI spec."""
    with open("api/openapi.json", "w") as f:
        json.dump(spec, f, indent=2)
    print("✅ Saved OpenAPI spec to api/openapi.json")


def fix_post_status_codes(spec: Dict[str, Any]) -> Dict[str, Any]:
    """TODO 1: Fix POST endpoints to return 201 Created instead of 200."""
    if "paths" not in spec:
        return spec

    post_endpoints = {
        "/v1/agents/sessions": "Create agent session",
        "/v1/agents/sessions/{session_id}/steps": "Add step to session",
        "/v1/agent-runs": "Create agent run",
    }

    for path, description in post_endpoints.items():
        if path in spec["paths"] and "post" in spec["paths"][path]:
            post_op = spec["paths"][path]["post"]

            # Move 200 response to 201 if it exists
            if "200" in post_op.get("responses", {}):
                resp_200 = post_op["responses"].pop("200")
                if "201" not in post_op["responses"]:
                    post_op["responses"]["201"] = resp_200
                    post_op["responses"]["201"]["description"] = f"Resource created successfully"

            # Ensure 201 exists
            if "201" not in post_op["responses"]:
                post_op["responses"]["201"] = {
                    "description": f"{description} - 201 Created",
                    "headers": {
                        "Location": {
                            "description": "URI of newly created resource (RFC 7231)",
                            "schema": {"type": "string"},
                        },
                        "Idempotency-Key": {
                            "description": "Echo of Idempotency-Key request header",
                            "schema": {"type": "string"},
                        },
                        "Idempotency-Replayed": {
                            "description": "true if response was replayed from cache, false if fresh",
                            "schema": {"type": "boolean"},
                        },
                        "X-Request-Id": {
                            "description": "Request ID for tracing (assigned by server)",
                            "schema": {"type": "string"},
                        },
                    },
                }

            # Ensure Location header is in 201 response
            if "headers" not in post_op["responses"]["201"]:
                post_op["responses"]["201"]["headers"] = {}

            if "Location" not in post_op["responses"]["201"]["headers"]:
                post_op["responses"]["201"]["headers"]["Location"] = {
                    "description": "URI of newly created resource (RFC 7231)",
                    "schema": {"type": "string"},
                }

            # Update status_code if present
            if "status_code" in post_op:
                if post_op["status_code"] == 200:
                    post_op["status_code"] = 201

    print("✅ Fixed POST endpoints to return 201 Created with Location headers")
    return spec


def fix_error_payloads(spec: Dict[str, Any]) -> Dict[str, Any]:
    """TODO 2: Standardize error payloads to RFC 7807 (application/problem+json)."""
    if "paths" not in spec:
        return spec

    error_codes = {"400", "401", "403", "404", "422", "500"}

    for path, path_item in spec["paths"].items():
        for method, operation in path_item.items():
            if not isinstance(operation, dict) or "responses" not in operation:
                continue

            for code, response in operation["responses"].items():
                if code in error_codes and isinstance(response, dict):
                    # Ensure application/problem+json
                    if "content" in response and "application/json" in response["content"]:
                        problem_content = response["content"].pop("application/json")
                        response["content"]["application/problem+json"] = problem_content

                    # Ensure content exists
                    if "content" not in response:
                        response["content"] = {
                            "application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemDetail"}}
                        }
                    elif "application/problem+json" not in response.get("content", {}):
                        response["content"]["application/problem+json"] = {
                            "schema": {"$ref": "#/components/schemas/ProblemDetail"}
                        }

    print("✅ Standardized error payloads to application/problem+json (RFC 7807)")
    return spec


def fix_field_naming(spec: Dict[str, Any]) -> Dict[str, Any]:
    """TODO 3: Unify field naming (metadata vs session_metadata) in agent schemas."""
    if "components" not in spec or "schemas" not in spec["components"]:
        return spec

    # Fix SessionResponse to use consistent 'metadata' field (not aliased to session_metadata)
    if "SessionResponse" in spec["components"]["schemas"]:
        sr = spec["components"]["schemas"]["SessionResponse"]
        if "properties" in sr and "metadata" in sr["properties"]:
            sr["properties"]["metadata"]["description"] = "Session metadata"
            # Remove alias if present
            if "alias" in sr["properties"]["metadata"]:
                del sr["properties"]["metadata"]["alias"]

    # Ensure CreateStepRequest has enum type validation
    if "CreateStepRequest" in spec["components"]["schemas"]:
        csr = spec["components"]["schemas"]["CreateStepRequest"]
        if "properties" in csr and "type" in csr["properties"]:
            # Ensure type is enum
            type_prop = csr["properties"]["type"]
            if "enum" not in type_prop:
                type_prop["enum"] = ["assistant", "system", "user", "error", "tool", "message"]
                type_prop["description"] = "Step type (one of: assistant, system, user, error, tool, message)"

    print("✅ Unified field naming (metadata consistent, Step type as enum)")
    return spec


def add_etag_to_agent_runs(spec: Dict[str, Any]) -> Dict[str, Any]:
    """TODO 4: Add ETag & 304 semantics to GET /agent-runs/{run_id}."""
    if "paths" not in spec:
        return spec

    path = "/v1/agent-runs/{run_id}"
    if path in spec["paths"] and "get" in spec["paths"][path]:
        get_op = spec["paths"][path]["get"]

        # Add If-None-Match parameter if missing
        has_if_none_match = any(p.get("name") == "If-None-Match" for p in get_op.get("parameters", []))
        if not has_if_none_match:
            if "parameters" not in get_op:
                get_op["parameters"] = []
            get_op["parameters"].append(
                {
                    "name": "If-None-Match",
                    "in": "header",
                    "required": False,
                    "description": "Conditional GET: only return 200 if ETag doesn't match (RFC 7232)",
                    "schema": {"type": "string"},
                    "example": '"abc123def456"',
                }
            )

        # Ensure 200 response has ETag header
        if "200" in get_op.get("responses", {}):
            resp_200 = get_op["responses"]["200"]
            if "headers" not in resp_200:
                resp_200["headers"] = {}

            resp_200["headers"]["ETag"] = {
                "description": "Entity tag for cache validation (RFC 7232)",
                "schema": {"type": "string"},
                "example": '"abc123def456"',
            }

        # Add 304 Not Modified response
        if "304" not in get_op.get("responses", {}):
            get_op["responses"]["304"] = {
                "description": "Not Modified - resource unchanged (RFC 7232)",
                "headers": {
                    "ETag": {
                        "description": "Entity tag for cache validation (RFC 7232)",
                        "schema": {"type": "string"},
                        "example": '"abc123def456"',
                    }
                },
            }

    print("✅ Added ETag & 304 semantics to GET /agent-runs/{run_id}")
    return spec


def add_common_headers_info(spec: Dict[str, Any]) -> Dict[str, Any]:
    """TODO 5: Add Common Headers documentation to info section."""
    if "info" not in spec:
        spec["info"] = {}

    # Add x-common-headers extension for documentation
    spec["info"]["x-common-headers"] = {
        "description": "Standard headers used across all endpoints",
        "headers": {
            "ETag": {"description": "Entity tag for cache validation (RFC 7232)", "scope": ["GET"]},
            "If-None-Match": {
                "description": "Conditional GET: return 304 if matches ETag (RFC 7232)",
                "scope": ["GET"],
            },
            "Location": {"description": "URI of newly created resource (RFC 7231)", "scope": ["POST (201)"]},
            "Idempotency-Key": {
                "description": "Unique key for idempotent request handling (RFC 9110)",
                "scope": ["POST", "PUT"],
            },
            "Idempotency-Replayed": {
                "description": "Set to 'true' if this is a replayed (cached) request (RFC 9110)",
                "scope": ["POST (replay)", "PUT (replay)"],
            },
            "X-Request-Id": {"description": "Request ID for tracing (assigned by server)", "scope": ["All"]},
            "X-Correlation-Id": {
                "description": "Correlation ID for debugging (included in error responses)",
                "scope": ["Error responses"],
            },
            "Vary": {
                "description": "Indicates which request headers affect the response (RFC 7231)",
                "scope": ["Cached responses"],
            },
            "X-RateLimit-Limit": {"description": "Rate limit quota for this endpoint", "scope": ["Write operations"]},
            "X-RateLimit-Remaining": {
                "description": "Remaining requests in current window",
                "scope": ["Write operations"],
            },
            "X-RateLimit-Reset": {
                "description": "Unix timestamp when rate limit resets",
                "scope": ["Write operations"],
            },
        },
    }

    print("✅ Added Common Headers documentation to spec")
    return spec


def fix_delete_semantics(spec: Dict[str, Any]) -> Dict[str, Any]:
    """TODO 6: Ensure DELETE returns 204 No Content with no body."""
    if "paths" not in spec:
        return spec

    delete_paths = [
        "/v1/agents/sessions/{session_id}",
    ]

    for path in delete_paths:
        if path in spec["paths"] and "delete" in spec["paths"][path]:
            delete_op = spec["paths"][path]["delete"]

            # Ensure 204 response
            if "204" in delete_op.get("responses", {}):
                resp_204 = delete_op["responses"]["204"]
                # Remove content if present
                if "content" in resp_204:
                    del resp_204["content"]
                resp_204["description"] = "Session cancelled successfully - No Content"

            # Update status_code if present
            if "status_code" in delete_op:
                if delete_op["status_code"] != 204:
                    delete_op["status_code"] = 204

    print("✅ Fixed DELETE semantics (204 No Content with no body)")
    return spec


def fix_pagination_naming(spec: Dict[str, Any]) -> Dict[str, Any]:
    """TODO 7: Verify pagination uses 'cursor' and 'next_cursor' consistently."""
    if "paths" not in spec:
        return spec

    list_endpoints = [
        "/v1/agents/sessions",
        "/v1/agents/sessions/{session_id}/steps",
        "/v1/agent-runs",
    ]

    for path in list_endpoints:
        if path in spec["paths"] and "get" in spec["paths"][path]:
            get_op = spec["paths"][path]["get"]

            # Check parameters
            params = get_op.get("parameters", [])
            for param in params:
                # Rename page_token to cursor if needed
                if param.get("name") == "page_token":
                    param["name"] = "cursor"
                    param[
                        "description"
                    ] = "Opaque cursor for pagination (use value from previous response's next_cursor)"

    # Fix response schemas to use next_cursor
    if "components" in spec and "schemas" in spec["components"]:
        list_schemas = [
            "SessionListResponse",
            "StepListResponse",
            "RunListResponse",
        ]
        for schema_name in list_schemas:
            if schema_name in spec["components"]["schemas"]:
                schema = spec["components"]["schemas"][schema_name]
                if "properties" in schema and "next_cursor" not in schema["properties"]:
                    # Rename next_page_token to next_cursor if present
                    if "next_page_token" in schema["properties"]:
                        schema["properties"]["next_cursor"] = schema["properties"].pop("next_page_token")

    print("✅ Verified pagination naming (cursor → next_cursor)")
    return spec


def add_rate_limit_headers(spec: Dict[str, Any]) -> Dict[str, Any]:
    """TODO 8: Document rate-limit headers on write endpoints."""
    if "paths" not in spec:
        return spec

    write_endpoints = [
        ("/v1/agents/sessions", "post"),
        ("/v1/agents/sessions/{session_id}/steps", "post"),
        ("/v1/agent-runs", "post"),
        ("/v1/agents/sessions/{session_id}", "delete"),
    ]

    rate_limit_headers = {
        "X-RateLimit-Limit": {
            "description": "Rate limit quota for this endpoint (requests per minute)",
            "schema": {"type": "integer"},
            "example": 100,
        },
        "X-RateLimit-Remaining": {
            "description": "Remaining requests in current rate limit window",
            "schema": {"type": "integer"},
            "example": 95,
        },
        "X-RateLimit-Reset": {
            "description": "Unix timestamp (seconds) when rate limit resets",
            "schema": {"type": "integer"},
            "example": 1634567890,
        },
    }

    for path, method in write_endpoints:
        if path in spec["paths"] and method in spec["paths"][path]:
            operation = spec["paths"][path][method]
            responses = operation.get("responses", {})

            # Add rate limit headers to 2xx and 4xx responses
            for status_code in ["201", "200", "204", "400", "401", "403", "404", "409", "422", "500"]:
                if status_code in responses:
                    response = responses[status_code]
                    if isinstance(response, dict) and "$ref" not in response:
                        if "headers" not in response:
                            response["headers"] = {}

                        # Add rate limit headers (skip for 204)
                        if status_code != "204":
                            for header_name, header_def in rate_limit_headers.items():
                                if header_name not in response["headers"]:
                                    response["headers"][header_name] = header_def

    print("✅ Added rate-limit headers documentation to write endpoints")
    return spec


def main():
    """Execute all 8 polish fixes."""
    print("🔄 Starting Agents API Polish...")

    spec = load_openapi()

    # Apply all fixes in order
    spec = fix_post_status_codes(spec)
    spec = fix_error_payloads(spec)
    spec = fix_field_naming(spec)
    spec = add_etag_to_agent_runs(spec)
    spec = add_common_headers_info(spec)
    spec = fix_delete_semantics(spec)
    spec = fix_pagination_naming(spec)
    spec = add_rate_limit_headers(spec)

    save_openapi(spec)

    print("\n✅ Agents API Polish Complete!")
    print("📊 All 8 improvements applied:")
    print("  1. ✅ POST status codes → 201 Created with Location")
    print("  2. ✅ Error payloads → application/problem+json (RFC 7807)")
    print("  3. ✅ Field naming unified (metadata, enum types)")
    print("  4. ✅ ETag & 304 added to GET /agent-runs/{run_id}")
    print("  5. ✅ Common Headers catalog added")
    print("  6. ✅ DELETE semantics → 204 No Content")
    print("  7. ✅ Pagination → consistent cursor naming")
    print("  8. ✅ Rate-limit headers documented")


if __name__ == "__main__":
    main()
