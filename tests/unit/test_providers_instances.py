from __future__ import annotations

from typing import Any, Dict

from fastapi.testclient import TestClient


def test_providers_and_instances_crud(client: TestClient, bearer_headers) -> None:
    headers = {**bearer_headers, "Content-Type": "application/json"}

    # Register provider using canonical register endpoint
    prov = {"name": "prov-test", "base_url": "http://example"}
    resp = client.post("/v1/admin/models/providers/register", headers=headers, json=prov)
    assert resp.status_code == 200
    assert resp.json()["details"]["name"] == "prov-test"

    # Get provider detail
    resp = client.get("/v1/admin/models/providers/prov-test", headers=bearer_headers)
    assert resp.status_code == 200
    assert resp.json().get("name") == "prov-test" or resp.json().get("id") == "prov-test"

    # Create instance
    inst_payload = {"modelKey": "demo-echo", "options": {}}
    resp = client.post("/v1/admin/models/instances", headers=headers, json=inst_payload)
    assert resp.status_code == 201
    iid = resp.json()["id"]

    # Get instance
    resp = client.get(f"/v1/admin/models/instances/{iid}", headers=bearer_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == iid

    # Delete instance
    resp = client.delete(f"/v1/admin/models/instances/{iid}", headers=bearer_headers)
    assert resp.status_code == 204

    # Delete provider
    resp = client.delete(f"/v1/admin/models/providers/prov-test", headers=bearer_headers)
    assert resp.status_code == 204
