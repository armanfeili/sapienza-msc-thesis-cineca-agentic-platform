"""
OIDC/JWT testing utilities.

Provides helpers to generate an RSA keypair, expose a JWKS, and mint RS256 JWTs
compatible with the app's OIDC validator. Intended for unit/integration tests.
"""

from __future__ import annotations

import base64
import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from jose import jwt
from jose.utils import base64url_encode
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization


def _b64u_int(i: int) -> str:
    length = (i.bit_length() + 7) // 8
    return base64url_encode(i.to_bytes(length, byteorder="big")).decode()


def generate_rsa_keypair(kid: Optional[str] = None) -> Dict[str, Any]:
    """Generate RSA keypair returning PEM private key and public JWK with kid."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub = key.public_key().public_numbers()

    kid = kid or uuid.uuid4().hex
    public_jwk = {
        "kty": "RSA",
        "n": _b64u_int(pub.n),
        "e": _b64u_int(pub.e),
        "alg": "RS256",
        "use": "sig",
        "kid": kid,
    }
    return {"private_pem": private_pem, "public_jwk": public_jwk, "kid": kid}


def write_jwks(path: Path, *public_jwks: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump({"keys": list(public_jwks)}, f)


def mint_jwt(
    private_pem: bytes,
    *,
    sub: str,
    issuer: str,
    audience: str,
    scopes: Optional[List[str]] = None,
    roles: Optional[List[str]] = None,
    lifetime_s: int = 3600,
    extra: Optional[Dict[str, Any]] = None,
    kid: Optional[str] = None,
) -> str:
    now = int(time.time())
    claims: Dict[str, Any] = {
        "iss": issuer,
        "aud": audience,
        "sub": sub,
        "iat": now,
        "nbf": now - 5,
        "exp": now + int(lifetime_s),
    }
    if scopes:
        claims["scope"] = " ".join(scopes)
    if roles:
        claims["roles"] = roles
    if extra:
        claims.update(extra)

    headers = {"kid": kid, "alg": "RS256", "typ": "JWT"}
    token = jwt.encode(claims, private_pem, algorithm="RS256", headers=headers)
    return token
