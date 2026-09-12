"""The rules `ProcurementService` holds that no HTTP request can reach, and the filters.

Three kinds of thing live here.

**Guards below the API.** Pydantic refuses an empty `lines` list and the ad-hoc schema requires a
`supplier_id`, so `purchase_order.empty` and `goods_receipt.supplier_required` are unreachable over
HTTP *today*. They are not dead code: M15's seed generator and M09's waste module call this service
directly, and a guard that only exists in a schema is a guard the next caller walks around.

**The recomputation guard for decision 7.** `purchase_order.status` is the one derived value this
module stores. The spec promises a test that the stored value equals a recomputation from the
receipt lines at every step, because a stored derived value with no test is a cache that becomes a
lie.

**The list filters**, which are the difference between a screen that shows a store manager their
four open orders and one that shows them four hundred rows.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.enums import PurchaseOrderStatus
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.tenancy import TenantScope
from app.models.identity import Employee
from app.models.procurement import PurchaseOrderLine
from app.models.stock import StockItem
from app.models.tenancy import Organization, Restaurant
from app.services.procurement import (
    OrderLineInput,
    ProcurementService,
    ReceiptLineInput,
    normalise_supplier_name,
)

PER_GRAM = Decimal("0.042000")
TEN_KG = Decimal("10000")


class World:
    def __init__(self, service: ProcurementService, actor: Actor, items: list[StockItem]) -> None:
        self.service = service
        self.actor = actor
        self.items = items

    @property
    def paneer(self) -> StockItem:
        return self.items[0]

    @property
    def ghee(self) -> StockItem:
        return self.items[1]


async def _world(session: AsyncSession, slug: str = "procure") -> World:
    organization = Organization(name=slug.title(), slug=slug)
    session.add(organization)
    await session.flush()
    restaurant = Restaurant(
        organization_id=organization.id,
        name=slug.title(),
        code="PRO",
        timezone="Asia/Kolkata",
        business_day_start=time(5, 0),
    )
    session.add(restaurant)
    await session.flush()
    employee = Employee(
        organization_id=organization.id,
        employee_code="PRO-1",
        full_name="Store Manager",
        joined_on=date(2026, 1, 1),
        employment_type="full_time",
        is_active=True,
    )
    session.add(employee)
    await session.flush()
    items: list[StockItem] = []
    for code in ("PANEER", "GHEE"):
        item = StockItem(
            restaurant_id=restaurant.id,
            kind="ingredient",
            code=code,
            name=code.title(),
            base_unit="g",
            current_unit_cost=Decimal("0.360000"),
            is_active=True,
        )
        session.add(item)
        items.append(item)
    await session.flush()

    scope = TenantScope(organization_id=organization.id, restaurant_id=restaurant.id)
    actor = Actor(
        employee_id=employee.id,
        organization_id=organization.id,
        restaurant_id=restaurant.id,
        full_name="Store Manager",
        permissions=frozenset(),
        rank=30,
    )
    return World(ProcurementService(session, scope), actor, items)


async def _sent_order(world: World, *, quantity: Decimal = TEN_KG) -> object:
    supplier = await world.service.create_supplier(world.actor, name="Sharma Traders")
    order = await world.service.create_order(
        world.actor,
        supplier_id=supplier.id,
        lines=[
            OrderLineInput(
                stock_item_id=world.paneer.id, quantity_ordered=quantity, unit_price=PER_GRAM
            )
        ],
    )
    return await world.service.send_order(world.actor, order.id)


# --------------------------------------------------------------------------- decision 7


class TestTheStoredStatusAgreesWithARecomputation:
    """Decision 7's guard. If this test is ever deleted, the cache becomes a lie."""

    async def test_at_every_step_of_a_split_delivery(self, db_session: AsyncSession) -> None:
        world = await _world(db_session)
        order = await _sent_order(world)

        for delivered in (Decimal("3000"), Decimal("3000"), Decimal("4000")):
            await world.service.receive(
                world.actor,
                purchase_order_id=order.id,  # type: ignore[attr-defined]
                lines=[
                    ReceiptLineInput(
                        stock_item_id=world.paneer.id,
                        quantity_invoiced=delivered,
                        quantity_received=delivered,
                    )
                ],
            )
            assert order.status == await _recompute(world, order)  # type: ignore[attr-defined]

        assert order.status == PurchaseOrderStatus.RECEIVED  # type: ignore[attr-defined]

    async def test_a_rejection_does_not_close_the_order(self, db_session: AsyncSession) -> None:
        """Accepted, not received: stock refused at the gate never arrived for the order's
        purposes, so the supplier still owes it."""
        world = await _world(db_session)
        order = await _sent_order(world)

        await world.service.receive(
            world.actor,
            purchase_order_id=order.id,  # type: ignore[attr-defined]
            lines=[
                ReceiptLineInput(
                    stock_item_id=world.paneer.id,
                    quantity_invoiced=TEN_KG,
                    quantity_received=TEN_KG,
                    quantity_rejected=Decimal("500"),
                    rejection_reason="Sour on arrival",
                )
            ],
        )

        assert order.status == PurchaseOrderStatus.PARTIAL  # type: ignore[attr-defined]
        assert order.status == await _recompute(world, order)  # type: ignore[attr-defined]


