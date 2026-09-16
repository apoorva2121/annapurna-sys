"""Queries over the kitchen. Business rules live in the service, not here.

Four of these carry weight.

**`routing_for` is one query, not one per dish.** A send needs each line's station and its standard
prep time, which live two joins away on `menu_item` and `menu_item_variant`. Asked per line, a
six-dish order would be twelve queries on the hot path of the busiest screen in the restaurant.

**`next_ticket_number` takes the same transaction-scoped advisory lock `next_order_number` does**,
per restaurant and business day. Two waiters sending in the same second must not both be ticket 12.

**`bump_revision` is `UPDATE … RETURNING` on one row per restaurant**, and it is called once per
transaction rather than once per ticket. A send that creates three tickets is one kitchen event, so
all three carry one revision — which is why the stream replays *inclusively* from a client's
cursor (`docs/modules/M08-kitchen-spec.md` decision 3).

**`rail` is the only query in this module with a latency budget** — 50 ms with 200 open tickets —
so it loads its lines in one extra statement rather than one per ticket, and it is the query
`ix_kot_ticket_rail` exists for.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import Integer, Select, cast, func, literal, select, update
from sqlalchemy.orm import selectinload

from app.core.enums import KotTicketStatus
from app.models.kitchen import KotStreamCursor, KotTicket, KotTicketLine
from app.models.menu import MenuItem, MenuItemVariant, Modifier
from app.models.orders import Order, OrderLine, OrderLineModifier, OrderTable
from app.repositories.base import RestaurantScopedRepository, page_size

# A namespace of its own, so a ticket-number lock never collides with an order-number lock taken in
# the same transaction by the same send.
_TICKET_NUMBER_LOCK_NAMESPACE = 0x4B4F_5401

# The rail shows work. A served or cancelled ticket has left it.
OPEN_STATUSES = (
    KotTicketStatus.NEW,
    KotTicketStatus.ACKNOWLEDGED,
    KotTicketStatus.PREPARING,
    KotTicketStatus.READY,
)


@dataclass(frozen=True, slots=True)
class LineRouting:
    """Everything a ticket line needs, resolved once at the send.

    Names travel with it because the ticket keeps them: a KOT is a printed instruction and must
    still read correctly after the dish is renamed or withdrawn.
    """

    order_line_id: uuid.UUID
    station_id: uuid.UUID
    prep_minutes: int
    quantity: int
    seq: int
    item_name: str
    variant_name: str
    special_instructions: str | None
    modifier_summary: str | None


class KitchenRepository(RestaurantScopedRepository[KotTicket]):
    model = KotTicket

    # ------------------------------------------------------------------ routing

    async def routing_for(self, line_ids: Sequence[uuid.UUID]) -> list[LineRouting]:
        """Station, standard prep time and the words to print, for every line, in two statements.

        Two rather than one: joining the modifiers in would multiply every line by its options and
        need de-duplicating in Python, which is more code and more rows than asking twice. Two is
        also two regardless of how many dishes were sent — the property that matters, and the one
        the query-count assertion holds.

        Scoped on `order_line`, so a line id belonging to another restaurant selects nothing rather
        than routing a dish onto this restaurant's rail.
        """
        if not line_ids:
            return []
        rows = await self.session.execute(
            select(
                OrderLine.id,
                MenuItem.station_id,
                MenuItemVariant.prep_minutes,
                OrderLine.quantity,
                OrderLine.seq,
                MenuItem.name,
                MenuItemVariant.name,
                OrderLine.special_instructions,
            )
            .join(MenuItemVariant, MenuItemVariant.id == OrderLine.menu_item_variant_id)
            .join(MenuItem, MenuItem.id == MenuItemVariant.menu_item_id)
            .where(
                OrderLine.restaurant_id == self.scope.restaurant_id,
                OrderLine.id.in_(line_ids),
            )
            .order_by(OrderLine.seq)
        )
        options = await self._modifier_names(line_ids)
        return [
            LineRouting(
                order_line_id=row[0],
                station_id=row[1],
                prep_minutes=row[2],
                quantity=row[3],
                seq=row[4],
                item_name=row[5],
                variant_name=row[6],
                special_instructions=row[7],
                modifier_summary=options.get(row[0]),
            )
            for row in rows
        ]

    async def _modifier_names(self, line_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, str]:
        """ "No onion, Extra spicy" per line — the half of a ticket that gets a dish sent back when
        it is missed."""
        rows = await self.session.execute(
            select(OrderLineModifier.order_line_id, Modifier.name)
            .join(Modifier, Modifier.id == OrderLineModifier.modifier_id)
            .where(
                OrderLineModifier.restaurant_id == self.scope.restaurant_id,
                OrderLineModifier.order_line_id.in_(line_ids),
            )
            .order_by(OrderLineModifier.order_line_id, Modifier.name)
        )
        names: dict[uuid.UUID, list[str]] = {}
        for line_id, name in rows:
            names.setdefault(line_id, []).append(name)
        return {line_id: ", ".join(found) for line_id, found in names.items()}

    # ------------------------------------------------------------------ numbering and rounds

    async def next_ticket_number(self, business_date: date) -> str:
        """The next ticket number for this business day, allocated under a lock held to commit.

        Restarts every business day for the same reason `order_number` does: a number that never
        resets is not something anybody calls across a kitchen.
        """
        key = f"{self.scope.restaurant_id}:{business_date.isoformat()}"
        await self.session.execute(
            select(
                func.pg_advisory_xact_lock(
                    literal(_TICKET_NUMBER_LOCK_NAMESPACE), func.hashtext(key)
                )
            )
        )
        highest = await self.session.scalar(
            self.scoped()
            .with_only_columns(func.max(cast(KotTicket.ticket_number, Integer)))
            .where(KotTicket.business_date == business_date)
        )
        return str((highest or 0) + 1)

    async def rounds_so_far(self, order_id: uuid.UUID) -> dict[uuid.UUID, int]:
        """How many rounds each station has already had for this order.

        The next ticket for a station is the one after its highest, which is what
        `uq_kot_ticket_round` holds the database to.
        """
        rows = await self.session.execute(
            select(KotTicket.station_id, func.max(KotTicket.sequence_in_order))
            .where(
                KotTicket.restaurant_id == self.scope.restaurant_id,
                KotTicket.order_id == order_id,
            )
            .group_by(KotTicket.station_id)
        )
        return {station_id: int(highest) for station_id, highest in rows.all()}

    # ------------------------------------------------------------------ the cursor

    async def bump_revision(self) -> int:
        """The restaurant's next kitchen revision, allocated and returned in one statement.

        The row is created on demand: a restaurant that has never sent a ticket has no cursor, and
        making one at migration time would mean backfilling every restaurant that ever exists.
        """
        revision = await self.session.scalar(
            update(KotStreamCursor)
            .where(KotStreamCursor.restaurant_id == self.scope.restaurant_id)
            .values(last_revision=KotStreamCursor.last_revision + 1)
            .returning(KotStreamCursor.last_revision)
        )
        if revision is not None:
            return int(revision)
        self.session.add(KotStreamCursor(restaurant_id=self.scope.restaurant_id, last_revision=1))
        await self.session.flush()
        return 1

    async def current_revision(self) -> int:
        """Where the stream starts for a client that arrives without a cursor: now, not the
        beginning of time. A screen opened at 9pm wants tonight's rail, which `rail()` gives it,
        not a replay of every ticket since the restaurant opened."""
        revision = await self.session.scalar(
            select(KotStreamCursor.last_revision).where(
                KotStreamCursor.restaurant_id == self.scope.restaurant_id
            )
        )
        return int(revision or 0)

    # ------------------------------------------------------------------ reads

    async def rail(
        self,
        *,
        station_id: uuid.UUID | None = None,
        statuses: Sequence[str] = OPEN_STATUSES,
        limit: int | None = None,
    ) -> Sequence[KotTicket]:
        """What a station has to cook, oldest first. The 50 ms query.

        Oldest first rather than newest: a rail is worked from the top, and a kitchen that sorted
        the newest ticket to the front would cook the last order first all night.
        """
        query = self._with_everything_the_rail_renders()
        if station_id is not None:
            query = query.where(KotTicket.station_id == station_id)
        if statuses:
            query = query.where(KotTicket.status.in_(statuses))
        query = query.order_by(KotTicket.printed_at).limit(page_size(limit))
        return (await self.session.scalars(query)).all()

    def _with_everything_the_rail_renders(self) -> Select[tuple[KotTicket]]:
        """Three statements for a page of any size, not three per ticket.

        The dish names are on the line already, so nothing here joins the menu. What is left is the
        order number and the tables — and the tables are joined live rather than snapshotted on
        purpose: a party that moves tables mid-meal must be found where they are now, not where
        they sat when the ticket printed. That is the one fact on a KOT that has to stay current.
        """
        return self.scoped().options(
            selectinload(KotTicket.lines),
            selectinload(KotTicket.order)
            .selectinload(Order.tables)
            .selectinload(OrderTable.restaurant_table),
        )

    async def since(
        self,
        revision: int,
        *,
        station_id: uuid.UUID | None = None,
        limit: int | None = None,
    ) -> Sequence[KotTicket]:
        """Every ticket at or after a revision — the stream's only query.

        **At or after**, not after. Several tickets can share a revision, and an exclusive cursor
        would lose the rest of a batch whose first event reached the client before the connection
        dropped. Re-sending is free because every event is a whole ticket state keyed by its id,
        so applying one twice changes nothing.
        """
        query = (
            self._with_everything_the_rail_renders()
            .where(KotTicket.revision >= revision)
            .order_by(KotTicket.revision, KotTicket.printed_at)
            .limit(page_size(limit))
        )
        if station_id is not None:
            # **In SQL, never afterwards.** The query is limited, so discarding another station's
            # tickets in Python would leave the stream's cursor parked behind them, re-fetching the
            # same page for ever and yielding nothing.
            query = query.where(KotTicket.station_id == station_id)
        return (await self.session.scalars(query)).all()

    async def with_lines(self, ticket_id: uuid.UUID) -> KotTicket | None:
        result = await self.session.scalars(
            self._with_everything_the_rail_renders().where(KotTicket.id == ticket_id)
        )
        return result.first()

    async def lines_for_order_lines(
        self, order_line_ids: Sequence[uuid.UUID]
    ) -> Sequence[KotTicketLine]:
        """Every kitchen line raised for these order lines — how a cancellation on the floor finds
        the work to stop, and how a serve finds the tickets to stamp."""
        if not order_line_ids:
            return []
        return (
            await self.session.scalars(
                select(KotTicketLine).where(
                    KotTicketLine.restaurant_id == self.scope.restaurant_id,
                    KotTicketLine.order_line_id.in_(order_line_ids),
                )
            )
        ).all()

    async def order_lines_by_id(self, order_line_ids: Sequence[uuid.UUID]) -> Sequence[OrderLine]:
        """The floor's copy of these dishes, so the kitchen can say the same thing the rail does."""
        if not order_line_ids:
            return []
        return (
            await self.session.scalars(
                select(OrderLine).where(
                    OrderLine.restaurant_id == self.scope.restaurant_id,
                    OrderLine.id.in_(order_line_ids),
                )
            )
        ).all()

    async def tickets_by_id(self, ticket_ids: Sequence[uuid.UUID]) -> Sequence[KotTicket]:
        if not ticket_ids:
            return []
        return (
            await self.session.scalars(
                self._with_everything_the_rail_renders().where(KotTicket.id.in_(ticket_ids))
            )
        ).all()
