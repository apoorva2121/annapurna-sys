"""The guest realm's token. A separate file, because a separate file cannot be imported by accident.

ADR 0009: "Separate auth realms. A guest token can never satisfy a staff dependency, **because they
are different types**." `decode_access_token` already refuses a token whose `typ` is not `access` —
that check exists so a refresh token cannot be presented as an access token. This is the same check,
from the other side, and the symmetry is the whole guarantee:

- a guest token presented to a staff route is refused by `decode_access_token`;
- a staff token presented to a guest route is refused by `decode_guest_token`.

Neither refusal depends on anybody remembering anything.

**What a guest token does not carry.** No `prm` claim — not an empty list, *absent*. A guest token
has no permission vocabulary at all, so there is no string an attacker can add to one that any staff
dependency would recognise. No `org`: the organization is how a chain recognises a diner across
branches and is none of a table's business. No employee id, no name, no phone. A JWT is signed and
not encrypted (`app/core/security.py` says so), so everything in it is public, and the only things
in here are two ids and a scope.

**Two scopes, from two different QR codes** (`docs/modules/M10-customers-spec.md` decision 1):

| Scope | Minted from | Lives | Grants |
|---|---|---|---|
| `table` | the sticker on the table | ~2h (`docs/security.md`) | the guest menu |
| `order` | the QR on the bill | until the order's token expires | that order's bill, one feedback |

A photographed table sticker is therefore worth the menu, which is already on the wall.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

import jwt

from app.core.config import get_settings
from app.core.security import ExpiredTokenError, InvalidTokenError

_ALGORITHM = "HS256"
_GUEST = "guest"

# 128 bits of randomness, hex, no separators. Long enough that guessing one is not a strategy, short
# enough to sit in a QR code that still scans from a table at arm's length.
_SLUG_BYTES = 16


def new_guest_slug() -> str:
    """A table's public id.

    Generated **Python-side**, like `id` and for the same reason ADR 0008 gives: the code that
    creates a table is the code that needs to print its QR, and a server default is not known until
    after the insert. The migration's column default exists only to backfill tables created before
    M10 existed.
    """
    return secrets.token_hex(_SLUG_BYTES)


class GuestScopeKind(StrEnum):
    TABLE = "table"
    ORDER = "order"


@dataclass(frozen=True, slots=True)
class GuestScope:
    """Everything a guest request is allowed to know about itself."""

    restaurant_id: uuid.UUID
    kind: GuestScopeKind
    subject_id: uuid.UUID
    # The first sixteen characters of the order token's stored hash, for an `order` scope only.
    # Not a secret — a prefix of a hash grants nothing — and not an identifier either: it is a
    # *generation*. A reprinted bill hashes a new token, the prefix moves, and every session opened
    # from the old QR is refused at its next request instead of living out its expiry.
    token_fingerprint: str | None = None

    @property
    def table_id(self) -> uuid.UUID | None:
        return self.subject_id if self.kind is GuestScopeKind.TABLE else None

    @property
    def order_id(self) -> uuid.UUID | None:
        return self.subject_id if self.kind is GuestScopeKind.ORDER else None


def issue_guest_token(
    *,
    restaurant_id: uuid.UUID,
    kind: GuestScopeKind,
    subject_id: uuid.UUID,
    expires_in: timedelta,
    token_fingerprint: str | None = None,
) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(subject_id),
        "rst": str(restaurant_id),
        "scp": str(kind),
        "typ": _GUEST,
        "iat": now,
        "exp": now + expires_in,
        "jti": uuid.uuid4().hex,
    }
    if token_fingerprint is not None:
        payload["tkn"] = token_fingerprint
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=_ALGORITHM)


def decode_guest_token(token: str) -> GuestScope:
    """Verify and unpack, or raise. There is no partial success."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[_ALGORITHM],
            options={
                "require": ["exp", "sub", "typ"],
                # The same reasoning as `decode_access_token`: a clock stepped back a second by NTP
                # must not refuse a token minted a moment ago. `exp` is what bounds a token's life.
                "verify_iat": False,
                "enforce_minimum_key_length": True,
            },
        )
    except jwt.ExpiredSignatureError as exc:
        raise ExpiredTokenError("The guest token has expired.") from exc
    except jwt.PyJWTError as exc:
        raise InvalidTokenError("The guest token is not valid.") from exc

    if payload.get("typ") != _GUEST:
        # A staff access token presented to a guest route. Refused here, and the mirror of it is
        # refused in `decode_access_token` — ADR 0009's guarantee, in two places, both structural.
        raise InvalidTokenError("The guest token is not valid.")

    try:
        kind = GuestScopeKind(str(payload.get("scp", "")))
        return GuestScope(
            restaurant_id=uuid.UUID(str(payload.get("rst", ""))),
            kind=kind,
            subject_id=uuid.UUID(str(payload["sub"])),
            token_fingerprint=(None if payload.get("tkn") is None else str(payload["tkn"])),
        )
    except ValueError as exc:
        raise InvalidTokenError("The guest token is not valid.") from exc
