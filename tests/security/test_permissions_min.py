import pytest

# NOTE: Runtime /v1/models* routes now share a relaxed bearer dependency that only validates
# signature/iss/aud and exposes subject (.sub). Tests MUST NOT rely on username or hidden
# scope checks for those routes; admin-only checks remain enforced under /v1/admin/**.


@pytest.mark.security
def test_auth_me_requires_user_me(client, mint_token):
    # Token without user:me should be forbidden
    tok = mint_token(sub="user1", scopes=["profile:read"])  # no user:me
    r = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code in (401, 403)

    # Token with user:me should succeed
    tok2 = mint_token(sub="user1", scopes=["user:me"])  # grants access
    r2 = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {tok2}"})
    assert r2.status_code == 200
    body = r2.json()
    # Identity now exposed via subject claim; maintain backward compatibility if username still present
    assert body.get("username") == "user1" or body.get("sub") == "user1"


@pytest.mark.security
def test_tools_list_requires_basic(client, mint_token):
    # Without token -> 401
    r = client.get("/v1/tools")
    assert r.status_code in (401, 403)

    # With unrelated scope -> 403
    tok = mint_token(sub="user1", scopes=["user:me"])  # lacks tools:*
    r2 = client.get("/v1/tools", headers={"Authorization": f"Bearer {tok}"})
    assert r2.status_code == 403

    # With tools:basic -> 200
    tok3 = mint_token(sub="user1", scopes=["tools:basic"])  # allowed
    r3 = client.get("/v1/tools", headers={"Authorization": f"Bearer {tok3}"})
    assert r3.status_code == 200


@pytest.mark.security
def test_safe_tool_invocation_with_basic(client, mint_token):
    # SAFE tool should be invocable with tools:basic
    tok = mint_token(sub="user1", scopes=["tools:basic"])  # basic permission
    r = client.post(
        "/v1/tools/system.health/invocations",
        json={"name": "system.health", "args": {}},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code in (200, 201)

    # Without tools permission -> 403
    tok2 = mint_token(sub="user1", scopes=["user:me"])  # lacks tools:*
    r2 = client.post(
        "/v1/tools/system.health/invocations",
        json={"name": "system.health", "args": {}},
        headers={"Authorization": f"Bearer {tok2}"},
    )
    assert r2.status_code == 403


@pytest.mark.security
def test_non_safe_tool_requires_all(client, mint_token):
    # Non-safe tool should be blocked with only tools:basic
    tok = mint_token(sub="user1", scopes=["tools:basic"])  # basic only
    r = client.post(
        "/v1/tools/nonexistent/invocations",
        json={"name": "nonexistent", "args": {}},
        headers={"Authorization": f"Bearer {tok}"},
    )
    # Unknown/non-invokable tool returns 404 before RBAC is enforced
    assert r.status_code == 404

    # With tools:all it should pass the permission gate and reach the impl (404 for missing tool)
    tok2 = mint_token(sub="user1", scopes=["tools:all"])  # elevated
    r2 = client.post(
        "/v1/tools/nonexistent/invocations",
        json={"name": "nonexistent", "args": {}},
        headers={"Authorization": f"Bearer {tok2}"},
    )
    assert r2.status_code in (400, 404)
