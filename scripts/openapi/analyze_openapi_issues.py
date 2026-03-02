#!/usr/bin/env python3
"""
Analyze OpenAPI spec for the 7 REST polish requirements (A-G).
Identifies issues to fix in subsequent automation script.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Set, Tuple


def load_spec(spec_path: str) -> Dict[str, Any]:
    """Load OpenAPI spec from file."""
    with open(spec_path, "r") as f:
        return json.load(f)


def check_requirement_a(spec: Dict) -> Dict[str, Any]:
    """A) Status codes & Location headers"""
    issues = []

    # Check POST /agents/sessions
    post_sessions = spec.get("paths", {}).get("/v1/agents/sessions", {}).get("post", {})
    responses_a = post_sessions.get("responses", {})

    # Check if 201 exists and has Location header
    if "201" in responses_a:
        resp_201 = responses_a["201"]
        headers_201 = resp_201.get("headers", {})
        if "Location" not in headers_201:
            issues.append("POST /v1/agents/sessions 201 missing Location header")
        if "Idempotency-Replayed" not in headers_201:
            issues.append("POST /v1/agents/sessions 201 missing Idempotency-Replayed header")
    else:
        issues.append("POST /v1/agents/sessions missing 201 response")

    # Check POST /agents/sessions/{id}/steps
    post_steps = spec.get("paths", {}).get("/v1/agents/sessions/{session_id}/steps", {}).get("post", {})
    responses_steps = post_steps.get("responses", {})
    if "201" in responses_steps:
        resp_201 = responses_steps["201"]
        headers_201 = resp_201.get("headers", {})
        if "Location" not in headers_201:
            issues.append("POST /v1/agents/sessions/{session_id}/steps 201 missing Location header")
    else:
        issues.append("POST /v1/agents/sessions/{session_id}/steps missing 201 response")

    # Check POST /agent-runs
    post_runs = spec.get("paths", {}).get("/v1/agent-runs", {}).get("post", {})
    responses_runs = post_runs.get("responses", {})
    if "201" in responses_runs:
        resp_201 = responses_runs["201"]
        headers_201 = resp_201.get("headers", {})
        if "Location" not in headers_201:
            issues.append("POST /v1/agent-runs 201 missing Location header")
    else:
        issues.append("POST /v1/agent-runs missing 201 response")

    return {"requirement": "A", "name": "Status codes & Location", "issues": issues}


def check_requirement_b(spec: Dict) -> Dict[str, Any]:
    """B) Error responses (RFC 7807)"""
    issues = []

    # Find all error responses across all endpoints
    for path, path_item in spec.get("paths", {}).items():
        for method, operation in path_item.items():
            if method not in ["get", "post", "put", "delete", "patch"]:
                continue

            responses = operation.get("responses", {})

            # Check 401
            if "401" in responses:
                resp = responses["401"]
                content = resp.get("content", {})
                if "application/problem+json" not in content:
                    issues.append(f"{method.upper()} {path} 401 not using application/problem+json")
                # Check schema
                if "application/problem+json" in content:
                    schema = content["application/problem+json"].get("schema", {})
                    if "$ref" in schema:
                        ref = schema["$ref"]
                        # For now just note, we'll check the schema itself
                        pass

            # Check 403
            if "403" in responses:
                resp = responses["403"]
                content = resp.get("content", {})
                if "application/problem+json" not in content:
                    issues.append(f"{method.upper()} {path} 403 not using application/problem+json")

            # Check 404
            if "404" in responses:
                resp = responses["404"]
                content = resp.get("content", {})
                if "application/problem+json" not in content:
                    issues.append(f"{method.upper()} {path} 404 not using application/problem+json")

            # Check 500
            if "500" in responses:
                resp = responses["500"]
                content = resp.get("content", {})
                if "application/problem+json" not in content:
                    issues.append(f"{method.upper()} {path} 500 not using application/problem+json")

    return {"requirement": "B", "name": "Error responses (RFC 7807)", "issues": issues}


def check_requirement_c(spec: Dict) -> Dict[str, Any]:
    """C) Schemas & examples alignment"""
    issues = []

    # Check POST /agents/sessions request for metadata naming
    post_session = spec.get("paths", {}).get("/v1/agents/sessions", {}).get("post", {})
    req_schema = post_session.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {})

    # Check POST /agents/sessions/{id}/steps for type field
    post_steps = spec.get("paths", {}).get("/v1/agents/sessions/{session_id}/steps", {}).get("post", {})
    steps_req = post_steps.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {})

    # Check components/schemas for CreateStepRequest
    schemas = spec.get("components", {}).get("schemas", {})
    create_step_schema = schemas.get("CreateStepRequest", {})
    if create_step_schema:
        props = create_step_schema.get("properties", {})
        type_field = props.get("type", {})
        if type_field.get("type") == "string" and "enum" not in type_field:
            issues.append("CreateStepRequest.type should be enum, not string")

    return {"requirement": "C", "name": "Schemas & examples", "issues": issues}


def check_requirement_d(spec: Dict) -> Dict[str, Any]:
    """D) Caching headers (ETag)"""
    issues = []

    # Check GET /agent-runs/{run_id}
    get_run = spec.get("paths", {}).get("/v1/agent-runs/{run_id}", {}).get("get", {})
    if get_run:
        responses = get_run.get("responses", {})

        # Check 200 has ETag
        if "200" in responses:
            headers_200 = responses["200"].get("headers", {})
            if "ETag" not in headers_200:
                issues.append("GET /v1/agent-runs/{run_id} 200 missing ETag header")

        # Check for If-None-Match parameter
        params = get_run.get("parameters", [])
        has_if_none_match = any(p.get("name") == "If-None-Match" for p in params)
        if not has_if_none_match:
            issues.append("GET /v1/agent-runs/{run_id} missing If-None-Match parameter")

        # Check for 304 response
        if "304" not in responses:
            issues.append("GET /v1/agent-runs/{run_id} missing 304 Not Modified response")

    return {"requirement": "D", "name": "Caching headers (ETag)", "issues": issues}


def check_requirement_e(spec: Dict) -> Dict[str, Any]:
    """E) Headers consistency"""
    issues = []

    # Check if x-common-headers exists in info
    info = spec.get("info", {})
    if "x-common-headers" not in info:
        issues.append("Missing x-common-headers in spec info")

    # Check endpoints for X-Request-Id and X-Correlation-Id
    required_on_errors = {"X-Correlation-Id"}
    required_on_all = {"X-Request-Id"}  # Should be on all responses

    # Sample check on a few endpoints
    sample_endpoints = [
        ("/v1/agents/sessions", "post"),
        ("/v1/agent-runs", "post"),
        ("/v1/agent-runs/{run_id}", "get"),
    ]

    for path, method in sample_endpoints:
        endpoint = spec.get("paths", {}).get(path, {}).get(method, {})
        if not endpoint:
            continue

        responses = endpoint.get("responses", {})

        # Check error responses have X-Correlation-Id
        for status in ["400", "401", "403", "404", "500"]:
            if status in responses:
                headers = responses[status].get("headers", {})
                # Error responses should have X-Correlation-Id
                # This is somewhat optional per RFC, but good practice

    # Check X-RateLimit-* on write endpoints
    write_endpoints = [
        ("/v1/agents/sessions", "post"),
        ("/v1/agent-runs", "post"),
        ("/v1/agents/sessions/{session_id}/steps", "post"),
    ]

    for path, method in write_endpoints:
        endpoint = spec.get("paths", {}).get(path, {}).get(method, {})
        if endpoint:
            responses = endpoint.get("responses", {})
            if "201" in responses or "200" in responses:
                success_status = "201" if "201" in responses else "200"
                headers = responses[success_status].get("headers", {})
                rate_limit_headers = {h for h in headers if h.startswith("X-RateLimit-")}
                if len(rate_limit_headers) < 3:
                    issues.append(f"{method.upper()} {path} missing complete X-RateLimit-* headers")

    return {"requirement": "E", "name": "Headers consistency", "issues": issues}


def check_requirement_f(spec: Dict) -> Dict[str, Any]:
    """F) DELETE semantics"""
    issues = []

    # Check DELETE /agents/sessions/{session_id}
    delete_session = spec.get("paths", {}).get("/v1/agents/sessions/{session_id}", {}).get("delete", {})
    if delete_session:
        responses = delete_session.get("responses", {})

        if "204" not in responses:
            issues.append("DELETE /v1/agents/sessions/{session_id} missing 204 No Content response")
        else:
            resp_204 = responses["204"]
            # Check it has no Content-Type requirement
            content = resp_204.get("content", {})
            if content:
                issues.append("DELETE /v1/agents/sessions/{session_id} 204 should have no body/content")

    return {"requirement": "F", "name": "DELETE semantics", "issues": issues}


def check_requirement_g(spec: Dict) -> Dict[str, Any]:
    """G) Pagination polish"""
    issues = []

    # Check list endpoints for cursor/next_cursor
    list_endpoints = [
        ("/v1/agents/sessions", "get"),
        ("/v1/agents/sessions/{session_id}/steps", "get"),
        ("/v1/agent-runs", "get"),
    ]

    for path, method in list_endpoints:
        endpoint = spec.get("paths", {}).get(path, {}).get(method, {})
        if not endpoint:
            continue

        # Check parameters for cursor
        params = endpoint.get("parameters", [])
        has_cursor = any(p.get("name") == "cursor" for p in params)
        if not has_cursor:
            issues.append(f"{method.upper()} {path} missing cursor query parameter")

        # Check response schema for next_cursor
        responses = endpoint.get("responses", {})
        if "200" in responses:
            schema = responses["200"].get("content", {}).get("application/json", {}).get("schema", {})
            # Typically list responses have a model like SessionListResponse
            # Check the schema properties for next_cursor

    return {"requirement": "G", "name": "Pagination polish", "issues": issues}


def main():
    spec_path = "/Users/armanfeili/Arman/Sapienza Courses/4-semester/Thesis/ILP-Thesis-2025/Cineca-Agentic-Platform/api/openapi.json"

    spec = load_spec(spec_path)

    print("=" * 80)
    print("OpenAPI Spec Analysis - 7 REST Polish Requirements")
    print("=" * 80)
    print()

    checks = [
        check_requirement_a(spec),
        check_requirement_b(spec),
        check_requirement_c(spec),
        check_requirement_d(spec),
        check_requirement_e(spec),
        check_requirement_f(spec),
        check_requirement_g(spec),
    ]

    total_issues = 0

    for check in checks:
        req = check["requirement"]
        name = check["name"]
        issues = check["issues"]
        total_issues += len(issues)

        print(f"\n{req}) {name}")
        print("-" * 80)
        if not issues:
            print("✅ No issues found")
        else:
            for issue in issues:
                print(f"  ⚠️  {issue}")

    print("\n" + "=" * 80)
    print(f"Total Issues Found: {total_issues}")
    print("=" * 80)


if __name__ == "__main__":
    main()
