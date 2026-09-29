"""
Parent sign-in tokens: ES256 against the auth provider's published keys (how
current Supabase projects sign), HS256 with a shared secret (older projects),
and the ways a token can try to get past either.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from campfinder import security
from campfinder.config import Settings

ISSUER = "https://project.supabase.co/auth/v1"
SECRET = "a-shared-secret-long-enough-for-hs256-0123"


class _JWKS(BaseHTTPRequestHandler):
    body: ClassVar[bytes] = b'{"keys": []}'
    fetches: ClassVar[int] = 0

    def log_message(self, *args) -> None:
        pass

    def do_GET(self) -> None:
        type(self).fetches += 1
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(self.body)


def _jwk(private_key: ec.EllipticCurvePrivateKey, kid: str) -> dict:
    data = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(private_key.public_key()))
    return {**data, "kid": kid, "alg": "ES256", "use": "sig"}


@pytest.fixture
def signing_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture
def settings(signing_key: ec.EllipticCurvePrivateKey):
    _JWKS.body = json.dumps({"keys": [_jwk(signing_key, "key-1")]}).encode()
    _JWKS.fetches = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), _JWKS)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    security._jwks_client.cache_clear()
    yield Settings(
        auth_jwks_url=f"http://127.0.0.1:{server.server_address[1]}/auth/v1/.well-known/jwks.json",
        auth_jwt_secret="",
        auth_jwt_audience="authenticated",
        auth_jwt_issuer=ISSUER,
    )
    server.shutdown()
    security._jwks_client.cache_clear()


def _claims(**over) -> dict:
    now = int(time.time())
    return {"sub": "user-1", "email": "Parent@Example.com", "aud": "authenticated",
            "iss": ISSUER, "iat": now, "exp": now + 3600, **over}


def _es256(key: ec.EllipticCurvePrivateKey, kid: str = "key-1", **over) -> str:
    return jwt.encode(_claims(**over), key, algorithm="ES256", headers={"kid": kid})


def _identify(token: str, settings: Settings) -> security.Identity:
    return security.current_identity(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token), settings)


def _refused(token: str, settings: Settings) -> None:
    with pytest.raises(HTTPException) as exc:
        _identify(token, settings)
    assert exc.value.status_code == 401


def test_es256_token_from_the_published_key_is_accepted(signing_key, settings) -> None:
    who = _identify(_es256(signing_key), settings)
    assert who == security.Identity(subject="user-1", email="parent@example.com")


def test_keys_are_cached(signing_key, settings) -> None:
    for _ in range(3):
        _identify(_es256(signing_key), settings)
    assert _JWKS.fetches == 1


def test_rotated_key_is_picked_up(signing_key, settings, monkeypatch: pytest.MonkeyPatch) -> None:
    _identify(_es256(signing_key), settings)
    new_key = ec.generate_private_key(ec.SECP256R1())
    _JWKS.body = json.dumps({"keys": [_jwk(signing_key, "key-1"), _jwk(new_key, "key-2")]}).encode()
    # Newer PyJWT waits out a short cooldown before refetching for an unknown key id;
    # a real rotation arrives long after the last fetch, so move the clock on.
    real_monotonic = time.monotonic
    monkeypatch.setattr(time, "monotonic", lambda: real_monotonic() + 120)
    assert _identify(_es256(new_key, kid="key-2"), settings).subject == "user-1"


def test_token_signed_by_another_key_is_refused(settings) -> None:
    stranger = ec.generate_private_key(ec.SECP256R1())
    _refused(_es256(stranger), settings)            # right kid, wrong signature
    _refused(_es256(stranger, kid="nope"), settings)  # unknown kid


def test_expired_wrong_audience_and_wrong_issuer_are_refused(signing_key, settings) -> None:
    _refused(_es256(signing_key, exp=int(time.time()) - 10), settings)
    _refused(_es256(signing_key, aud="anon"), settings)
    _refused(_es256(signing_key, iss="https://someone-else.supabase.co/auth/v1"), settings)


def test_hs256_token_made_with_the_public_key_is_refused(signing_key, settings) -> None:
    # The classic algorithm-confusion attack: sign HS256 using the public key as the secret.
    public_pem = signing_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    forged = jwt.api_jws.PyJWS().encode(
        json.dumps(_claims()).encode(), key="u" * 40, algorithm="HS256", headers={"kid": "key-1"}
    )
    header, payload, _ = forged.split(".")
    import base64
    import hashlib
    import hmac
    sig = hmac.new(public_pem, f"{header}.{payload}".encode(), hashlib.sha256).digest()
    forged = f"{header}.{payload}.{base64.urlsafe_b64encode(sig).rstrip(b'=').decode()}"
    _refused(forged, settings)


def test_unsigned_and_unexpected_algorithms_are_refused(signing_key, settings) -> None:
    _refused(jwt.encode(_claims(), None, algorithm="none"), settings)
    rs_claimed = _es256(signing_key)
    header = json.loads(jwt.utils.base64url_decode(rs_claimed.split(".")[0]))
    header["alg"] = "RS256"
    swapped = jwt.utils.base64url_encode(json.dumps(header).encode()).decode() + rs_claimed[rs_claimed.index("."):]
    _refused(swapped, settings)


def test_hs256_still_works_when_a_secret_is_set(settings) -> None:
    both = replace(settings, auth_jwt_secret=SECRET, auth_jwt_issuer="")
    token = jwt.encode(_claims(), SECRET, algorithm="HS256")
    assert _identify(token, both).subject == "user-1"
    _refused(jwt.encode(_claims(), "w" * 40, algorithm="HS256"), both)


def test_hs256_is_refused_when_no_secret_is_set(settings) -> None:
    _refused(jwt.encode(_claims(), "a" * 40, algorithm="HS256"), settings)


def test_no_auth_configured_refuses_everything(signing_key) -> None:
    _refused(_es256(signing_key), Settings(auth_jwks_url="", auth_jwt_secret=""))
