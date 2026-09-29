"""
Security primitives shared by the routers.

- One-time tokens (claims, spot-request responses, alert unsubscribes) are
  random, sent once, and stored only as a SHA-256 hash.
- Parent identity comes from a JWT issued by the auth provider: ES256 or
  RS256 against its published keys, or HS256 with a shared secret.
- Write endpoints are rate limited per client IP.
"""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from functools import lru_cache

import jwt
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from campfinder.config import Settings, get_settings

# ── One-time tokens ────────────────────────────────────────────────────────

def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ── Parent identity ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Identity:
    subject: str
    email: str


_bearer = HTTPBearer(auto_error=False)

# Each algorithm is tied to one kind of key, so a token can't pick a weaker
# check (an HS256 token "signed" with our public key is refused, for example).
ASYMMETRIC_KEY_TYPES = {"ES256": ec.EllipticCurvePublicKey, "RS256": rsa.RSAPublicKey}


@lru_cache(maxsize=4)
def _jwks_client(url: str) -> jwt.PyJWKClient:
    # Keys are cached for five minutes; an unknown key id triggers one refetch,
    # which is how a key rotation at the auth provider reaches us.
    return jwt.PyJWKClient(url, cache_keys=True, lifespan=300, timeout=5)


def _verification_key(token: str, settings: Settings) -> tuple[object, str]:
    header = jwt.get_unverified_header(token)
    alg = header.get("alg")
    if alg in ASYMMETRIC_KEY_TYPES and settings.auth_jwks_url:
        key = _jwks_client(settings.auth_jwks_url).get_signing_key_from_jwt(token).key
        if not isinstance(key, ASYMMETRIC_KEY_TYPES[alg]):
            raise jwt.InvalidAlgorithmError("Token algorithm does not match its key")
        return key, alg
    if alg == "HS256" and settings.auth_jwt_secret:
        return settings.auth_jwt_secret, alg
    raise jwt.InvalidAlgorithmError(f"Algorithm {alg!r} is not accepted")


def current_identity(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> Identity:
    """Verify the bearer JWT and return who is calling. 401 on anything else."""
    if not (settings.auth_jwks_url or settings.auth_jwt_secret):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication is not configured")
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in required")
    token = credentials.credentials
    try:
        key, alg = _verification_key(token, settings)
        claims = jwt.decode(
            token,
            key,
            algorithms=[alg],
            audience=settings.auth_jwt_audience,
            issuer=settings.auth_jwt_issuer or None,
            options={"require": ["sub", "exp"]},
        )
    except jwt.PyJWTError:  # includes key-set fetch failures
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")
    email = claims.get("email")
    if not isinstance(email, str) or "@" not in email:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session has no email")
    return Identity(subject=str(claims["sub"]), email=email.lower())


def mint_token(subject: str, email: str, *, settings: Settings, ttl_seconds: int = 3600) -> str:
    """Issue a JWT the way the auth provider would. Used by tests and local dev."""
    now = int(time.time())
    return jwt.encode(
        {"sub": subject, "email": email, "aud": settings.auth_jwt_audience,
         "iat": now, "exp": now + ttl_seconds},
        settings.auth_jwt_secret,
        algorithm="HS256",
    )


# ── Rate limiting ──────────────────────────────────────────────────────────

class SlidingWindowLimiter:
    """
    In-memory per-key limiter. Good for one API instance; swap the store for
    Redis when there is more than one.
    """

    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            q = self._hits[key]
            cutoff = now - self.window
            while q and q[0] <= cutoff:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


_limiter: SlidingWindowLimiter | None = None


def get_limiter(settings: Settings = Depends(get_settings)) -> SlidingWindowLimiter:
    global _limiter
    if _limiter is None:
        _limiter = SlidingWindowLimiter(settings.rate_limit_per_minute)
    return _limiter


def client_ip(request: Request) -> str:
    # Behind Railway/Vercel the first X-Forwarded-For entry is the client.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limited(request: Request, limiter: SlidingWindowLimiter = Depends(get_limiter)) -> None:
    """Dependency for write endpoints."""
    if not limiter.allow(client_ip(request)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests. Try again in a minute.")
