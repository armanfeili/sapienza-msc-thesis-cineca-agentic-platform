import json

from fastapi.testclient import TestClient

from src.app import create_app
import os

app = create_app()
client = TestClient(app)


def _auth_headers(bearer_headers):
    return bearer_headers


def test_agent_run_idempotency(bearer_headers):
    payload = {"prompt": "Hello"}
    headers = {**_auth_headers(bearer_headers), "Idempotency-Key": "test-key-1"}
    r1 = client.post("/v1/agents:run", json=payload, headers=headers)
    assert r1.status_code == 200
    j1 = r1.json()

    r2 = client.post("/v1/agents:run", json=payload, headers=headers)
    assert r2.status_code == 200
    j2 = r2.json()

    assert j1 == j2


def test_provider_set_main_deprecation(bearer_headers):
    headers = {**_auth_headers(bearer_headers), "Content-Type": "application/json"}
    payload = {"name": "demo-provider"}
    # Legacy provider route removed; ensure canonical colon-action path is present in OpenAPI
    spec = client.app.openapi()
    paths = spec.get("paths", {})
    assert "/v1/admin/models/providers/set_main" not in paths
    # canonical action path should exist
    assert any(p.startswith("/v1/admin/models/providers/") and p.endswith(":set-default") for p in paths.keys())
