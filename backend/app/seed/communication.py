"""A few conversations, so M11's screens have something in them.

**M11 shipped complete, tested, and with nothing to look at.** There was no communication seeder,
so `make seed` produced a restaurant where Messages was empty for everyone. The owner opened it on
2026-09-19 and said so: *"Same in message, i dont see any sample data."* It is the same gap as
M13's reports and M17's performance — a module is not finished when its tests pass, it is finished
when somebody can open it.

**The threads are the ones the module was built for**, not filler: a shift handover, a piece of
equipment that has failed, and a manager telling the floor something. If a demonstration needs a
thread of a kind the product cannot create, that is a finding rather than a seeding problem.

**No attachment is seeded, and that is a gap worth naming rather than hiding.** Every attachment
in the product returned `auth.required` when opened, from M11 until 2026-09-19, and nobody saw it
because no seeded thread had a file on one — the defect was reachable only by uploading by hand. A
seeded attachment would have caught it on the first manual pass rather than the sixth. It is not
here because an attachment needs bytes in object storage, which a seeder that must run identically
on a laptop and in CI should not be inventing. **Worth doing when the storage seam is next
touched.**

**It calls the service rather than inserting rows.** `create` owns the direct-thread dedupe and the
"that kind is created by the thing it belongs to" refusal; `send` owns the empty-message refusal
and the revision counter the stream depends on. A seeder writing its own rows would be a second
implementation of both, and would cheerfully seed a thread the application would reject.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.enums import ConversationType, MessagePriority
from app.core.tenancy import TenantScope
from app.models.access import EmployeeRoleAssignment, Role
from app.models.communication import Conversation, Message
from app.models.identity import Employee
from app.models.tenancy import Restaurant
from app.services.conversations import ConversationService

logger = logging.getLogger(__name__)

_FOR_RESTAURANT = "SG_KOREGAON"


@dataclass(frozen=True, slots=True)
class CommunicationSummary:
    conversations_created: int = 0
    messages_created: int = 0

    @property
    def created_nothing(self) -> bool:
        return not (self.conversations_created or self.messages_created)


@dataclass(frozen=True, slots=True)
class _Thread:
    """One seeded conversation: a title, who is in it, and what was said.

    `said` is (how many hours ago, who said it by index into `members`, the words). Hours rather
    than dates so the list has a believable order however long ago the seed was run — a thread
    whose newest message is four months old reads as a dead restaurant.
    """

    title: str
    said: tuple[tuple[int, int, str], ...]


_THREADS: tuple[_Thread, ...] = (
    _Thread(
        title="Evening handover",
        said=(
            (
                20,
                0,
                "Table 7 asked for the bill twice. The garden needs more cover after nine.",
            ),
            (19, 1, "Noted. Two on the garden from Friday, and we will see if it settles."),
            (18, 0, "Also the paneer ran low around ten. Kitchen managed but it was close."),
        ),
    ),
    _Thread(
        title="Walk-in freezer — door seal",
        said=(
            (
                30,
                1,
                "The walk-in door is not sealing. Ice building along the bottom edge.",
            ),
            (29, 0, "How bad? Is anything at risk tonight?"),
            (
                28,
                1,
                "Nothing at risk yet, it holds temperature. Needs looking at this week though.",
            ),
            (
                4,
                0,
                "Engineer comes Thursday morning. Keep it shut as much as you can until then.",
            ),
        ),
    ),
    _Thread(
        title="Sunday — full covers from seven",
        said=(
            (
                10,
                0,
                "Fully booked from seven on Sunday. Everyone in by half six, prep done before.",
            ),
            (
                9,
                1,
                "Understood. Gravies done Saturday night, so Sunday is plating only.",
            ),
        ),
    ),
)


async def _people(session: AsyncSession, restaurant: Restaurant, limit: int) -> list[Employee]:
    """Employees here, most senior first.

    Seniority by `Role.rank`, never by a role's code (ADR 0007) — the rule holds in a seeder too.
    Most senior first so the manager is `members[0]` and speaks first in a handover, which is how
    these threads actually start.
    """
    rows = await session.scalars(
        select(Employee)
        .join(EmployeeRoleAssignment, EmployeeRoleAssignment.employee_id == Employee.id)
        .join(Role, Role.id == EmployeeRoleAssignment.role_id)
        .where(
            EmployeeRoleAssignment.restaurant_id == restaurant.id,
            Employee.is_active.is_(True),
        )
        .order_by(Role.rank, Employee.employee_code)
        .limit(limit)
    )
    seen: dict[str, Employee] = {}
    for employee in rows:
        seen.setdefault(str(employee.id), employee)
    return list(seen.values())


async def seed_communication(session: AsyncSession) -> CommunicationSummary:
    """Create the sample threads. Safe to run repeatedly."""
    restaurant = await session.scalar(select(Restaurant).where(Restaurant.code == _FOR_RESTAURANT))
    if restaurant is None:
        return CommunicationSummary()

    # Get-or-create by *the restaurant having any thread at all*, rather than by title: a title is
    # the one thing on a conversation a person is free to change, so keying on it would seed a
    # second copy the moment somebody renamed one.
    existing = await session.scalar(
        select(func.count(Conversation.id)).where(Conversation.restaurant_id == restaurant.id)
    )
    if existing:
        return CommunicationSummary()

    members = await _people(session, restaurant, limit=4)
    if len(members) < 2:
        # A conversation needs somebody to have it with.
        return CommunicationSummary()

    scope = TenantScope(organization_id=restaurant.organization_id, restaurant_id=restaurant.id)
    conversations_created = 0
    messages_created = 0
    now = datetime.now(UTC)

    for thread in _THREADS:
        author = members[0]
        service = ConversationService(session, scope)
        conversation, _existed = await service.create(
            _actor(author, restaurant),
            type_=ConversationType.GROUP,
            title=thread.title,
            participant_ids=[member.id for member in members[1:]],
        )
        conversations_created += 1

        for hours_ago, speaker, words in thread.said:
            speaking = members[speaker % len(members)]
            message = await service.send(
                _actor(speaking, restaurant),
                conversation_id=conversation.id,
                body=words,
                priority=MessagePriority.NORMAL,
                reply_to_message_id=None,
            )
            # Backdated after the fact: `send` stamps "now", which is right for the application and
            # would give three months of trading a message list all posted in the same second.
            said_at = now - timedelta(hours=hours_ago)
            message.created_at = said_at
            conversation.last_message_at = said_at
            messages_created += 1

    await session.flush()
    summary = CommunicationSummary(
        conversations_created=conversations_created, messages_created=messages_created
    )
    logger.info("seed.communication.complete", extra={"summary": summary})
    return summary


def _actor(employee: Employee, restaurant: Restaurant) -> Actor:
    """A seeded speaker.

    Permissions are empty because the seeder is calling the service for its *rules* — the dedupe,
    the refusals, the revision counter — and not to check its own authority. `message.send` is on
    every role in the catalogue anyway (M11 granted it deliberately: the person who finds the
    broken freezer at 6am is exactly the person with no other permissions).
    """
    return Actor(
        employee_id=employee.id,
        organization_id=restaurant.organization_id,
        restaurant_id=restaurant.id,
        full_name=employee.full_name,
        permissions=frozenset(),
        rank=0,
    )


__all__ = ["CommunicationSummary", "Message", "seed_communication"]
