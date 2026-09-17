"""`python -m app.bootstrap` (R7 step 1): what it creates, and the three things it refuses.

Against real Postgres, because what is under test includes the unique constraint on
`organization.slug` and the nullable `audit_log.actor_employee_id` — neither provable against a
double.
"""

from __future__ import annotations

import argparse

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bootstrap import (
    MissingRoleCatalogueError,
    SlugAlreadyExistsError,
    bootstrap,
)
from app.core.enums import RoleCode
from app.models.access import EmployeeRoleAssignment, Role
from app.models.audit import AuditLog
from app.models.identity import Employee, UserAccount
from app.models.tenancy import Organization, Restaurant


def _args(**overrides: object) -> argparse.Namespace:
    defaults = {
        "org": "Spice Garden Hospitality",
        "slug": "spice-garden",
        "restaurant": "Spice Garden - Koregaon Park",
        "code": "SG_KOREGAON",
        "owner_name": "Rajesh Mehta",
        "owner_email": "owner@example.com",
        "owner_phone": None,
        "owner_code": "EMP001",
        "timezone": "Asia/Kolkata",
        "currency": "INR",
    }
    return argparse.Namespace(**{**defaults, **overrides})


async def test_it_creates_one_organization_one_restaurant_and_one_owner(
    db_session: AsyncSession,
) -> None:
    password = await bootstrap(db_session, _args())
    await db_session.flush()

    organization = await db_session.scalar(
        select(Organization).where(Organization.slug == "spice-garden")
    )
    assert organization is not None
    # Not a demo: the whole point of the flag is that these numbers reach every report.
    assert organization.is_demo is False

    restaurant = await db_session.scalar(
        select(Restaurant).where(Restaurant.organization_id == organization.id)
    )
    assert restaurant is not None
    assert restaurant.code == "SG_KOREGAON"
    assert restaurant.timezone == "Asia/Kolkata"
    # Legal identifiers nobody has supplied yet stay blank rather than being invented.
    assert restaurant.gstin is None
    assert restaurant.fssai_licence is None

    employee = await db_session.scalar(
        select(Employee).where(Employee.organization_id == organization.id)
    )
    assert employee is not None
    assert employee.full_name == "Rajesh Mehta"

    account = await db_session.scalar(
        select(UserAccount).where(UserAccount.organization_id == organization.id)
    )
    assert account is not None
    assert account.email == "owner@example.com"
    # The password is returned for printing, never stored in the clear.
    assert password not in (account.password_hash or "")

    assignment = await db_session.scalar(
        select(EmployeeRoleAssignment).where(EmployeeRoleAssignment.employee_id == employee.id)
    )
    assert assignment is not None
    owner_role = await db_session.scalar(
        select(Role).where(Role.code == RoleCode.OWNER, Role.organization_id.is_(None))
    )
    assert owner_role is not None
    assert assignment.role_id == owner_role.id


async def test_the_generated_password_is_sixteen_characters(db_session: AsyncSession) -> None:
    """R7 names the length. Readable off a terminal onto a phone, not guessable."""
    password = await bootstrap(db_session, _args())
    assert len(password) == 16


async def test_it_writes_an_audit_row_with_no_actor_and_no_password(
    db_session: AsyncSession,
) -> None:
    """Nobody is signed in, and an unattributed row is worth more than no row."""
    password = await bootstrap(db_session, _args())
    await db_session.flush()

    row = await db_session.scalar(
        select(AuditLog).where(AuditLog.action == "organization.bootstrap")
    )
    assert row is not None
    assert row.actor_employee_id is None
    assert row.entity_type == "organization"
    # The password must not be recoverable from the record of its own creation.
    assert password not in str(row.new_value)


async def test_the_owner_joined_on_the_restaurants_local_date(db_session: AsyncSession) -> None:
    """Invariant 4. A container runs UTC; Kiritimati is UTC+14, so the dates differ for 10 hours
    of every day and `date.today()` would silently record the wrong one."""
    args = _args(slug="far-east", code="FE_ONE", timezone="Pacific/Kiritimati")
    await bootstrap(db_session, args)
    await db_session.flush()

    from datetime import datetime
    from zoneinfo import ZoneInfo

    employee = await db_session.scalar(select(Employee).where(Employee.employee_code == "EMP001"))
    assert employee is not None
    assert employee.joined_on == datetime.now(tz=ZoneInfo("Pacific/Kiritimati")).date()


