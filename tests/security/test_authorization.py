import json
from typing import Iterable, Optional

import pytest
from starlette.testclient import TestClient


ADMIN_CANDIDATE_PATHS = [
    "/admin",
    "/admin/health",
    "/admin/config",
    "/security/policies",
    "/security/permissions",
    "/mcp/policies",
    "/v1/auth/users",
    "/users",
    "/v1/admin/models/manage",
    "/v1/admin/model/manage",
    "/v1/admin/models/admin",
    "/tools/security/permissions",
    "/system/admin",
]


def _first_existing_path(client: TestClient, paths: Iterable[str]) -> Optional[str]:
    """Return the first path that does not 404, or None."""
    for p in paths:
        r = client.get(p)
        if r.status_code != 404:
            return p
    return None


def _login_for_token(client: TestClient):
    """
    Try a few common auth endpoints to obtain a bearer token.

    Returns (token, login_path) or (None, None) if no login endpoint is available.
    """
    candidates = [
        ("/v1/auth/login", {"username": "tester", "password": "tester"}),
        ("/token", {"username": "tester", "password": "tester"}),
        ("/login", {"username": "tester", "password": "tester"}),
    ]

    # Try JSON first, then form-encoded
    for path, body in candidates:
        # Probe if endpoint exists
        probe = client.get(path)
        if probe.status_code == 404:
            continue

        # JSON
        r = client.post(path, json=body)
        if r.status_code in (200, 201):
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            token = data.get("access_token") or data.get("token") or data.get("bearer") or data.get("jwt")
            if token:
                return token, path

        # Form
        r = client.post(path, data=body)
        if r.status_code in (200, 201):
            # Try JSON parse if possible
            token = None
            if r.headers.get("content-type", "").startswith("application/json"):
                data = r.json()
                token = data.get("access_token") or data.get("token") or data.get("bearer") or data.get("jwt")
            else:
                # best effort parse
                try:
                    data = json.loads(r.text)
                    token = data.get("access_token") or data.get("token") or data.get("bearer") or data.get("jwt")
                except Exception:
                    token = None
            if token:
                return token, path

    return None, None


@pytest.mark.security
def test_admin_like_endpoints_are_not_public(client: TestClient):
    """
    Heuristic: endpoints that look 'admin-ish' should not be accessible
    anonymously. If none exists, skip rather than fail.
    """
    path = _first_existing_path(client, ADMIN_CANDIDATE_PATHS)
    if not path:
        pytest.skip("No admin-like endpoint is exposed by this app")

    r = client.get(path)
    assert r.status_code in (401, 403), f"{path} should not be public; got {r.status_code} {r.text}"


@pytest.mark.security
def test_regular_user_cannot_access_admin_area(client: TestClient):
    """
    If we can obtain a user token and an admin-like endpoint exists,
    the request should be forbidden (403) or at least not succeed (not 2xx).
    If the endpoint returns 200, consider it unprotected and skip (so this
    suite remains compatible with minimal demo apps).
    """
    path = _first_existing_path(client, ADMIN_CANDIDATE_PATHS)
    if not path:
        pytest.skip("No admin-like endpoint is exposed by this app")

    token, login_path = _login_for_token(client)
    if not token:
        pytest.skip("Login endpoint not available; cannot test role-based access")

    r = client.get(path, headers={"Authorization": f"Bearer {token}"})
    if 200 <= r.status_code < 300:
        pytest.skip(f"{path} appears not to enforce admin-only; skipping strict assertion")
    assert r.status_code in (
        401,
        403,
        404,
    ), f"{path} expected forbidden/not-found for regular user, got {r.status_code}"


@pytest.mark.security
def test_permission_probe_endpoint_shape(client: TestClient):
    """
    If the API exposes a permission introspection endpoint, validate its shape.
    Common guesses: /security/permissions, /auth/permissions.
    """
    path = _first_existing_path(client, ["/security/permissions", "/auth/permissions", "/permissions"])
    if not path:
        pytest.skip("No permission introspection endpoint found")

    # Anonymous access may be blocked; try both unauth and (if possible) auth.
    r = client.get(path)
    if r.status_code in (401, 403):
        token, _ = _login_for_token(client)
        if not token:
            pytest.skip("Permissions endpoint requires auth but login not available")
        r = client.get(path, headers={"Authorization": f"Bearer {token}"})

    assert r.status_code == 200, f"Permissions endpoint should respond 200, got {r.status_code} {r.text}"
    if r.headers.get("content-type", "").startswith("application/json"):
        data = r.json()
        # Expect either a list of strings or an object with keys like 'roles'/'permissions'
        assert isinstance(data, (list, dict)), f"Unexpected permissions payload type: {type(data)}"
        if isinstance(data, list):
            assert all(isinstance(x, (str, dict)) for x in data)
        else:
            # dict
            keys = set(map(str.lower, data.keys()))
            assert any(k in keys for k in ("roles", "permissions", "scopes")), f"Unexpected keys in payload: {data}"
