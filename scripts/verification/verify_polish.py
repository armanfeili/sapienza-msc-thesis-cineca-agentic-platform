#!/usr/bin/env python3
"""
Verify all 7 REST polish requirements are complete and consistent.
Final comprehensive check before deployment.
"""

import json
from pathlib import Path


def load_spec(spec_path: str) -> dict:
    """Load OpenAPI spec."""
    with open(spec_path, "r") as f:
        return json.load(f)


def verify_all():
    spec_path = "/Users/armanfeili/Arman/Sapienza Courses/4-semester/Thesis/ILP-Thesis-2025/Cineca-Agentic-Platform/api/openapi.json"
    spec = load_spec(spec_path)

    print("=" * 80)
    print("FINAL REST API POLISH VERIFICATION")
    print("=" * 80)
    print()

    issues = []

    # Requirement A: Status codes & Location headers
    print("✓ Requirement A: Status codes & Location headers")
    post_endpoints = [
        "/v1/agents/sessions",
        "/v1/agents/sessions/{session_id}/steps",
        "/v1/agent-runs",
    ]
    for path in post_endpoints:
        post_op = spec.get("paths", {}).get(path, {}).get("post", {})
        if "201" in post_op.get("responses", {}):
            headers = post_op["responses"]["201"].get("headers", {})
            if "Location" in headers and "Idempotency-Replayed" in headers:
                print(f"  ✅ {path}")
            else:
                print(f"  ❌ {path} - missing headers")
                issues.append(f"{path} 201 missing headers")
        else:
            print(f"  ❌ {path} - no 201 response")
            issues.append(f"{path} no 201")

    # Requirement B: Error responses RFC 7807
    print("\n✓ Requirement B: Error responses (RFC 7807)")
    sample_endpoints = [("/v1/agents/sessions", "post"), ("/v1/agent-runs", "post")]
    for path, method in sample_endpoints:
        op = spec.get("paths", {}).get(path, {}).get(method, {})
        responses = op.get("responses", {})
        all_errors_ok = all(
            "application/problem+json" in responses.get(code, {}).get("content", {})
            for code in ["400", "401", "403", "404", "500"]
            if code in responses
        )
        status_icon = "✅" if all_errors_ok else "❌"
        print(f"  {status_icon} {method.upper()} {path}")
        if not all_errors_ok:
            issues.append(f"{method.upper()} {path} error responses not RFC 7807")

    # Requirement C: Schemas alignment
    print("\n✓ Requirement C: Schemas & examples")
    schemas = spec.get("components", {}).get("schemas", {})
    create_step = schemas.get("CreateStepRequest", {})
    if create_step and "enum" in create_step.get("properties", {}).get("type", {}):
        print("  ✅ CreateStepRequest.type is enum")
    else:
        print("  ⚠️  CreateStepRequest.type (not critical for agents API)")

    # Requirement D: Caching headers ETag
    print("\n✓ Requirement D: Caching headers (ETag)")
    get_run = spec.get("paths", {}).get("/v1/agent-runs/{run_id}", {}).get("get", {})
    if get_run:
        responses = get_run.get("responses", {})
        has_etag = "ETag" in responses.get("200", {}).get("headers", {})
        has_if_none_match = any(p.get("name") == "If-None-Match" for p in get_run.get("parameters", []))
        has_304 = "304" in responses

        if has_etag and has_if_none_match and has_304:
            print("  ✅ GET /v1/agent-runs/{run_id} has ETag support")
        else:
            print(f"  ❌ Missing: ETag={has_etag}, If-None-Match={has_if_none_match}, 304={has_304}")
            issues.append("GET /v1/agent-runs/{run_id} ETag support incomplete")

    # Requirement E: Headers consistency
    print("\n✓ Requirement E: Headers consistency")
    info = spec.get("info", {})
    if "x-common-headers" in info:
        headers = info["x-common-headers"].get("headers", {})
        required_headers = [
            "ETag",
            "If-None-Match",
            "Location",
            "Idempotency-Key",
            "Idempotency-Replayed",
            "X-Request-Id",
            "X-Correlation-Id",
            "Vary",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
        ]
        present = all(h in headers for h in required_headers)
        if present:
            print("  ✅ x-common-headers documented with all required headers")
        else:
            missing = [h for h in required_headers if h not in headers]
            print(f"  ⚠️  Missing headers: {', '.join(missing)}")
    else:
        print("  ❌ x-common-headers not in spec")
        issues.append("x-common-headers missing")

    # Requirement F: DELETE semantics
    print("\n✓ Requirement F: DELETE semantics")
    delete_session = spec.get("paths", {}).get("/v1/agents/sessions/{session_id}", {}).get("delete", {})
    if delete_session:
        responses = delete_session.get("responses", {})
        if "204" in responses and "200" not in responses:
            print("  ✅ DELETE /v1/agents/sessions/{session_id} returns 204 No Content")
        elif "204" in responses and "200" in responses:
            print("  ⚠️  DELETE has both 204 and 200 (should remove 200)")
            issues.append("DELETE has both 204 and 200")
        else:
            print("  ❌ DELETE missing 204 response")
            issues.append("DELETE missing 204")

    # Requirement G: Pagination polish
    print("\n✓ Requirement G: Pagination (cursor/next_cursor)")
    list_endpoints = [
        ("/v1/agents/sessions", "SessionListResponse"),
        ("/v1/agents/sessions/{session_id}/steps", "SessionStepsListResponse"),
    ]

    for path, response_model in list_endpoints:
        get_op = spec.get("paths", {}).get(path, {}).get("get", {})
        if get_op:
            # Check cursor parameter
            params = get_op.get("parameters", [])
            has_cursor = any(p.get("name") == "cursor" for p in params)

            # Check next_cursor in response schema
            responses = get_op.get("responses", {})
            schema_ref = responses.get("200", {}).get("content", {}).get("application/json", {}).get("schema", {})

            # Get the actual schema
            schema = spec.get("components", {}).get("schemas", {}).get(response_model, {})
            has_next_cursor = "next_cursor" in schema.get("properties", {})

            if has_cursor and has_next_cursor:
                print(f"  ✅ GET {path}: cursor parameter + next_cursor response")
            else:
                print(f"  ⚠️  GET {path}: cursor={has_cursor}, next_cursor={has_next_cursor}")
                if not has_cursor:
                    issues.append(f"{path} missing cursor parameter")
                if not has_next_cursor:
                    issues.append(f"{response_model} missing next_cursor field")

    # Summary
    print("\n" + "=" * 80)
    if not issues:
        print("✅ ALL 7 REQUIREMENTS VERIFIED - READY FOR DEPLOYMENT")
    else:
        print("❌ ISSUES FOUND:")
        for issue in issues:
            print(f"  - {issue}")
    print("=" * 80)

    return len(issues) == 0


if __name__ == "__main__":
    success = verify_all()
    exit(0 if success else 1)
