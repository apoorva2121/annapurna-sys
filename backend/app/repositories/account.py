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

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identifiers import normalise_identifier
from app.models.identity import Employee, SignInChoice, UserAccount, UserSession
from app.models.tenancy import Organization


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
        normal = normalise_identifier(identifier)
        column = UserAccount.email if "@" in normal else UserAccount.phone
        query = select(UserAccount).where(column == normal).order_by(UserAccount.organization_id)
        return (await self.session.scalars(query)).all()

    async def identifier_taken_in(self, organization_id: uuid.UUID, identifier: str) -> bool:
        """Whether someone in this organization already signs in with this.

        Per organization since backlog-issues B4 (decision D1): another organization may hold the
        same login, because sign-in matches the password first and asks which organization only when
        it opens more than one. The unique constraints are the guarantee; this is the sentence.
        """
        normal = normalise_identifier(identifier)
        column = UserAccount.email if "@" in normal else UserAccount.phone
        found = await self.session.scalar(
            select(UserAccount.id)
            .where(UserAccount.organization_id == organization_id, column == normal)
            .limit(1)
        )
        return found is not None

    async def organizations(self, organization_ids: Sequence[uuid.UUID]) -> Sequence[Organization]:
        """The organizations a sign-in choice offers, by name."""
        query = (
            select(Organization)
            .where(Organization.id.in_(list(organization_ids)))
            .order_by(Organization.name, Organization.id)
        )
        return (await self.session.scalars(query)).all()

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


class SignInChoiceRepository:
    """The two-minute pass (backlog-issues B4). Unscoped: it exists before any organization is
    chosen, and it is found only by the hash of a value the server issued."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def claim(self, token_hash: str) -> SignInChoice | None:
        """Use a pass, in the statement that proves it is unused and unexpired — so two requests
        presenting one pass cannot both sign in."""
        result = await self.session.scalars(
            update(SignInChoice)
            .where(
                SignInChoice.token_hash == token_hash,
                SignInChoice.used_at.is_(None),
                SignInChoice.expires_at > func.now(),
            )
            .values(used_at=func.now())
            .returning(SignInChoice)
        )
        return result.first()
