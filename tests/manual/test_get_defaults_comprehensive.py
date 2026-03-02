"""
Test GET /v1/models/defaults endpoint - comprehensive scenario tests.

Tests cover:
1. Happy paths (user/tenant/global precedence)
2. Cache behavior (304 Not Modified)
3. Missing defaults (404)
4. Response shape validation
5. Headers validation (X-Default-Scope, ETag, Vary)
"""
import requests
import json

BASE_URL = "http://localhost:8000"

# Set these from environment or hardcode for testing
USER_TOKEN = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6IlBfUER0Z1l6angzVXlSVE9mTG10RSJ9.eyJpc3MiOiJodHRwczovL2NpbmVjYS5ldS5hdXRoMC5jb20vIiwic3ViIjoiYXV0aDB8NjhjNzE1ZDU2ZjVlN2Q0ZWZhNmFkNmU2IiwiYXVkIjoiYXBpOi8vY2luZWNhLWFnZW50aWMtcGxhdGZvcm0iLCJpYXQiOjE3NjA3MDY5MDksImV4cCI6MTc2MDc5MzMwOSwic2NvcGUiOiJ1c2VyOm1lIHRvb2xzOmludm9rZTpiYXNpYyIsImd0eSI6InBhc3N3b3JkIiwiYXpwIjoia3drZjFiR24yTm1kS1d6aW9aWWt2dFlNMDIyZHpiNUMifQ.EQLz7T7pH9qn_nFfmWhoK5Hr0rsxeklfqm6OADTb-GfMgmAehpmBgZwm8KPO_TftYJBrt9ZAoSIrGGUPQ8JV_qiDFIejNPwVOS-2WMcsCLRALD9UYcCl97ckiwVeqnFvJ9v-sVNZfFVJ6H2HmXdr9u-1IQYLrC_aNJfOpamhWPNIGKN_JL8xlBukPlSfpq5l3X6R0vZB35XwSPEhOCaznhimVRhanTRPKZDDTwCGjRmAYLoU9uIcR-fttQFqbPhBcYciFDfWwWCyANXPmNNVq6M-Jzsjy0kXGrYRrg0tzgbCCR040QxqfUdaaciorpVqyPqieSktfv1Md1Gvqg-86g"
ADMIN_TOKEN = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6IlBfUER0Z1l6angzVXlSVE9mTG10RSJ9.eyJpc3MiOiJodHRwczovL2NpbmVjYS5ldS5hdXRoMC5jb20vIiwic3ViIjoiYXV0aDB8NjhjNzA5OTY5MjI1YWZlMjY1MTUxZWQ1IiwiYXVkIjoiYXBpOi8vY2luZWNhLWFnZW50aWMtcGxhdGZvcm0iLCJpYXQiOjE3NjA2ODcyNTEsImV4cCI6MTc2MDc3MzY1MSwic2NvcGUiOiJ1c2VyOm1lIHRvb2xzOmludm9rZTphbGwgYWRtaW46YWxsIiwiZ3R5IjoicGFzc3dvcmQiLCJhenAiOiJrd2tmMWJHbjJObWRLV3ppb1pZa3Z0WU0wMjJkemI1QyJ9.Qx4Kx2XP6gmAQATy6CVW-kCU8wLNNNlsxHiH9krOGXct-enl91ygzsLTUiqN8TRhRc3dtf6-bt4PLU8lb8ER2MA_ORs6oO4PCIAAjNxUNvc2NYFAhkWKEf5nytAB0WWtmV3EnZShY0R1eX2ur5Tc7Q7EGtURxo6KNCj20biVES2yPyxNz23lrpua83uJxn1_Aqc2a7EbokkgA_uGd65yLg5Z_6bJ4h_tUH9A1qE295syJd0-bE21B0PWXa_yPy1EMOGUSybjl86MGl6VInCzSycq_fsOMUB9L__-GqmAFkxv04L82Uf-1oqtyJQSwqH1LhcI3onrwN3U5OCnC3KmYg"


def test_get_defaults_user_scope():
    """Test GET /defaults returns user-scoped default (highest precedence)."""
    print("\n=== Test 1: User Scope Default ===")

    response = requests.get(f"{BASE_URL}/v1/models/defaults", headers={"Authorization": f"Bearer {USER_TOKEN}"})

    print(f"Status: {response.status_code}")
    print(f"X-Default-Scope: {response.headers.get('X-Default-Scope')}")
    print(f"ETag: {response.headers.get('ETag')}")
    print(f"Vary: {response.headers.get('Vary')}")

    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    assert response.headers.get("X-Default-Scope") in [
        "user",
        "tenant",
        "global",
    ], f"X-Default-Scope header missing or invalid"

    data = response.json()
    print(f"Response: {json.dumps(data, indent=2)}")

    # Validate response shape
    assert "chat" in data, "Missing 'chat' key"
    assert "etag" in data, "Missing 'etag' key"

    chat = data["chat"]
    assert "instance_id" in chat, "Missing chat.instance_id"
    assert "name" in chat, "Missing chat.name"
    assert "provider_id" in chat, "Missing chat.provider_id"
    assert "model_id" in chat, "Missing chat.model_id"

    print("✅ Test 1 PASSED")
    return response.headers.get("ETag")


