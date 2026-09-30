"""Parent sign-in tokens: asymmetric keys from a JWKS, and the legacy shared secret."""

from __future__ import annotations

import dataclasses
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from campfinder import security
from campfinder.config import get_settings

JWKS_URL = "https://example.supabase.co/auth/v1/.well-known/jwks.json"


@pytest.fixture
def signing_key(monkeypatch: pytest.MonkeyPatch) -> ec.EllipticCurvePrivateKey:
    """An ES256 key pair, with its public half served as the provider's JWKS."""
    key = ec.generate_private_key(ec.SECP256R1())
    public = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(key.public_key()))
    public.update(kid="key-1", alg="ES256", use="sig")
    security._jwks_client.cache_clear()
    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", lambda self: {"keys": [public]})
    yield key
    security._jwks_client.cache_clear()


def _es256(key: ec.EllipticCurvePrivateKey, *, kid: str = "key-1", ttl: int = 3600) -> str:
    now = int(time.time())
    claims = {"sub": "auth-user-1", "email": "Parent@Example.com", "aud": "authenticated", "iat": now, "exp": now + ttl}
    return jwt.encode(claims, key, algorithm="ES256", headers={"kid": kid})


def _identify(token: str, **overrides: str) -> security.Identity:
    settings = dataclasses.replace(get_settings(), **overrides)
    return security.current_identity(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token), settings)


def test_es256_token_verified_against_jwks(signing_key: ec.EllipticCurvePrivateKey) -> None:
    identity = _identify(_es256(signing_key), auth_jwks_url=JWKS_URL, auth_jwt_secret="")
    assert identity == security.Identity(subject="auth-user-1", email="parent@example.com")


def test_es256_token_rejected_when_signed_by_another_key(signing_key: ec.EllipticCurvePrivateKey) -> None:
    stranger = ec.generate_private_key(ec.SECP256R1())
    with pytest.raises(HTTPException) as err:
        _identify(_es256(stranger), auth_jwks_url=JWKS_URL, auth_jwt_secret="")
    assert err.value.status_code == 401


def test_expired_es256_token_rejected(signing_key: ec.EllipticCurvePrivateKey) -> None:
    with pytest.raises(HTTPException):
        _identify(_es256(signing_key, ttl=-10), auth_jwks_url=JWKS_URL, auth_jwt_secret="")


def test_hs256_token_rejected_when_only_jwks_is_configured() -> None:
    token = security.mint_token("u", "p@example.com", settings=get_settings())
    with pytest.raises(HTTPException) as err:
        _identify(token, auth_jwks_url=JWKS_URL, auth_jwt_secret="")
    assert err.value.status_code == 401


def test_es256_token_rejected_when_only_secret_is_configured(signing_key: ec.EllipticCurvePrivateKey) -> None:
    with pytest.raises(HTTPException):
        _identify(_es256(signing_key), auth_jwks_url="")


def test_unsigned_token_rejected() -> None:
    token = jwt.encode({"sub": "u", "email": "p@example.com", "aud": "authenticated", "exp": int(time.time()) + 60},
                       key=None, algorithm="none")
    with pytest.raises(HTTPException):
        _identify(token, auth_jwks_url=JWKS_URL)
