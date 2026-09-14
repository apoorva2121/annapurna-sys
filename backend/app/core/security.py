"""Password hashing and token handling.

Two credentials with opposite storage rules, which is the thing to keep straight when reading this:

- A **password** is hashed with a random per-hash salt, so the same password stored twice produces
  two different rows. It is only ever verified, never looked up.
- A **refresh token** is hashed deterministically (SHA-256, no salt), because the server has to
  *find* the session row by the token the client presents. That is safe here in a way it would not
  be for a password: the token is 256 bits of CSPRNG output, so there is no dictionary to attack.

Neither the raw refresh token nor the password hash ever leaves this process in a response body or
a log line.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error, InvalidHashError

from app.core.config import get_settings

_ALGORITHM = "HS256"
_ACCESS = "access"


class TokenError(Exception):
    """Base for anything wrong with a presented token."""


class InvalidTokenError(TokenError):
    """Malformed, wrongly signed, or the wrong kind of token."""


class ExpiredTokenError(TokenError):
    """Well-formed and correctly signed, but past its expiry."""


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    """What a verified access token asserts. Ids are strings because that is what a JWT carries;
    the caller parses them once, at the boundary."""

    employee_id: str
    organization_id: str
    restaurant_id: str
    permissions: frozenset[str]
    # The session the token was issued for (`sid`, backlog-issues B4). None for a token minted
    # before tokens carried it.
    session_id: str | None = None


def _hasher() -> PasswordHasher:
    settings = get_settings()
    return PasswordHasher(
        time_cost=settings.argon2_time_cost,
        memory_cost=settings.argon2_memory_cost_kib,
        parallelism=settings.argon2_parallelism,
    )


def hash_password(password: str) -> str:
    """Argon2id with a fresh random salt. The returned string carries its own parameters, so
    raising the cost later does not invalidate existing hashes."""
    return _hasher().hash(password)


def verify_password(password: str, stored_hash: str | None) -> bool:
    """False rather than an exception for every failure mode.

    `stored_hash` is None for an invited-but-not-activated account, and can be malformed if a row
    was written by hand. Both must deny the login quietly — raising here would turn a bad password
    into a 500 that a caller retries, and would distinguish "no such account" from "wrong
    password" by response code, which is the enumeration hole this module exists to close.
    """
    if not stored_hash:
        return False
    try:
        return _hasher().verify(stored_hash, password)
    except (Argon2Error, InvalidHashError):
        return False


def hash_refresh_token(raw_token: str) -> str:
    """Deterministic by design — the session row is looked up by this value.

    Unsalted SHA-256 is the right primitive here and the wrong one for passwords: the input is 256
    bits of CSPRNG output, so precomputation has nothing to precompute.
    """
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def new_refresh_token() -> tuple[str, str]:
    """Returns (raw, hashed). The raw value goes to the client once and is never stored; the hash
    is what the database keeps, so a stolen dump yields no live sessions."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_refresh_token(raw)


def issue_access_token(
    employee_id: str,
    organization_id: str,
    restaurant_id: str,
    permissions: list[str],
    session_id: str | None = None,
    expires_in: timedelta | None = None,
    token_type: str = _ACCESS,
) -> str:
    """Claims are abbreviated and impersonal on purpose.

    A JWT is signed, not encrypted: anyone holding it can read every claim. So it carries ids and
    permission strings and nothing else — no name, no email, no phone number.
    """
    settings = get_settings()
    now = datetime.now(UTC)
    lifetime = (
        expires_in
        if expires_in is not None
        else timedelta(minutes=settings.access_token_ttl_minutes)
    )
    payload = {
        "sub": employee_id,
        "org": organization_id,
        "rst": restaurant_id,
        "prm": permissions,
        "typ": token_type,
        "iat": now,
        "exp": now + lifetime,
        # A unique id per token, so a specific one can be denied later without a scheme change.
        "jti": uuid.uuid4().hex,
    }
    if session_id is not None:
        # Which session this token belongs to (remediation R6, backlog-issues B4). A switch
        # continues it rather than inventing one, and a password change spares it without needing
        # the cookie a native client does not send. An id, not a secret: it grants nothing alone.
        payload["sid"] = session_id
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=_ALGORITHM)


def decode_access_token(token: str) -> AccessTokenClaims:
    """Verify and unpack, or raise. There is no partial success.

    `algorithms=[_ALGORITHM]` is what refuses an `alg: none` token — the 2015 attack where an
    attacker strips the signature and the library trusts the header's word for it.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[_ALGORITHM],
            options={
                "require": ["exp", "sub", "typ"],
                # No `iat` check. PyJWT refuses a token whose issued-at is in the future, with
                # no leeway, so a clock stepped back a second by NTP — or two instances a second
                # apart — refuses a token minted a moment ago and signs the person out. `exp` is
                # what bounds a token's life and it stays exact; a leeway would stretch it too.
                # A future `iat` is no attack: a token nobody could sign never gets this far.
                "verify_iat": False,
                # Refuse a key too short to sign safely rather than warning about it. Settings
                # already fails the boot on one; this is the same rule at the second layer.
                "enforce_minimum_key_length": True,
            },
        )
    except jwt.ExpiredSignatureError as exc:
        raise ExpiredTokenError("The access token has expired.") from exc
    except jwt.PyJWTError as exc:
        raise InvalidTokenError("The access token is not valid.") from exc

    if payload.get("typ") != _ACCESS:
        # A refresh token presented as an access token would extend a session far past its
        # intended life, so the type is checked rather than assumed.
        raise InvalidTokenError("The access token is not valid.")

    return AccessTokenClaims(
        employee_id=str(payload["sub"]),
        organization_id=str(payload.get("org", "")),
        restaurant_id=str(payload.get("rst", "")),
        session_id=None if payload.get("sid") is None else str(payload["sid"]),
        permissions=frozenset(payload.get("prm", [])),
    )