async def _recompute(world: World, order: object) -> str:
    """The independent computation, written out rather than reusing the service's own."""
    lines = await world.service.session.scalars(
        select(PurchaseOrderLine).where(
            PurchaseOrderLine.purchase_order_id == order.id  # type: ignore[attr-defined]
        )
    )
    accepted = await world.service.receipts.accepted_by_item(order.id)  # type: ignore[attr-defined]
    rows = lines.all()
    complete = all(
        accepted.get(line.stock_item_id, Decimal("0")) >= Decimal(str(line.quantity_ordered))
        for line in rows
    )
    if complete:
        return PurchaseOrderStatus.RECEIVED.value
    if any(value > 0 for value in accepted.values()):
        return PurchaseOrderStatus.PARTIAL.value
    return PurchaseOrderStatus.SENT.value


# --------------------------------------------------------------------------- guards below the API


class TestTheGuardsNoRequestCanReach:
    async def test_an_order_with_no_lines_is_refused(self, db_session: AsyncSession) -> None:
        world = await _world(db_session)
        supplier = await world.service.create_supplier(world.actor, name="Sharma Traders")

        with pytest.raises(AppError, match="at least one line"):
            await world.service.create_order(world.actor, supplier_id=supplier.id, lines=[])

    async def test_an_order_listing_one_item_twice_is_refused(
        self, db_session: AsyncSession
    ) -> None:
        """Merged rather than refused, two lines of 10 kg might be a mistake or two crates — and
        the server is not the thing that knows which."""
        world = await _world(db_session)
        supplier = await world.service.create_supplier(world.actor, name="Sharma Traders")
        line = OrderLineInput(
            stock_item_id=world.paneer.id, quantity_ordered=TEN_KG, unit_price=PER_GRAM
        )

        with pytest.raises(AppError, match="same item twice"):
            await world.service.create_order(
                world.actor, supplier_id=supplier.id, lines=[line, line]
            )

    async def test_a_delivery_with_no_lines_is_refused(self, db_session: AsyncSession) -> None:
        world = await _world(db_session)
        supplier = await world.service.create_supplier(world.actor, name="Sharma Traders")

        with pytest.raises(AppError, match="at least one line"):
            await world.service.receive(world.actor, supplier_id=supplier.id, lines=[])

    async def test_a_delivery_with_no_supplier_and_no_order_is_refused(
        self, db_session: AsyncSession
    ) -> None:
        """Stock cannot arrive from nobody. Without this the receipt would fail on a NOT NULL
        column instead, which is a 500 rather than a sentence."""
        world = await _world(db_session)

        with pytest.raises(AppError, match="who it came from"):
            await world.service.receive(
                world.actor,
                lines=[
                    ReceiptLineInput(
                        stock_item_id=world.paneer.id,
                        quantity_invoiced=TEN_KG,
                        quantity_received=TEN_KG,
                        unit_price=PER_GRAM,
                    )
                ],
            )

    async def test_a_delivery_listing_one_item_twice_is_refused(
        self, db_session: AsyncSession
    ) -> None:
        """`uq_gr_line_receipt_item` would refuse it anyway, with a 500 rather than a sentence."""
        world = await _world(db_session)
        supplier = await world.service.create_supplier(world.actor, name="Sharma Traders")
        line = ReceiptLineInput(
            stock_item_id=world.paneer.id,
            quantity_invoiced=TEN_KG,
            quantity_received=TEN_KG,
            unit_price=PER_GRAM,
        )

        with pytest.raises(AppError, match="same item twice"):
            await world.service.receive(world.actor, supplier_id=supplier.id, lines=[line, line])

    async def test_cancelling_without_a_reason_is_refused(self, db_session: AsyncSession) -> None:
        world = await _world(db_session)
        order = await _sent_order(world)

        with pytest.raises(AppError, match="needs a reason"):
            await world.service.cancel_order(world.actor, order.id, reason="   ")  # type: ignore[attr-defined]

    async def test_sending_an_order_twice_is_refused(self, db_session: AsyncSession) -> None:
        world = await _world(db_session)
        order = await _sent_order(world)

        with pytest.raises(ConflictError, match="cannot be sent again"):
            await world.service.send_order(world.actor, order.id)  # type: ignore[attr-defined]

    async def test_an_unknown_supplier_order_or_receipt_is_a_404(
        self, db_session: AsyncSession
    ) -> None:
        """Not a 500 and not an empty result: an id that names nothing here must say so."""
        world = await _world(db_session)
        missing = world.paneer.id  # a real uuid that is not one of these three kinds

        with pytest.raises(NotFoundError, match="supplier"):
            await world.service.get_supplier(missing)
        with pytest.raises(NotFoundError, match="purchase order"):
            await world.service.get_order(missing)
        with pytest.raises(NotFoundError, match="delivery"):
            await world.service.get_receipt(missing)
        with pytest.raises(NotFoundError, match="supplier"):
            await world.service.update_supplier(world.actor, missing, {"name": "X"})


