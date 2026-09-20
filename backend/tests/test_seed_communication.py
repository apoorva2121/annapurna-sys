"""M11's sample threads, which did not exist until 2026-09-20.

The owner opened Messages during their screen-by-screen pass and found it empty: *"Same in message,
i dont see any sample data."* There was no communication seeder at all — M11 shipped complete,
tested, and with nothing for a person to look at. The same gap as M13's reports and M17's
performance, three times in one week.

These tests exist because a seeder is easy to verify wrongly. Running it against the local database
proved nothing the first time: conversations were already there from hand testing, the get-or-create
guard skipped correctly, and the log said *"Seed data already present; nothing to do."* A clean
database is the only place the question can be answered.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.communication import Conversation, ConversationParticipant, Message
from app.models.tenancy import Restaurant
from app.seed.communication import seed_communication
from app.seed.identity import seed_identity
from app.seed.setup import seed_setup


async def _seed(session: AsyncSession) -> None:
    await seed_identity(session)
    await seed_setup(session)
    await seed_communication(session)
    await session.flush()


async def _koregaon(session: AsyncSession) -> Restaurant:
    restaurant = await session.scalar(select(Restaurant).where(Restaurant.code == "SG_KOREGAON"))
    assert restaurant is not None
    return restaurant


class TestTheSeededThreads:
    async def test_messages_is_not_empty_for_somebody_opening_it(
        self, db_session: AsyncSession
    ) -> None:
        """The whole point. Before this seeder the screen was blank in every environment."""
        await _seed(db_session)
        restaurant = await _koregaon(db_session)

        conversations = await db_session.scalar(
            select(func.count(Conversation.id)).where(Conversation.restaurant_id == restaurant.id)
        )
        messages = await db_session.scalar(
            select(func.count(Message.id)).where(Message.restaurant_id == restaurant.id)
        )

        assert conversations == 3
        assert messages == 9

    async def test_every_thread_has_more_than_one_voice(self, db_session: AsyncSession) -> None:
        """A handover with one speaker is a note to self, and demonstrates nothing about a module
        whose subject is people talking to each other."""
        await _seed(db_session)
        restaurant = await _koregaon(db_session)

        rows = (
            await db_session.execute(
                select(
                    Message.conversation_id, func.count(func.distinct(Message.sender_employee_id))
                )
                .where(Message.restaurant_id == restaurant.id)
                .group_by(Message.conversation_id)
            )
        ).all()

        assert rows, "no threads were seeded — this test would otherwise pass vacuously"
        for conversation_id, speakers in rows:
            assert speakers >= 2, f"{conversation_id!s} has only one voice in it"

    async def test_the_messages_are_spread_over_time_rather_than_one_instant(
        self, db_session: AsyncSession
    ) -> None:
        """`send` stamps "now", which is right for the application and wrong for a seed: three
        months of trading beside a message list all posted in the same second reads as fake."""
        await _seed(db_session)
        restaurant = await _koregaon(db_session)

        stamps = (
            await db_session.scalars(
                select(Message.created_at).where(Message.restaurant_id == restaurant.id)
            )
        ).all()

        assert len(set(stamps)) > 1, "every message was posted at the same moment"

    async def test_everybody_in_a_thread_is_a_participant(self, db_session: AsyncSession) -> None:
        """Membership is what the unread counts and the stream are built on, so a seeded thread
        somebody speaks in but does not belong to would be a broken demonstration."""
        await _seed(db_session)
        restaurant = await _koregaon(db_session)

        senders = set(
            (
                await db_session.scalars(
                    select(Message.sender_employee_id).where(Message.restaurant_id == restaurant.id)
                )
            ).all()
        )
        members = set(
            (
                await db_session.scalars(
                    select(ConversationParticipant.employee_id).where(
                        ConversationParticipant.restaurant_id == restaurant.id
                    )
                )
            ).all()
        )

        assert senders, "nobody spoke"
        assert senders <= members, "somebody spoke in a thread they are not in"

    async def test_seeding_twice_does_not_produce_a_second_copy(
        self, db_session: AsyncSession
    ) -> None:
        """`make seed` is run casually and repeatedly. The failure to design against is not a
        crash, it is six conversations where there should be three."""
        await _seed(db_session)
        restaurant = await _koregaon(db_session)
        first = await db_session.scalar(
            select(func.count(Conversation.id)).where(Conversation.restaurant_id == restaurant.id)
        )

        summary = await seed_communication(db_session)
        await db_session.flush()
        again = await db_session.scalar(
            select(func.count(Conversation.id)).where(Conversation.restaurant_id == restaurant.id)
        )

        assert summary.created_nothing
        assert again == first
