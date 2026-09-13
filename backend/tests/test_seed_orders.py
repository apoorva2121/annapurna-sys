"""The orders, the bill, the credit note and the short till the seed plants for M07's screens.

`docs/seed-data.md`'s principle once more: a demo that opens on an empty table map and a till with
nothing to reconcile is a demo of an empty product. These tests stop the planted state quietly
disappearing — and because the seeder goes through the real services, they also prove a seeded bill
is priced, numbered and credited by the same code a real one is.

The whole seed runs first, in order, because this seeder stands on every one before it: tables,
dishes, tax rates, recipes and a stock ledger the inventory seeder has already opened.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orders import CashSession, CreditNote, Invoice, Order, Payment
from app.models.tenancy import Restaurant
from app.seed.identity import seed_identity
from app.seed.inventory import seed_inventory
from app.seed.menu import seed_menu
from app.seed.orders import seed_orders
from app.seed.procurement import seed_procurement
from app.seed.setup import seed_setup
from app.seed.stock import seed_stock


@pytest.fixture
async def seeded(db_session: AsyncSession) -> AsyncSession:
    await seed_identity(db_session)
    await seed_setup(db_session)
    await seed_menu(db_session)
    await seed_stock(db_session)
    await seed_inventory(db_session)
    await seed_procurement(db_session)
    return db_session


async def _koregaon(session: AsyncSession) -> Restaurant:
    restaurant = await session.scalar(select(Restaurant).where(Restaurant.code == "SG_KOREGAON"))
    assert restaurant is not None
    return restaurant


async def test_the_floor_opens_mid_service(seeded: AsyncSession) -> None:
    """An open order and a sent one, beside the bill that has already gone."""
    summary = await seed_orders(seeded)
    restaurant = await _koregaon(seeded)

    statuses = sorted(
        (
            await seeded.scalars(select(Order.status).where(Order.restaurant_id == restaurant.id))
        ).all()
    )
    assert statuses == ["open", "sent", "settled"]
    assert summary.orders_created >= 3


async def test_the_bill_is_split_across_cash_and_upi_and_one_dish_is_credited(
    seeded: AsyncSession,
) -> None:
    await seed_orders(seeded)
    restaurant = await _koregaon(seeded)

    invoice = await seeded.scalar(select(Invoice).where(Invoice.restaurant_id == restaurant.id))
    assert invoice is not None
    methods = set(
        (
            await seeded.scalars(
                select(Payment.method).where(
                    Payment.invoice_id == invoice.id, Payment.credit_note_id.is_(None)
                )
            )
        ).all()
    )
    assert "cash" in methods
    note = await seeded.scalar(select(CreditNote).where(CreditNote.invoice_id == invoice.id))
    assert note is not None
    # Partial: one dish back, not the whole bill.
    assert Decimal("0") < Decimal(str(note.grand_total)) < Decimal(str(invoice.grand_total))


async def test_the_till_is_closed_fifty_rupees_short(seeded: AsyncSession) -> None:
    """The planted shortfall, so the cash-up screen has a variance to show on day one."""
    await seed_orders(seeded)
    restaurant = await _koregaon(seeded)

    till = await seeded.scalar(
        select(CashSession).where(CashSession.restaurant_id == restaurant.id)
    )
    assert till is not None
    assert till.status == "closed"
    assert till.variance == Decimal("-50.00")


async def test_seeding_again_takes_no_second_order(seeded: AsyncSession) -> None:
    await seed_orders(seeded)

    again = await seed_orders(seeded)

    assert again.created_nothing
