"""`python -m app.bootstrap` — the first organization on a fresh deployment (R7 step 1).

Not the seeder. `python -m app.seed` builds a demo world from committed YAML with a committed
password and refuses to run outside local; this creates **one real** organization, restaurant and
owner, and is meant to be run exactly once against staging or production.

Everything else a restaurant needs — its floor, stations, tax rates, menu — the owner enters through
M02's setup screens. This command exists only to create the account that can sign in and do that,
because a deployment with no account has no way to make its first one.

Three refusals, each because the alternative is worse than stopping:

* **A slug that already exists.** Re-running with the same slug must not silently make a second
  organization with the same name, nor quietly adopt the existing one and print a password that
  does not work.
* **No role catalogue.** Migrations not run yet. Inventing an owner role here would hand somebody
  permissions nobody granted.
* **A restaurant code already in the organization.** Unreachable while the slug must be new;
  asserted so it stays unreachable if this ever grows a `--reuse-org` flag.

The password is generated here and **printed to stdout once**. It is never logged:
`configure_logging` ships records to stdout too, and a password in a log is a password in whatever
collects the logs.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import secrets
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.enums import EmploymentType, OrganizationPlan, RoleCode, UserAccountStatus
from app.core.identifiers import normalise_identifier
from app.core.logging import configure_logging
from app.core.security import hash_password
from app.models.access import EmployeeRoleAssignment, Role
from app.models.audit import AuditLog
from app.models.identity import Employee, UserAccount
from app.models.tenancy import Organization, Restaurant

logger = logging.getLogger("app.bootstrap")

EXIT_OK = 0
EXIT_SLUG_EXISTS = 2
EXIT_NO_ROLE_CATALOGUE = 3
EXIT_CODE_EXISTS = 4

# 12 random bytes of urlsafe base64 is 16 characters, which is what R7 specifies. Long enough not to
# be guessable, short enough that a person can read it off a terminal onto a phone.
_PASSWORD_BYTES = 12


class SlugAlreadyExistsError(Exception):
    """The organization slug is taken, and bootstrap will not adopt or overwrite it."""


class MissingRoleCatalogueError(Exception):
    """Migrations have not run, so there is no system owner role to grant."""


class RestaurantCodeExistsError(Exception):
    """The branch code is already used inside this organization."""


async def bootstrap(session: AsyncSession, args: argparse.Namespace) -> str:
    """Create the organization, its first restaurant and its owner. Returns the password."""
    if await session.scalar(select(Organization).where(Organization.slug == args.slug)):
        raise SlugAlreadyExistsError(
            f"An organization with slug {args.slug!r} already exists. Bootstrap creates the first "
            "organization and will not add a second with the same slug, nor change the existing "
            "one's owner password. Choose another slug, or reset the password through the app."
        )

    # organization_id IS NULL is the template catalogue seeded by migration 0002.
    owner_role = await session.scalar(
        select(Role).where(Role.code == RoleCode.OWNER, Role.organization_id.is_(None))
    )
    if owner_role is None:
        raise MissingRoleCatalogueError(
            "No system owner role found. Run `alembic upgrade head` before bootstrapping: the role "
            "catalogue is created by a migration, and guessing an owner's permissions here would "
            "grant what nobody decided."
        )

    organization = Organization(
        name=args.org,
        slug=args.slug,
        billing_email=normalise_identifier(args.owner_email),
        plan=OrganizationPlan.TRIAL,
        # The one flag that separates this from `make seed`: these are real numbers and must appear
        # in every report.
        is_demo=False,
    )
    session.add(organization)
    await session.flush()

    if await session.scalar(
        select(Restaurant).where(
            Restaurant.organization_id == organization.id, Restaurant.code == args.code
        )
    ):
        raise RestaurantCodeExistsError(f"{args.code!r} is already a restaurant in {args.slug!r}.")

    # gstin, address and fssai_licence are deliberately absent. They are legal identifiers that
    # print on a bill, and a placeholder is worse than a blank the setup screens still ask for.
    restaurant = Restaurant(
        organization_id=organization.id,
        name=args.restaurant,
        code=args.code,
        timezone=args.timezone,
        currency=args.currency,
        settings={},
    )
    session.add(restaurant)
    await session.flush()

    password = secrets.token_urlsafe(_PASSWORD_BYTES)
    account = UserAccount(
        organization_id=organization.id,
        email=normalise_identifier(args.owner_email),
        phone=None if args.owner_phone is None else normalise_identifier(args.owner_phone),
        password_hash=await hash_password(password),
        # ACTIVE, not INVITED: there is nobody to send an invitation, and this password is handed
        # over out of band by whoever ran the command.
        status=UserAccountStatus.ACTIVE,
    )
    session.add(account)
    await session.flush()

    employee = Employee(
        organization_id=organization.id,
        user_account_id=account.id,
        employee_code=args.owner_code,
        full_name=args.owner_name,
        # Not `date.today()`. The container runs UTC and the restaurant does not: an owner
        # bootstrapped at 03:00 IST would otherwise be recorded as joining the previous day
        # (invariant 4 — display and aggregate in the restaurant's timezone).
        joined_on=datetime.now(tz=ZoneInfo(args.timezone)).date(),
        employment_type=EmploymentType.FULL_TIME,
    )
    session.add(employee)
    await session.flush()

    session.add(
        EmployeeRoleAssignment(
            employee_id=employee.id, restaurant_id=restaurant.id, role_id=owner_role.id
        )
    )

    # No actor. Nobody was signed in — that is the point of the command — and an unattributed row is
    # worth more than no row, which is why `audit_log.actor_employee_id` is nullable.
    session.add(
        AuditLog(
            restaurant_id=restaurant.id,
            actor_employee_id=None,
            action="organization.bootstrap",
            entity_type="organization",
            entity_id=organization.id,
            new_value={
                "slug": args.slug,
                "restaurant_code": args.code,
                "owner_employee_code": args.owner_code,
                # The password is not here, and must never be.
                "owner_email": normalise_identifier(args.owner_email),
            },
        )
    )
    return password


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.bootstrap",
        description="Create the first organization, restaurant and owner on a fresh deployment.",
    )
    parser.add_argument("--org", required=True, help="Legal or trading name of the organization")
    parser.add_argument("--slug", required=True, help="URL-safe unique key, e.g. spice-garden")
    parser.add_argument("--restaurant", required=True, help="This branch's name")
    parser.add_argument("--code", required=True, help="Short branch code, e.g. SG_KOREGAON")
    parser.add_argument("--owner-name", required=True, help="The owner's full name")
    parser.add_argument("--owner-email", required=True, help="The owner's sign-in email")
    parser.add_argument("--owner-phone", default=None, help="Optional second identifier")
    parser.add_argument("--owner-code", default="EMP001", help="Employee code for the owner")
    parser.add_argument("--timezone", default="Asia/Kolkata", help="IANA zone for the restaurant")
    parser.add_argument("--currency", default="INR", help="ISO 4217 code")
    return parser


async def _run(args: argparse.Namespace) -> str:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            password = await bootstrap(session, args)
            # One transaction. A failure anywhere above leaves no half-built organization.
            await session.commit()
            return password
    finally:
        await engine.dispose()


def run(argv: list[str] | None = None) -> int:
    configure_logging()
    args = _parser().parse_args(argv)
    try:
        password = asyncio.run(_run(args))
    except SlugAlreadyExistsError as exc:
        logger.error("%s", exc)
        return EXIT_SLUG_EXISTS
    except MissingRoleCatalogueError as exc:
        logger.error("%s", exc)
        return EXIT_NO_ROLE_CATALOGUE
    except RestaurantCodeExistsError as exc:
        logger.error("%s", exc)
        return EXIT_CODE_EXISTS

    logger.info("Bootstrapped %r with restaurant %r.", args.slug, args.code)
    # print, not logger: see the module docstring. Shown once and never recoverable.
    print("\n" + "=" * 68)
    print(f"  Owner sign-in : {normalise_identifier(args.owner_email)}")
    print(f"  Password      : {password}")
    print("=" * 68)
    print("  Shown once. Store it in a password manager, then change it after first sign-in.")
    print("  It is not in the logs and not in the audit row, so it cannot be recovered.\n")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(run())
