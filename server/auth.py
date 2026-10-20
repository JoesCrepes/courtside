"""Request authentication.

Two kinds of caller:

- The Android app signs in with Supabase Auth and sends the access token
  (a JWT). We verify it against the project's public signing keys (JWKS), so
  no Supabase secret lives here, and then require the email to be on
  COURTSIDE_ALLOWED_EMAILS. These callers may read and write.
- Scripts and scheduled jobs send COURTSIDE_API_KEY. They may only read.

Both are sent as `Authorization: Bearer <token>`. Everything fails closed:
if a setting is missing, that kind of caller is refused.
"""

from __future__ import annotations

import os
import secrets
import time
from dataclasses import dataclass

import jwt
import requests
from fastapi import HTTPException, Request

JWKS_TTL = 3600
_jwks: dict[str, tuple[float, dict[str, jwt.PyJWK]]] = {}


@dataclass(frozen=True)
class Caller:
    kind: str  # "user" or "key"
    email: str | None = None

    @property
    def can_write(self) -> bool:
        return self.kind == "user"


def _signing_keys(supabase_url: str, refresh: bool = False) -> dict[str, jwt.PyJWK]:
    hit = _jwks.get(supabase_url)
    if hit and not refresh and time.time() - hit[0] < JWKS_TTL:
        return hit[1]
    r = requests.get(f"{supabase_url}/auth/v1/.well-known/jwks.json", timeout=10)
    r.raise_for_status()
    keys = {k["kid"]: jwt.PyJWK(k) for k in r.json().get("keys", []) if "kid" in k}
    _jwks[supabase_url] = (time.time(), keys)
    return keys


def _verify_user(token: str) -> Caller:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    allowed = {e.strip().lower() for e in os.environ.get("COURTSIDE_ALLOWED_EMAILS", "").split(",") if e.strip()}
    if not url or not allowed:
        raise HTTPException(503, "SUPABASE_URL and COURTSIDE_ALLOWED_EMAILS must be configured")
    try:
        kid = jwt.get_unverified_header(token).get("kid")
        keys = _signing_keys(url)
        if kid not in keys:  # Supabase rotated keys since we cached them
            keys = _signing_keys(url, refresh=True)
        key = keys.get(kid)
        if key is None:
            raise HTTPException(401, "token signed with an unknown key")
        claims = jwt.decode(
            token, key, algorithms=["ES256", "RS256"], audience="authenticated", issuer=f"{url}/auth/v1",
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "token expired") from None
    except jwt.InvalidTokenError as e:
        raise HTTPException(401, f"invalid token: {e}") from None
    except requests.RequestException:
        raise HTTPException(503, "could not fetch Supabase signing keys") from None
    email = (claims.get("email") or "").lower()
    if email not in allowed:
        raise HTTPException(403, "this account is not allowed")
    return Caller("user", email)


def caller(request: Request) -> Caller:
    auth = request.headers.get("authorization", "")
    token = auth[len("Bearer "):].strip() if auth.startswith("Bearer ") else ""
    if not token:
        raise HTTPException(401, "missing bearer token")
    # A JWT has three dot-separated parts; an API key has none.
    if token.count(".") == 2:
        return _verify_user(token)
    key = os.environ.get("COURTSIDE_API_KEY")
    if not key:
        raise HTTPException(503, "COURTSIDE_API_KEY is not configured")
    if not secrets.compare_digest(token, key):
        raise HTTPException(401, "bad API key")
    return Caller("key")


def writer(request: Request) -> Caller:
    c = caller(request)
    if not c.can_write:
        raise HTTPException(403, "writes need a signed-in user, not an API key")
    return c
