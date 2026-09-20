"""Make the seeded restaurant's figures reachable by the reports, for review on a laptop.

**The problem, found by the owner on 2026-09-19.** They asked for dummy data so they could look at
the Reports tab and give feedback. The data already existed — M15 generates 120 days of trading
with 14 planted signals — and the reports were guaranteed to show none of it, because two
deliberate locks close on each other:

1. `seed/generate.py` writes history **only** into an organization marked `is_demo`, which it calls
   *"a second lock on top of M13's reporting exclusion"*;
2. `ReportingRepository._real_restaurants()` excludes every `is_demo` organization from every
   report.

A test pins it: `test_planted_signals.py` asserts a sales report over generated data returns
exactly `0.00`. **That is the one filter standing between demo figures and a real restaurant's
books, and it must not be weakened.**

The consequence, though, is that **nobody has ever seen a populated report in this product** —
not an owner, not a reviewer, not a developer — and the owner could not give feedback on screens
that only ever render zeros.

**What this does, and why it is safe.** It clears `is_demo` on the seeded organization **after**
everything has been generated. The generator's lock is untouched: by the time this runs, generation
is finished and the organization was demo throughout. M13's exclusion is untouched too — it simply
no longer matches, because the organization is no longer marked demo.

**Two guards, and both are load-bearing:**

- **`ENV` must be local.** Not staging and not production. Staging carries the demo world on
  purpose (`_seed_password` explains why) and production must never hold seeded trading at all.
  There is no override, and adding one should require changing this code and thinking about why.
- **`SEED_REVIEWABLE` must be set explicitly.** A flag somebody types, not a default. The ordinary
  `make seed` is unchanged and still produces a demo organization excluded from every report.

**What it does not guard against, stated plainly:** a local database that somebody has also put
real work into. This clears the flag on *every* demo organization it finds, and a restaurant's
figures and seeded trading would then be counted together. The local rule is the only thing
standing between those, which is another reason it has no override.

**It is deliberately not reversible from here.** Re-marking an organization as demo would hide
trading that reports had already counted, which is the more dangerous direction. Re-seed instead.
"""

from __future__ import annotations

import logging
import os

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.tenancy import Organization

logger = logging.getLogger(__name__)

#: The flag. Named for what it produces — a demo somebody can review — rather than for the column
#: it changes, because the column is an implementation detail and the intent is not.
FLAG = "SEED_REVIEWABLE"


class NotReviewableError(RuntimeError):
    """Asked to make the seed reviewable somewhere it must not be."""


def wanted() -> bool:
    return os.environ.get(FLAG, "").strip().lower() in {"1", "true", "yes"}


async def seed_reviewable(session: AsyncSession) -> int:
    """Clear `is_demo` on the seeded organizations. Returns how many were changed.

    Does nothing at all unless the flag is set, so importing and calling this unconditionally from
    the seeder is safe — the decision lives in one place rather than in a caller's `if`.
    """
    if not wanted():
        return 0

    settings = get_settings()
    if not settings.is_local:
        # The same rule as the seeded password, for the same reason: what is harmless on a laptop
        # is a hole anywhere a real restaurant's data might live. There is no override, and adding
        # one should require changing this code and thinking about why.
        raise NotReviewableError(
            f"{FLAG} is refused outside a local environment. Reports exclude demo organizations so "
            "that seeded trading can never be mistaken for a restaurant's books, and this clears "
            "exactly that flag."
        )

    organizations = (await session.scalars(select(Organization).where(Organization.is_demo))).all()
    if not organizations:
        logger.info("seed.reviewable.nothing_to_do")
        return 0

    await session.execute(
        update(Organization)
        .where(Organization.id.in_([organization.id for organization in organizations]))
        .values(is_demo=False)
    )
    await session.flush()

    logger.warning(
        "%s: cleared is_demo on %d organization(s). Their generated trading now appears in every "
        "report. This database is for review and must not be treated as a restaurant's books.",
        FLAG,
        len(organizations),
    )
    return len(organizations)
