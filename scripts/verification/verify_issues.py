#!/usr/bin/env python3
import json

with open("api/openapi.json", "r") as f:
    spec = json.load(f)

print("=" * 80)
print("VERIFICATION OF USER-REPORTED ISSUES")
print("=" * 80)
print()

# Issue 1: POST /agents/sessions runtime returns 200, must be 201
print("1️⃣  POST /agents/sessions status code")
print("-" * 80)
post_sessions = spec.get("paths", {}).get("/v1/agents/sessions", {}).get("post", {})
if post_sessions:
    responses = post_sessions.get("responses", {})
    if "201" in responses:
        resp = responses["201"]
        print(f"✅ 201 response exists")

        # Check Location header
        headers = resp.get("headers", {})
        if "Location" in headers:
            print(f"✅ Location header present")
        else:
            print(f"❌ Location header MISSING")
    else:
        print(f"❌ 201 response NOT found")
else:
    print(f"❌ POST /agents/sessions NOT found")
print()

# Issue 2: Error examples show "Not Found" and status 404 for 401/403/500
print("2️⃣  Error response definitions")
print("-" * 80)

responses_defs = spec.get("components", {}).get("responses", {})

for error_code, error_name in [("401", "Unauthorized"), ("403", "Forbidden"), ("500", "InternalError")]:
    print(f"\nChecking {error_code}:")

    # Check components responses
    resp_def = responses_defs.get(error_name, {})
    if resp_def:
        content = resp_def.get("content", {})
        if "application/problem+json" in content:
            examples = content["application/problem+json"].get("examples", {})
            for ex_name, ex in examples.items():
                value = ex.get("value", {})
                ex_status = value.get("status")
                ex_title = value.get("title")

                if ex_status == int(error_code):
                    print(f"  ✅ Example status: {ex_status}, title: {ex_title}")
                else:
                    print(f"  ❌ Example status: {ex_status} (should be {error_code}), title: {ex_title}")
        else:
            print(f"  ❌ No application/problem+json content")
print()

# Issue 3: Some 404 and 422 still using application/json
print("3️⃣  404 and 422 content types")
print("-" * 80)

issues = []
for path, path_item in spec.get("paths", {}).items():
    for method, operation in path_item.items():
        if method not in ["get", "post", "put", "delete", "patch", "head", "options"]:
            continue

        responses = operation.get("responses", {})
        for code in ["404", "422"]:
            if code in responses:
                resp = responses[code]
                content = resp.get("content", {})

                # Check content type
                if "application/json" in content and "application/problem+json" not in content:
                    issues.append(f"{method.upper()} {path} {code}: application/json (should be problem+json)")

if issues:
    print(f"❌ Found {len(issues)} issues:")
    for issue in issues[:5]:
        print(f"  - {issue}")
else:
    print(f"✅ All 404 and 422 responses use application/problem+json")
print()

# Issue 4: Try-it-out body for steps has "type": "string"
print("4️⃣  SessionStepRequest type field")
print("-" * 80)

post_steps = spec.get("paths", {}).get("/v1/agents/sessions/{session_id}/steps", {}).get("post", {})
if post_steps:
    req_body = post_steps.get("requestBody", {})
    content = req_body.get("content", {}).get("application/json", {})
    schema = content.get("schema", {})

    if "$ref" in schema:
        schema_name = schema["$ref"].split("/")[-1]
        schema_def = spec.get("components", {}).get("schemas", {}).get(schema_name, {})
        props = schema_def.get("properties", {})

        if "type" in props:
            type_field = props["type"]
            print(f"Schema: {schema_name}")

            # Check definition
            if "enum" in type_field:
                print(f"✅ Type field has enum: {type_field.get('enum')}")
            else:
                print(f"⚠️  Type field definition: {json.dumps(type_field, indent=2)}")

            # Check example
            if "example" in type_field:
                ex = type_field.get("example")
                if ex == "string":
                    print(f"❌ Example is 'string' (invalid, should be enum value)")
                else:
                    print(f"✅ Example is: {ex}")
            else:
                print(f"❌ No example provided")
        else:
            print(f"ℹ️  No 'type' field in {schema_name}")
            print(f"   Properties: {list(props.keys())}")
else:
    print(f"❌ POST /agents/sessions/{session_id}/steps NOT found")

print()
print("=" * 80)
