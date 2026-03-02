import json
from typing import Iterable, Optional, Tuple

import pytest
from starlette.testclient import TestClient


def _first_existing_path(client: TestClient, paths: Iterable[str]) -> Optional[str]:
    """Return the first path that does not 404, or None."""
    for p in paths:
        r = client.get(p)
        if r.status_code != 404:
            return p
    return None


def _login_for_token(client: TestClient) -> Tuple[Optional[str], Optional[str]]:
    """
    Try a few common auth endpoints to obtain a bearer token.

    Returns (token, login_path) or (None, None) if no login endpoint is available.
    """
    candidates = [
        ("/auth/login", {"username": "tester", "password": "tester"}),
        ("/auth/token", {"username": "tester", "password": "tester"}),
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
def test_health_is_public(client: TestClient):
    """Sanity: /health should be accessible without auth."""
    r = client.get("/health")
    assert r.status_code in (200, 204), f"/health expected 200/204, got {r.status_code} {r.text}"


@pytest.mark.security
def test_protected_endpoint_requires_auth(client: TestClient):
    """
    If a 'whoami' endpoint exists, it should require auth.
    We tolerate apps that don't expose it and skip in that case.
    """
    whoami = _first_existing_path(
        client, ["/v1/auth/me", "/v1/auth/whoami", "/auth/me", "/auth/whoami", "/me", "/users/me"]
    )
    if not whoami:
        pytest.skip("No protected 'whoami' endpoint exposed")

    # Unauthenticated request should be rejected
    r = client.get(whoami)
    assert r.status_code in (401, 403), f"{whoami} should require auth, got {r.status_code} {r.text}"


@pytest.mark.security
def test_login_flow_and_access_me(client: TestClient):
    """
    If a login endpoint and a 'whoami' endpoint exist, we should be able
    to obtain a token and access the protected route.
    """
    token, login_path = _login_for_token(client)
    whoami = _first_existing_path(
        client, ["/v1/auth/me", "/v1/auth/whoami", "/auth/me", "/auth/whoami", "/me", "/users/me"]
    )

    if not login_path or not token or not whoami:
        pytest.skip("Login and/or 'whoami' endpoint not available to test full flow")

    r = client.get(whoami, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, f"Authorized request to {whoami} failed: {r.status_code} {r.text}"

    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    # Best-effort assertions on common shape
    assert isinstance(data, dict)
    # Subject-first identity; accept legacy keys for transitional compatibility
    assert any(k in data for k in ("sub", "username", "user", "email")), f"Unexpected whoami payload: {data}"


@pytest.mark.security
def test_invalid_token_is_rejected(client: TestClient):
    """
    A clearly invalid bearer token should be rejected by protected endpoints.
    """
    whoami = _first_existing_path(
        client, ["/v1/auth/me", "/v1/auth/whoami", "/auth/me", "/auth/whoami", "/me", "/users/me"]
    )
    if not whoami:
        pytest.skip("No protected 'whoami' endpoint exposed")

    r = client.get(whoami, headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code in (401, 403), f"Invalid token should be rejected, got {r.status_code} {r.text}"
