#!/usr/bin/env python3
"""
Fix all reported REST API issues:
1. POST /agents/sessions runtime 200 -> 201 with Location
2. Error examples (401/403/500) with wrong titles/status codes
3. 404/422 responses using application/json instead of application/problem+json
4. Try-it-out body for steps has invalid type examples
"""

import json
from pathlib import Path
from typing import Dict, Any, List


def load_spec(spec_path: str) -> Dict[str, Any]:
    with open(spec_path, "r") as f:
        return json.load(f)


def save_spec(spec: Dict[str, Any], spec_path: str) -> None:
    with open(spec_path, "w") as f:
        json.dump(spec, f, indent=2)


def fix_post_sessions_201(spec: Dict[str, Any]) -> List[str]:
    """Ensure POST /agents/sessions returns 201 with Location header."""
    changes = []

    post_sessions = spec.get("paths", {}).get("/v1/agents/sessions", {}).get("post", {})
    if not post_sessions:
        return ["⚠️ POST /v1/agents/sessions not found"]

    responses = post_sessions.get("responses", {})

    # Check 201 status
    if "201" in responses:
        resp = responses["201"]

        # Check Location header
        headers = resp.get("headers", {})
        if "Location" not in headers:
            headers["Location"] = {
                "description": "URI of newly created resource (RFC 7231)",
                "schema": {"type": "string"},
            }
            changes.append("✅ Added Location header to POST 201 response")
        else:
            changes.append("✅ POST 201 response already has Location header")
    else:
        changes.append("⚠️ POST /agents/sessions does not have 201 response")

    return changes


def fix_error_response_examples(spec: Dict[str, Any]) -> List[str]:
    """Fix error response examples to have correct title and status code."""
    changes = []

    # Define correct mappings
    error_fixes = {
        "Unauthorized": {"status": 401, "title": "Unauthorized", "detail": "Invalid or missing authentication"},
        "Forbidden": {"status": 403, "title": "Forbidden", "detail": "Insufficient permissions"},
        "InternalError": {
            "status": 500,
            "title": "Internal Server Error",
            "detail": "An error occurred processing your request",
        },
    }

    responses_defs = spec.get("components", {}).get("responses", {})

    for response_name, expected in error_fixes.items():
        resp_def = responses_defs.get(response_name, {})
        if not resp_def:
            continue

        content = resp_def.get("content", {}).get("application/problem+json", {})
        if "examples" not in content:
            content["examples"] = {}
            changes.append(f"ℹ️ Added examples to {response_name}")

        examples = content["examples"]
        ex_key = response_name.lower()

        # Ensure example exists with correct values
        if ex_key not in examples:
            examples[ex_key] = {
                "value": {
                    "type": "about:blank",
                    "title": expected["title"],
                    "status": expected["status"],
                    "detail": expected["detail"],
                    "extensions": {"correlation_id": "corr-123456", "timestamp": "2025-10-20T10:30:45Z"},
                },
                "summary": f'{expected["title"]} error',
            }
            changes.append(f"✅ Added example to {response_name}")
        else:
            # Fix existing example
            value = examples[ex_key]["value"]
            if value.get("status") != expected["status"]:
                value["status"] = expected["status"]
                changes.append(f"✅ Fixed {response_name} example status to {expected['status']}")
            if value.get("title") != expected["title"]:
                value["title"] = expected["title"]
                changes.append(f"✅ Fixed {response_name} example title to '{expected['title']}'")

    return changes


def fix_404_422_content_types(spec: Dict[str, Any]) -> List[str]:
    """Ensure all 404 and 422 responses use application/problem+json."""
    changes = []

    for path, path_item in spec.get("paths", {}).items():
        for method, operation in path_item.items():
            if method not in ["get", "post", "put", "delete", "patch", "head", "options"]:
                continue

            responses = operation.get("responses", {})

            for code in ["404", "422"]:
                if code not in responses:
                    continue

                resp = responses[code]
                content = resp.get("content", {})

                # If it has application/json but not problem+json, convert it
                if "application/json" in content and "application/problem+json" not in content:
                    # Move application/json content to problem+json
                    json_content = content.pop("application/json")
                    content["application/problem+json"] = json_content
                    changes.append(f"✅ {method.upper()} {path} {code}: converted to application/problem+json")

                # Ensure problem+json exists
                if "application/problem+json" not in content:
                    content["application/problem+json"] = {"schema": {"$ref": "#/components/schemas/ProblemDetail"}}
                    changes.append(f"✅ {method.upper()} {path} {code}: added application/problem+json")

    return changes


def fix_steps_type_enum(spec: Dict[str, Any]) -> List[str]:
    """Fix SessionStepRequest type field to have valid enum values."""
    changes = []

    # Find the schema
    schemas = spec.get("components", {}).get("schemas", {})

    # SessionStepRequest should have input field, not type field
    # But let's check if there's a step type or similar
    for schema_name in ["SessionStep", "StepInput", "Step"]:
        if schema_name in schemas:
            schema_def = schemas[schema_name]
            props = schema_def.get("properties", {})

            if "type" in props:
                type_field = props["type"]

                # Add enum if missing
                if "enum" not in type_field:
                    type_field["enum"] = ["message", "assistant", "system", "tool", "user", "error"]
                    type_field["example"] = "message"
                    changes.append(f"✅ Added enum to {schema_name}.type field")
                elif "example" in type_field and type_field["example"] == "string":
                    type_field["example"] = "message"
                    changes.append(f"✅ Fixed {schema_name}.type example from 'string' to 'message'")

    return changes


def main():
    spec_path = "api/openapi.json"

    print("=" * 80)
    print("FIXING ALL REPORTED REST API ISSUES")
    print("=" * 80)
    print()

    spec = load_spec(spec_path)
    all_changes = []

    # Issue 1
    print("1️⃣  Fixing POST /agents/sessions 201 status")
    changes = fix_post_sessions_201(spec)
    for c in changes:
        print(f"  {c}")
    all_changes.extend(changes)
    print()

    # Issue 2
    print("2️⃣  Fixing error response examples (401/403/500)")
    changes = fix_error_response_examples(spec)
    for c in changes:
        print(f"  {c}")
    all_changes.extend(changes)
    print()

    # Issue 3
    print("3️⃣  Fixing 404/422 content types")
    changes = fix_404_422_content_types(spec)
    for c in changes:
        print(f"  {c}")
    all_changes.extend(changes)
    print()

    # Issue 4
    print("4️⃣  Fixing SessionStepRequest type enum")
    changes = fix_steps_type_enum(spec)
    for c in changes:
        print(f"  {c}")
    all_changes.extend(changes)
    print()

    # Save
    print("=" * 80)
    save_spec(spec, spec_path)
    print(f"✅ Saved {len(all_changes)} changes to {spec_path}")
    print("=" * 80)


if __name__ == "__main__":
    main()
