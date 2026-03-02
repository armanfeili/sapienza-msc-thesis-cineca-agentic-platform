#!/usr/bin/env python3
"""
Generate a test admin token for smoke testing.
Uses the test OIDC configuration from tests/conftest.py
"""
import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from tests.fixtures.oidc import generate_rsa_keypair, write_jwks, mint_jwt


def main():
    # Generate keypair (same as conftest.py configure_oidc fixture)
    keys = generate_rsa_keypair(kid="test-key-1")

    # Write JWKS file (for app to verify)
    jwks_path = Path("/tmp/test-jwks.json")
    write_jwks(jwks_path, keys["public_jwk"])
    print(f"✓ JWKS written to {jwks_path}")

    # Mint admin token with admin:all scope
    admin_token = mint_jwt(
        keys["private_pem"],
        sub="test-admin",
        issuer="https://test-issuer.local",
        audience="https://api.local",
        scopes=["admin:all"],
        roles=["admin"],
        kid=keys["kid"],
        lifetime_s=86400,  # 24 hours
    )

    print(f"\n✓ Admin token generated:")
    print(f"\nexport ADMIN_TOKEN='{admin_token}'")
    print(f"\nOr run smoke test with:")
    print(f"ADMIN_TOKEN='{admin_token}' ./tests/scripts/smoke_test_model_instances.sh")


if __name__ == "__main__":
    main()
