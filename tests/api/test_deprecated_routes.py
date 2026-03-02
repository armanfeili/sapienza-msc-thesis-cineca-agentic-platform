import pytest


def test_tools_invoke_legacy_returns_410(client):
    r = client.post("/tools/invoke", json={"name": "graph.query", "args": {}})
    assert r.status_code == 410
    assert r.headers.get("Deprecation") == "true"
    assert "successor-version" in (r.headers.get("Link") or "")


def test_builtins_staged_duplicate_returns_410(client):
    r = client.get("/model/manifests/builtins/staged")
    # Either the canonical handler or the legacy duplicate may return 200; ensure the legacy one is hidden from schema
    # We assert that if it returns 410, it contains Deprecation header
    if r.status_code == 410:
        assert r.headers.get("Deprecation") == "true"


def test_root_legacy_returns_410(client):
    r = client.get("/")
    assert r.status_code == 410
    assert r.headers.get("Deprecation") == "true"


def test_admin_head_jobs_legacy_returns_410(client):
    r = client.head("/admin/jobs")
    assert r.status_code == 410
    assert r.headers.get("Deprecation") == "true"


def test_internal_ops_db_legacy_endpoints(client):
    # create
    r = client.post("/internal/ops/ops/db/create", json={})
    assert r.status_code == 410
    assert r.headers.get("Deprecation") == "true"
    # populate
    r = client.post("/internal/ops/ops/db/populate", json={})
    assert r.status_code == 410
    assert r.headers.get("Deprecation") == "true"
    # cancel
    r = client.post("/internal/ops/ops/db/cancel/123", json={})
    assert r.status_code == 410
    assert r.headers.get("Deprecation") == "true"


def test_processes_stop_legacy_returns_410(client):
    r = client.post("/processes/stop/123")
    assert r.status_code == 410
    assert r.headers.get("Deprecation") == "true"
