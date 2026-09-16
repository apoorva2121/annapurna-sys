"""Minting a guest session from a QR code. The only place either QR becomes a token.

`docs/modules/M10-customers-spec.md` decision 1: two codes, two lifetimes, two powers.

**One refusal for everything.** A slug that does not exist, a slug on a deactivated table, a token
that expired, a token for an order that was voided — all of them answer identically.
`docs/security.md`: "No enumeration: guest lookups return the same response whether or not the
[thing] exists." A guest cannot act on the difference anyway; they scan again or ask a waiter.

**Nothing here is scoped when it starts, and everything is scoped when it ends.** The slug and the
token hash are each globally unique, so each *determines* a restaurant. That is why the two lookups
that read them are the only unscoped queries in the guest realm and live under one heading in
`app/repositories/guest.py`.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.guest_token import GuestScopeKind, issue_guest_token
from app.core.security import hash_refresh_token
from app.models.orders import Order
from app.repositories.guest import order_by_token_hash, table_by_slug
from app.repositories.tenancy import name_of

logger = logging.getLogger(__name__)

# `docs/security.md`: "Table tokens are short-lived (rotating, ~2h) and scoped to one table at one
# restaurant." Long enough for a meal, short enough that a photograph taken at lunch is useless at
# dinner.
TABLE_SESSION_TTL = timedelta(hours=2)

# How long a bill's QR keeps working after the bill is printed. Feedback happens at the table or on
# the way out; `docs/customer-experience.md` puts response rates "an order of magnitude above
# next-day SMS" precisely because of that. A day is generous and still finite.
BILL_TOKEN_TTL = timedelta(hours=24)


def _refused() -> AppError:
    return AppError(
        "guest.session_expired",
        "This code is no longer valid. Please scan the QR code again.",
        status_code=401,
    )


@dataclass(frozen=True, slots=True)
class GuestSession:
    """What a scan is worth: a token, when it dies, what it opens, and the name on the door."""

    token: str
    expires_at: datetime
    scope: str
    restaurant_name: str


class GuestSessionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def from_table_slug(self, slug: str) -> GuestSession:
        """The sticker on the table. Grants the menu and nothing else."""
        table = await table_by_slug(self.session, slug)
        if table is None:
            raise _refused()

        expires_at = datetime.now(UTC) + TABLE_SESSION_TTL
        token = issue_guest_token(
            restaurant_id=table.restaurant_id,
            kind=GuestScopeKind.TABLE,
            subject_id=table.id,
            expires_in=TABLE_SESSION_TTL,
        )
        logger.info("guest.session_opened", extra={"scope": "table"})
        return GuestSession(
            token=token,
            expires_at=expires_at,
            scope=str(GuestScopeKind.TABLE),
            restaurant_name=await name_of(self.session, table.restaurant_id),
        )

    async def from_order_token(self, raw_token: str) -> GuestSession:
        """The QR on the bill. Grants that order's own bill and one feedback submission."""
        token_hash = hash_refresh_token(raw_token)
        order = await order_by_token_hash(self.session, token_hash)
        if order is None or order.guest_token_expires_at is None:
            raise _refused()

        now = datetime.now(UTC)
        if order.guest_token_expires_at <= now:
            raise _refused()

        token = issue_guest_token(
            restaurant_id=order.restaurant_id,
            kind=GuestScopeKind.ORDER,
            subject_id=order.id,
            expires_in=order.guest_token_expires_at - now,
            # The generation, not a secret. A reprinted bill hashes a new token, this moves, and
            # every session opened from the old QR is refused at its next request.
            token_fingerprint=token_hash[:16],
        )
        logger.info("guest.session_opened", extra={"scope": "order"})
        return GuestSession(
            token=token,
            expires_at=order.guest_token_expires_at,
            scope=str(GuestScopeKind.ORDER),
            restaurant_name=await name_of(self.session, order.restaurant_id),
        )

    # ------------------------------------------------------------------ minting the bill's QR

    @staticmethod
    def mint_bill_token(order: Order) -> str:
        """Called from the staff side when a bill is printed. Returns the raw token **once**.

        The raw value is never stored and never readable again — `hash_refresh_token`'s reasoning,
        applied to the second bearer token in this product. A reprint calls this again, which
        replaces the hash, which kills the previous QR and every session opened from it. That is the
        behaviour a restaurant wants: a bill folder left on a cleared table stops being a key.
        """
        raw = secrets.token_urlsafe(24)
        order.guest_token_hash = hash_refresh_token(raw)
        order.guest_token_expires_at = datetime.now(UTC) + BILL_TOKEN_TTL
        return raw