# --------------------------------------------------------------------------- editing a draft


class TestEditingADraft:
    async def test_replacing_the_lines_recomputes_the_total(self, db_session: AsyncSession) -> None:
        world = await _world(db_session)
        supplier = await world.service.create_supplier(world.actor, name="Sharma Traders")
        order = await world.service.create_order(
            world.actor,
            supplier_id=supplier.id,
            lines=[
                OrderLineInput(
                    stock_item_id=world.paneer.id, quantity_ordered=TEN_KG, unit_price=PER_GRAM
                )
            ],
        )
        assert Decimal(str(order.total_amount)) == Decimal("420.00")

        await world.service.update_order(
            world.actor,
            order.id,
            lines=[
                OrderLineInput(
                    stock_item_id=world.ghee.id,
                    quantity_ordered=Decimal("1000"),
                    unit_price=Decimal("0.900000"),
                )
            ],
        )

        assert Decimal(str(order.total_amount)) == Decimal("900.00")
        reloaded = await world.service.get_order(order.id)
        assert [line.stock_item_id for line in reloaded.lines] == [world.ghee.id]

    async def test_the_expected_date_can_be_cleared_explicitly(
        self, db_session: AsyncSession
    ) -> None:
        """`None` has to mean two different things on a PATCH — "leave it alone" and "clear it" —
        so the route passes `set_expected` from `model_fields_set` rather than guessing from the
        value. Same pattern as M02's `effective_to`."""
        world = await _world(db_session)
        supplier = await world.service.create_supplier(world.actor, name="Sharma Traders")
        order = await world.service.create_order(
            world.actor,
            supplier_id=supplier.id,
            expected_at=datetime(2026, 10, 1, tzinfo=UTC),
            lines=[
                OrderLineInput(
                    stock_item_id=world.paneer.id, quantity_ordered=TEN_KG, unit_price=PER_GRAM
                )
            ],
        )

        await world.service.update_order(world.actor, order.id, expected_at=None)
        assert order.expected_at == datetime(2026, 10, 1, tzinfo=UTC)

        await world.service.update_order(world.actor, order.id, expected_at=None, set_expected=True)
        assert order.expected_at is None