async def test_a_second_bootstrap_with_the_same_slug_is_refused(db_session: AsyncSession) -> None:
    """Not a second organization, and not a new password on the existing one."""
    await bootstrap(db_session, _args())
    await db_session.flush()

    with pytest.raises(SlugAlreadyExistsError, match="already exists"):
        await bootstrap(db_session, _args(code="SG_OTHER"))


async def test_bootstrapping_before_migrating_is_refused(db_session: AsyncSession) -> None:
    """Guessing an owner's permissions here would grant what nobody decided."""
    await db_session.execute(
        delete(Role).where(Role.code == RoleCode.OWNER, Role.organization_id.is_(None))
    )
    await db_session.flush()

    with pytest.raises(MissingRoleCatalogueError, match="alembic upgrade head"):
        await bootstrap(db_session, _args(slug="no-roles", code="NR_ONE"))


# --------------------------------------------------------------------- the CLI layer
# `run()` is what a person actually invokes, and two of its behaviours are load-bearing: the exit
# code a deploy script branches on, and the promise in the module docstring that the password
# reaches stdout and never a log record.


def test_the_parser_requires_the_six_facts_that_cannot_be_guessed() -> None:
    from app.bootstrap import _parser

    args = _parser().parse_args(
        [
            "--org",
            "Spice Garden Hospitality",
            "--slug",
            "spice-garden",
            "--restaurant",
            "Koregaon Park",
            "--code",
            "SG_KP",
            "--owner-name",
            "Rajesh Mehta",
            "--owner-email",
            "owner@example.com",
        ]
    )
    assert args.slug == "spice-garden"
    # Defaults that are safe to assume for an Indian restaurant, and only those.
    assert args.timezone == "Asia/Kolkata"
    assert args.currency == "INR"
    assert args.owner_code == "EMP001"
    assert args.owner_phone is None


def test_the_parser_refuses_to_invent_a_missing_fact() -> None:
    from app.bootstrap import _parser

    with pytest.raises(SystemExit):
        _parser().parse_args(["--org", "Only A Name"])


def test_the_password_is_printed_to_stdout_and_never_logged(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The docstring's promise, asserted. `configure_logging` ships records to stdout too, so a
    password in a log record is a password in whatever collects the logs."""
    import logging

    from app import bootstrap as module

    generated = "PrintedOnceAbc1"  # what _run would hand back

    async def _fake_run(_args: argparse.Namespace) -> str:
        return generated

    monkeypatch.setattr(module, "_run", _fake_run)
    with caplog.at_level(logging.DEBUG):
        code = module.run(
            [
                "--org",
                "Spice Garden",
                "--slug",
                "spice-garden",
                "--restaurant",
                "KP",
                "--code",
                "SG_KP",
                "--owner-name",
                "Rajesh Mehta",
                "--owner-email",
                "owner@example.com",
            ]
        )

    assert code == module.EXIT_OK
    assert generated in capsys.readouterr().out
    assert generated not in caplog.text


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        ("SlugAlreadyExistsError", 2),
        ("MissingRoleCatalogueError", 3),
        ("RestaurantCodeExistsError", 4),
    ],
)
def test_each_refusal_has_its_own_exit_code(
    monkeypatch: pytest.MonkeyPatch, error: str, expected: int
) -> None:
    """Distinct codes, not a traceback: each is a configuration mistake fixable in one step, and a
    stack trace buries the sentence naming which step."""
    from app import bootstrap as module

    async def _fake_run(_args: argparse.Namespace) -> str:
        raise getattr(module, error)("refused")

    monkeypatch.setattr(module, "_run", _fake_run)
    code = module.run(
        [
            "--org",
            "Spice Garden",
            "--slug",
            "spice-garden",
            "--restaurant",
            "KP",
            "--code",
            "SG_KP",
            "--owner-name",
            "Rajesh Mehta",
            "--owner-email",
            "owner@example.com",
        ]
    )
    assert code == expected
