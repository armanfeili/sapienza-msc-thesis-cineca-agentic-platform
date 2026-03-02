import json


def test_jobs_create_401_without_auth(client):
    # No Authorization header should result in 401 Unauthorized
    r = client.post("/v1/jobs:create", json={"type": "demo", "payload": {}})
    assert r.status_code == 401, r.text


def test_jobs_create_403_non_admin(client, mint_token):
    # Non-admin token (no admin role, no jobs:manage) should be forbidden
    token = mint_token(sub="user-1", roles=["user"])  # no admin role
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post("/v1/jobs:create", json={"type": "demo", "payload": {}}, headers=headers)
    assert r.status_code == 403, r.text


def test_jobs_create_400_unknown_type(client, bearer_headers):
    # Unknown job type should be rejected with 400
    r = client.post("/v1/jobs:create", json={"type": "not-a-real-type", "payload": {}}, headers=bearer_headers)
    assert r.status_code == 400, r.text
    data = r.json()
    # detail string should mention unknown job type
    assert "unknown" in (data.get("detail") or "").lower()


def test_jobs_create_400_schema_violation(client, bearer_headers, settings_patch):
    # Patch schema to require integer field 'x' and disallow additional properties
    settings_patch(
        JOB_PAYLOAD_SCHEMAS={
            "demo": {
                "type": "object",
                "properties": {"x": {"type": "integer"}},
                "required": ["x"],
                "additionalProperties": False,
            }
        }
    )
    # Missing required 'x' should trigger 400 invalid payload
    r = client.post("/v1/jobs:create", json={"type": "demo", "payload": {"y": "oops"}}, headers=bearer_headers)
    assert r.status_code == 400, r.text
    data = r.json()
    assert "invalid payload" in (data.get("detail") or "").lower()


def test_jobs_create_422_missing_type_field(client, bearer_headers):
    # Pydantic validation should produce 422 when required field 'type' is missing
    r = client.post("/v1/jobs:create", json={"payload": {}}, headers=bearer_headers)
    assert r.status_code == 422, r.text