# --------------------------------------------------------------------------- the filters


class TestTheListFilters:
    async def test_suppliers_can_be_narrowed_to_the_active_ones(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session)
        keep = await world.service.create_supplier(world.actor, name="Aaa Traders")
        drop = await world.service.create_supplier(world.actor, name="Zzz Traders")
        await world.service.update_supplier(world.actor, drop.id, {"is_active": False})

        assert [s.id for s in await world.service.list_suppliers(include_inactive=False)] == [
            keep.id
        ]
        assert len(await world.service.list_suppliers()) == 2

    async def test_orders_can_be_narrowed_by_status_and_supplier(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session)
        supplier = await world.service.create_supplier(world.actor, name="Sharma Traders")
        other = await world.service.create_supplier(world.actor, name="Other Traders")
        draft = await world.service.create_order(
            world.actor,
            supplier_id=supplier.id,
            lines=[
                OrderLineInput(
                    stock_item_id=world.paneer.id, quantity_ordered=TEN_KG, unit_price=PER_GRAM
                )
            ],
        )
        sent = await world.service.create_order(
            world.actor,
            supplier_id=other.id,
            lines=[
                OrderLineInput(
                    stock_item_id=world.ghee.id, quantity_ordered=TEN_KG, unit_price=PER_GRAM
                )
            ],
        )
        await world.service.send_order(world.actor, sent.id)

        by_status = await world.service.list_orders(status=PurchaseOrderStatus.DRAFT)
        assert [order.id for order in by_status] == [draft.id]
        by_supplier = await world.service.list_orders(supplier_id=other.id)
        assert [order.id for order in by_supplier] == [sent.id]

    async def test_receipts_can_be_narrowed_by_supplier(self, db_session: AsyncSession) -> None:
        world = await _world(db_session)
        mine = await world.service.create_supplier(world.actor, name="Sharma Traders")
        theirs = await world.service.create_supplier(world.actor, name="Other Traders")
        for supplier_id in (mine.id, theirs.id):
            await world.service.receive(
                world.actor,
                supplier_id=supplier_id,
                lines=[
                    ReceiptLineInput(
                        stock_item_id=world.paneer.id,
                        quantity_invoiced=Decimal("1000"),
                        quantity_received=Decimal("1000"),
                        unit_price=PER_GRAM,
                    )
                ],
            )

        filtered = await world.service.list_receipts(supplier_id=mine.id)
        assert len(filtered) == 1
        assert filtered[0].supplier_id == mine.id
        assert len(await world.service.list_receipts()) == 2


# --------------------------------------------------------------------------- odds and ends


