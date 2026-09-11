"""Credential lookups and session rows.

This repository is the one exception to "every repository takes a TenantScope": at login there is
no scope yet — resolving the identifier is what produces it. The organization is therefore passed
explicitly on every call, so the absence of a scope is visible in each signature rather than being
a quiet default.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import Employee, UserAccount, UserSession


class UserAccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_all_by_identifier(self, identifier: str) -> Sequence[UserAccount]:
        """Every account matching an email or phone, across all organizations.

        Global on purpose, and it is the *only* honest scope for this question. The login form asks
        for an identifier and not a tenant, so resolution has to search everywhere — which means
        two tenants holding the same identifier is an ambiguity the product cannot resolve, and
        therefore something creation has to prevent.

        Returning every match rather than the first is what lets both callers do their job: login
        refuses an ambiguous match, and creating a login refuses to *become* one. An earlier
        org-scoped version of this method looked safer and was the reason a tenant could take an
        identifier belonging to another and lock its owner out permanently.
        """
        normalised = identifier.strip().lower()
        query = select(UserAccount).where(
            or_(UserAccount.email == normalised, UserAccount.phone == identifier.strip())
        )
        return (await self.session.scalars(query)).all()

    async def identifier_is_taken(self, identifier: str) -> bool:
        """Whether anyone, anywhere, already signs in with this. Never says who — that would make
        the staff form an oracle for which addresses exist in other tenants."""
        return bool(await self.find_all_by_identifier(identifier))

    async def get(self, account_id: uuid.UUID) -> UserAccount | None:
        return await self.session.get(UserAccount, account_id)

    async def employee_for(self, account_id: uuid.UUID) -> Employee | None:
        """The person behind a login, before any scope exists.

        Unscoped for the same reason the identifier lookup is: this runs *during* login, and the
        organization is not known until it returns. `EmployeeRepository` cannot answer it — that
        class refuses to be constructed without a `TenantScope`, which is the structural guarantee
        we want everywhere else and exactly what cannot hold here.

        Safe because the account id is not client input: it came from an identifier lookup that has
        already matched a password.
        """
        result = await self.session.scalars(
            select(Employee).where(Employee.user_account_id == account_id)
        )
        return result.first()


class UserSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_live_by_hash(self, token_hash: str) -> UserSession | None:
        """Live means: not revoked and not expired. Both are checked in SQL rather than in Python,
        so there is no window where a caller forgets one of them."""
        query = select(UserSession).where(
            UserSession.refresh_token_hash == token_hash,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > datetime.now(UTC),
        )
        return (await self.session.scalars(query)).first()

    async def claim_for_rotation(self, token_hash: str) -> UserSession | None:
        """Atomically retire a live session and hand it back, or return None.

        **One statement, not a read then a write.** `find_live_by_hash` followed by setting
        `revoked_at` leaves a window: two refreshes presenting the same token both pass the liveness
        check, both mint a new session, and the family-based theft detection this table exists for
        is silently defeated — the two new rows have different hashes, so the unique index does not
        catch it either. A stolen token was supposed to be worth one use at most; read-then-write
        made it worth as many as fit in the window.

        `UPDATE … WHERE revoked_at IS NULL … RETURNING` makes the claim and the proof the same
        operation, so exactly one caller wins and the loser is handled as a replay.

        Found by external review, 2026-09-11.
        """
        result = await self.session.execute(
            update(UserSession)
            .where(
                UserSession.refresh_token_hash == token_hash,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > datetime.now(UTC),
            )
            .values(revoked_at=datetime.now(UTC))
            .returning(UserSession)
        )
        return result.scalars().first()

    async def find_live_by_hash_for_account(
        self, token_hash: str, account_id: uuid.UUID
    ) -> UserSession | None:
        """A live session that belongs to a named account.

        The account filter is in SQL rather than at the call site so it cannot be forgotten: the
        refresh cookie and the access token are two independent inputs, and a caller presenting
        their own token with someone else's cookie must not be able to write to that person's row.
        """
        query = select(UserSession).where(
            UserSession.refresh_token_hash == token_hash,
            UserSession.user_account_id == account_id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > datetime.now(UTC),
        )
        return (await self.session.scalars(query)).first()

    async def find_any_by_hash(self, token_hash: str) -> UserSession | None:
        """Deliberately includes revoked rows: presenting an already-rotated token is the signal
        that a refresh token was stolen, and it can only be detected by finding the dead row."""
        query = select(UserSession).where(UserSession.refresh_token_hash == token_hash)
        return (await self.session.scalars(query)).first()

    async def revoke_family(self, family_id: uuid.UUID) -> int:
        """Kill every session descended from one login. Used when a rotated token is replayed."""
        result = cast(
            "CursorResult[Any]",
            await self.session.execute(
                update(UserSession)
                .where(UserSession.family_id == family_id, UserSession.revoked_at.is_(None))
                .values(revoked_at=datetime.now(UTC))
            ),
        )
        return result.rowcount

    async def revoke_all_for_account(
        self, user_account_id: uuid.UUID, *, except_session_id: uuid.UUID | None = None
    ) -> int:
        """Every live session for one person, in a single statement.

        One statement rather than a read-then-write loop because this runs on deactivation, and
        "revokes every session immediately" (acceptance criterion 4) must not have a window in
        which a session created mid-loop survives.
        """
        query = update(UserSession).where(
            UserSession.user_account_id == user_account_id,
            UserSession.revoked_at.is_(None),
        )
        if except_session_id is not None:
            query = query.where(UserSession.id != except_session_id)
        result = cast(
            "CursorResult[Any]",
            await self.session.execute(query.values(revoked_at=datetime.now(UTC))),
        )
        return result.rowcount
