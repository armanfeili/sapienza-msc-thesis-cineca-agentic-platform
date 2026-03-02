"""
OpenAPI contract tests for tenant endpoints.

Validates that the generated OpenAPI spec matches expected structure:
- Required header parameters (X-Tenant-Id)
- Required request body fields (name, admin_email)
- Response examples for all status codes
- Proper response headers
"""

import json
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def openapi_spec():
    """Load the generated OpenAPI specification."""
    spec_path = Path(__file__).parent.parent / "api" / "openapi.json"
    with open(spec_path) as f:
        return json.load(f)


class TestTenantOpenAPIContract:
    """Validate OpenAPI spec for tenant endpoints."""

    def test_post_tenants_has_x_tenant_id_header(self, openapi_spec):
        """POST /v1/admin/tenants requires X-Tenant-Id header in spec."""
        post_op = openapi_spec["paths"]["/v1/admin/tenants"]["post"]
        parameters = post_op.get("parameters", [])

        # Find X-Tenant-Id header parameter
        header_params = [p for p in parameters if p.get("in") == "header" and p.get("name") == "X-Tenant-Id"]
        assert len(header_params) == 1, "POST should have exactly one X-Tenant-Id header parameter"

        header_param = header_params[0]
        assert header_param["required"] is True, "X-Tenant-Id should be required"
        assert "description" in header_param, "X-Tenant-Id should have description"
        assert "example" in header_param, "X-Tenant-Id should have example value"

    def test_patch_tenants_has_x_tenant_id_header(self, openapi_spec):
        """PATCH /v1/admin/tenants/{id} requires X-Tenant-Id header in spec."""
        patch_op = openapi_spec["paths"]["/v1/admin/tenants/{tenant_id}"]["patch"]
        parameters = patch_op.get("parameters", [])

        # Find X-Tenant-Id header parameter
        header_params = [p for p in parameters if p.get("in") == "header" and p.get("name") == "X-Tenant-Id"]
        assert len(header_params) == 1, "PATCH should have exactly one X-Tenant-Id header parameter"

        header_param = header_params[0]
        assert header_param["required"] is True, "X-Tenant-Id should be required"

    def test_delete_tenants_has_x_tenant_id_header(self, openapi_spec):
        """DELETE /v1/admin/tenants/{id} requires X-Tenant-Id header in spec."""
        delete_op = openapi_spec["paths"]["/v1/admin/tenants/{tenant_id}"]["delete"]
        parameters = delete_op.get("parameters", [])

        # Find X-Tenant-Id header parameter
        header_params = [p for p in parameters if p.get("in") == "header" and p.get("name") == "X-Tenant-Id"]
        assert len(header_params) == 1, "DELETE should have exactly one X-Tenant-Id header parameter"

        header_param = header_params[0]
        assert header_param["required"] is True, "X-Tenant-Id should be required"

    def test_post_request_body_required_fields(self, openapi_spec):
        """POST request body schema marks name and admin_email as required."""
        schema_ref = openapi_spec["paths"]["/v1/admin/tenants"]["post"]["requestBody"]["content"]["application/json"][
            "schema"
        ]
        assert "$ref" in schema_ref, "Request body should reference schema"

        # Extract schema name and look it up
        schema_name = schema_ref["$ref"].split("/")[-1]
        schema = openapi_spec["components"]["schemas"][schema_name]

        # Verify required fields
        assert "required" in schema, "Schema should have 'required' array"
        assert "name" in schema["required"], "name should be required"
        assert "admin_email" in schema["required"], "admin_email should be required"
        assert "metadata" not in schema["required"], "metadata should be optional"

    def test_post_request_body_has_multiple_examples(self, openapi_spec):
        """POST request body schema has multiple examples (minimal, full, basic)."""
        schema_ref = openapi_spec["paths"]["/v1/admin/tenants"]["post"]["requestBody"]["content"]["application/json"][
            "schema"
        ]
        schema_name = schema_ref["$ref"].split("/")[-1]
        schema = openapi_spec["components"]["schemas"][schema_name]

        assert "examples" in schema, "Schema should have examples"
        examples = schema["examples"]
        assert len(examples) >= 2, "Should have at least 2 examples (minimal and full)"

        # Check for minimal example (required fields only)
        minimal_examples = [ex for ex in examples if "minimal" in ex.get("summary", "").lower()]
        assert len(minimal_examples) >= 1, "Should have a minimal example"

        minimal_value = minimal_examples[0]["value"]
        assert "name" in minimal_value, "Minimal example should have name"
        assert "admin_email" in minimal_value, "Minimal example should have admin_email"
        # metadata is optional, may or may not be present

    def test_post_responses_include_idempotent_and_conflict(self, openapi_spec):
        """POST responses include 200 (idempotent) and 409 (conflict) examples."""
        post_op = openapi_spec["paths"]["/v1/admin/tenants"]["post"]
        responses = post_op["responses"]

        # Check for 200 idempotent response
        assert "200" in responses, "Should have 200 response for idempotent case"
        assert "description" in responses["200"], "200 should have description"
        assert "idempotent" in responses["200"]["description"].lower(), "200 description should mention idempotency"

        # Check for 409 conflict response
        assert "409" in responses, "Should have 409 response for conflict case"
        assert "description" in responses["409"], "409 should have description"
        assert "conflict" in responses["409"]["description"].lower(), "409 description should mention conflict"

    def test_post_201_response_has_headers(self, openapi_spec):
        """POST 201 response documents response headers (Location, ETag, etc.)."""
        post_op = openapi_spec["paths"]["/v1/admin/tenants"]["post"]
        response_201 = post_op["responses"]["201"]

        assert "headers" in response_201, "201 response should document headers"
        headers = response_201["headers"]

        # Key headers for POST 201
        assert "Location" in headers, "Should document Location header"
        assert "ETag" in headers, "Should document ETag header"
        assert "X-Request-Id" in headers, "Should document X-Request-Id header"

    def test_delete_409_response_has_blockers_example(self, openapi_spec):
        """DELETE 409 response includes blockers array in example."""
        delete_op = openapi_spec["paths"]["/v1/admin/tenants/{tenant_id}"]["delete"]
        response_409 = delete_op["responses"]["409"]

        assert "content" in response_409, "409 should have content"
        example = response_409["content"]["application/json"]["example"]

        # Verify RFC 7807 structure
        assert "type" in example, "409 should have 'type' field (RFC 7807)"
        assert "status" in example, "409 should have 'status' field"
        assert example["status"] == 409, "Status should be 409"

        # Verify blockers extension
        assert "extensions" in example, "409 should have extensions"
        assert "blockers" in example["extensions"], "409 extensions should include blockers"
        assert isinstance(example["extensions"]["blockers"], list), "Blockers should be an array"
        assert len(example["extensions"]["blockers"]) > 0, "Blockers example should have at least one item"

    def test_delete_204_response_has_headers(self, openapi_spec):
        """DELETE 204 response documents response headers."""
        delete_op = openapi_spec["paths"]["/v1/admin/tenants/{tenant_id}"]["delete"]
        response_204 = delete_op["responses"]["204"]

        assert "headers" in response_204, "204 response should document headers"
        headers = response_204["headers"]

        # Key headers for DELETE 204
        assert "X-Request-Id" in headers, "Should document X-Request-Id header"
        assert "X-Event-Id" in headers, "Should document X-Event-Id header"