class TestTheSmallerRules:
    async def test_a_supplier_name_is_normalised_before_it_is_compared(self) -> None:
        assert normalise_supplier_name("  Sharma   Traders ") == "Sharma Traders"

    async def test_renaming_onto_another_supplier_is_refused(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session)
        await world.service.create_supplier(world.actor, name="Sharma Traders")
        second = await world.service.create_supplier(world.actor, name="Other Traders")

        with pytest.raises(ConflictError, match="already a supplier"):
            await world.service.update_supplier(world.actor, second.id, {"name": "Sharma  Traders"})

    async def test_renaming_a_supplier_to_its_own_name_is_allowed(
        self, db_session: AsyncSession
    ) -> None:
        """The clash check has to exclude the row being edited, or correcting a phone number while
        leaving the name alone would refuse itself."""
        world = await _world(db_session)
        supplier = await world.service.create_supplier(world.actor, name="Sharma Traders")

        await world.service.update_supplier(
            world.actor, supplier.id, {"name": "Sharma Traders", "phone": "9820011001"}
        )
        assert supplier.phone == "9820011001"

    async def test_reactivating_a_supplier_clears_the_deactivation_date(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session)
        supplier = await world.service.create_supplier(world.actor, name="Sharma Traders")
        await world.service.update_supplier(world.actor, supplier.id, {"is_active": False})
        assert supplier.deactivated_at is not None

        await world.service.update_supplier(world.actor, supplier.id, {"is_active": True})
        assert supplier.deactivated_at is None

    async def test_a_second_delivery_at_the_same_price_writes_no_second_reprice(
        self, db_session: AsyncSession
    ) -> None:
        """An audit trail of identical reprices is noise, and noise is how a real price change
        stops being noticed."""
        world = await _world(db_session)
        supplier = await world.service.create_supplier(world.actor, name="Sharma Traders")
        for invoice in ("A1", "A2"):
            await world.service.receive(
                world.actor,
                supplier_id=supplier.id,
                invoice_number=invoice,
                lines=[
                    ReceiptLineInput(
                        stock_item_id=world.paneer.id,
                        quantity_invoiced=Decimal("1000"),
                        quantity_received=Decimal("1000"),
                        unit_price=PER_GRAM,
                    )
                ],
            )

        from app.models.audit import AuditLog

        rows = await db_session.scalars(
            select(AuditLog).where(AuditLog.action == "stock_item.repriced")
        )
        assert len(rows.all()) == 1

    async def test_the_variance_window_excludes_deliveries_outside_it(
        self, db_session: AsyncSession
    ) -> None:
        """Bounded by `business_date` on an index, and the bound has to actually bind: a report
        that quietly included last year would make every supplier look worse than they are."""
        world = await _world(db_session)
        supplier = await world.service.create_supplier(world.actor, name="Sharma Traders")
        today = await world.service.inventory.business_date_now()
        for invoice, moment in (
            ("OLD", datetime.now(UTC) - timedelta(days=400)),
            ("NEW", datetime.now(UTC)),
        ):
            await world.service.receive(
                world.actor,
                supplier_id=supplier.id,
                invoice_number=invoice,
                received_at=moment,
                lines=[
                    ReceiptLineInput(
                        stock_item_id=world.paneer.id,
                        quantity_invoiced=Decimal("10000"),
                        quantity_received=Decimal("9000"),
                        unit_price=PER_GRAM,
                    )
                ],
            )

        recent = await world.service.supplier_variance(
            supplier.id, start=today - timedelta(days=30), end=today
        )
        assert recent.rows[0].deliveries == 1
        assert recent.short_delivery_value == Decimal("42.00")

        everything = await world.service.supplier_variance(
            supplier.id, start=today - timedelta(days=500), end=today
        )
        assert everything.rows[0].deliveries == 2
        assert everything.short_delivery_value == Decimal("84.00")


async def test_receiving_against_an_unknown_order_is_a_404(db_session: AsyncSession) -> None:
    """`_require_order` locks the row before anything else happens, so an id that names nothing
    must 404 there rather than fall through to a supplier lookup that would 404 for the wrong
    reason."""
    world = await _world(db_session)

    with pytest.raises(NotFoundError, match="purchase order"):
        await world.service.receive(
            world.actor,
            purchase_order_id=world.paneer.id,
            lines=[
                ReceiptLineInput(
                    stock_item_id=world.paneer.id,
                    quantity_invoiced=TEN_KG,
                    quantity_received=TEN_KG,
                    unit_price=PER_GRAM,
                )
            ],
        )