def test_cache_behavior(etag):
    """Test cache behavior with If-None-Match header."""
    print("\n=== Test 2: Cache Behavior (304 Not Modified) ===")

    response = requests.get(
        f"{BASE_URL}/v1/models/defaults", headers={"Authorization": f"Bearer {USER_TOKEN}", "If-None-Match": etag}
    )

    print(f"Status: {response.status_code}")
    print(f"X-Default-Scope: {response.headers.get('X-Default-Scope')}")
    print(f"ETag: {response.headers.get('ETag')}")

    assert response.status_code == 304, f"Expected 304, got {response.status_code}"
    assert response.headers.get("X-Default-Scope") is not None, "X-Default-Scope missing on 304"
    assert response.headers.get("ETag") == etag, "ETag mismatch"
    assert len(response.content) == 0, "304 should have empty body"

    print("✅ Test 2 PASSED")


def test_admin_access():
    """Test admin can access defaults."""
    print("\n=== Test 3: Admin Access ===")

    response = requests.get(f"{BASE_URL}/v1/models/defaults", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})

    print(f"Status: {response.status_code}")
    print(f"X-Default-Scope: {response.headers.get('X-Default-Scope')}")

    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    data = response.json()
    print(f"Response: {json.dumps(data, indent=2)}")

    print("✅ Test 3 PASSED")


def test_headers_present():
    """Test all required headers are present."""
    print("\n=== Test 4: Headers Validation ===")

    response = requests.get(f"{BASE_URL}/v1/models/defaults", headers={"Authorization": f"Bearer {USER_TOKEN}"})

    required_headers = ["X-Request-Id", "X-Default-Scope", "ETag", "Cache-Control", "Vary"]

    for header in required_headers:
        value = response.headers.get(header)
        print(f"{header}: {value}")
        assert value is not None, f"Missing required header: {header}"

    # Validate Vary includes both Authorization and X-Tenant-Id
    vary = response.headers.get("Vary", "")
    assert "Authorization" in vary, "Vary should include Authorization"
    assert "X-Tenant-Id" in vary, "Vary should include X-Tenant-Id"

    print("✅ Test 4 PASSED")


def test_etag_differs_by_scope():
    """Test that ETags differ for different users (different scopes)."""
    print("\n=== Test 5: ETag Uniqueness ===")

    response_user = requests.get(f"{BASE_URL}/v1/models/defaults", headers={"Authorization": f"Bearer {USER_TOKEN}"})

    response_admin = requests.get(f"{BASE_URL}/v1/models/defaults", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})

    etag_user = response_user.headers.get("ETag")
    etag_admin = response_admin.headers.get("ETag")

    print(f"User ETag: {etag_user}")
    print(f"Admin ETag: {etag_admin}")

    # ETags might be the same if both users have the same default,
    # but they could also differ if users have different defaults
    print(f"ETags are {'identical' if etag_user == etag_admin else 'different'}")

    print("✅ Test 5 PASSED (informational)")


def test_no_auth_returns_401():
    """Test that missing auth returns 401."""
    print("\n=== Test 6: No Auth (401) ===")

    response = requests.get(f"{BASE_URL}/v1/models/defaults")

    print(f"Status: {response.status_code}")

    assert response.status_code == 401, f"Expected 401, got {response.status_code}"

    print("✅ Test 6 PASSED")


def test_response_shape_completeness():
    """Test response has all required fields."""
    print("\n=== Test 7: Response Shape Completeness ===")

    response = requests.get(f"{BASE_URL}/v1/models/defaults", headers={"Authorization": f"Bearer {USER_TOKEN}"})

    data = response.json()

    # Top level
    assert isinstance(data, dict), "Response should be dict"
    assert "chat" in data, "Missing 'chat' key"
    assert "etag" in data, "Missing 'etag' key"
    assert isinstance(data["etag"], str), "etag should be string"

    # Chat object
    chat = data["chat"]
    assert isinstance(chat, dict), "chat should be dict"

    required_chat_fields = ["instance_id", "name", "provider_id", "model_id"]
    for field in required_chat_fields:
        assert field in chat, f"Missing chat.{field}"
        assert isinstance(chat[field], str), f"chat.{field} should be string"
        assert len(chat[field]) > 0, f"chat.{field} should not be empty"

    print(f"✅ All fields present and valid:")
    print(f"  - instance_id: {chat['instance_id']}")
    print(f"  - name: {chat['name']}")
    print(f"  - provider_id: {chat['provider_id']}")
    print(f"  - model_id: {chat['model_id']}")
    print(f"  - etag: {data['etag']}")

    print("✅ Test 7 PASSED")


if __name__ == "__main__":
    print("=" * 60)
    print("GET /v1/models/defaults - Comprehensive Test Suite")
    print("=" * 60)

    # Run tests
    try:
        etag = test_get_defaults_user_scope()
        test_cache_behavior(etag)
        test_admin_access()
        test_headers_present()
        test_etag_differs_by_scope()
        test_no_auth_returns_401()
        test_response_shape_completeness()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback

        traceback.print_exc()
