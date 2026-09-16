"""After settlement: invoice cancellation, credit notes and refunds. Acceptance criteria 13 and 14.

A settled order is never edited. What happens afterwards is a new document, and the tests below are
about the three ways a real evening tries to go around that: cancelling yesterday's paid bill to
make the cash disappear, crediting a dish more times than it was served, and refunding more than
was credited.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

from httpx import AsyncClient, Response
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.business_day import calendar_date_of, financial_year_of
from app.models.audit import AuditLog
from app.models.menu import MenuItemVariant
from app.models.orders import CreditNote, Invoice, Order, Payment
from app.repositories.orders import CreditedSoFar
from app.services.reversals import CreditLineInput, ReversalService
from tests.test_orders_endpoints import ORDERS, Menu, _added, _open, _setup
from tests.test_settlement import _count, _registered, _settle
from tests.test_setup_endpoints import World, _auth, _token

INVOICES = "/api/v1/staff/invoices"
_KOLKATA = "Asia/Kolkata"


def _keyed(token: str, key: str | None = None) -> dict[str, str]:
    return _auth(token) | {"Idempotency-Key": key or str(uuid.uuid4())}


async def _settled(
    session: AsyncSession, client: AsyncClient, *, quantity: int = 2
) -> tuple[World, Menu, str, dict[str, Any], dict[str, Any]]:
    """A settled order of dal and its tax invoice, and the waiter's token that settled it."""
    world, menu, token = await _setup(session, client)
    await _registered(session, world)
    order = await _added(
        client, token, await _open(client, token, menu), menu.dal, quantity=quantity
    )
    response = await _settle(client, token, order)
    assert response.status_code == 201, response.text
    return world, menu, token, order, response.json()


async def _cancel(
    client: AsyncClient, token: str, invoice: dict[str, Any], reason: str = "billed to table 7"
) -> Response:
    return await client.post(
        f"{INVOICES}/{invoice['id']}/cancel", json={"reason": reason}, headers=_keyed(token)
    )


async def _credit(
    client: AsyncClient,
    token: str,
    invoice: dict[str, Any],
    *,
    quantity: int = 1,
    refunds: list[dict[str, Any]] | None = None,
    key: str | None = None,
    line_id: str | None = None,
) -> Response:
    order = (await client.get(f"{ORDERS}/{invoice['order_id']}", headers=_auth(token))).json()
    return await client.post(
        f"{INVOICES}/{invoice['id']}/credit-notes",
        json={
            "reason": "the dal came out cold",
            "lines": [{"order_line_id": line_id or order["lines"][0]["id"], "quantity": quantity}],
            "refunds": refunds or [],
        },
        headers=_keyed(token, key),
    )


class TestCancellingAnInvoice:
    """Acceptance criterion 14: on its business day only, keeping its number."""

    async def test_an_invoice_issued_in_error_is_cancelled_keeps_its_number_and_voids_its_order(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, _, token, order, invoice = await _settled(db_session, api_client)
        manager = await _token(api_client, "manager")

        response = await _cancel(api_client, manager, invoice)

        assert response.status_code == 200, response.text
        cancelled = response.json()
        assert cancelled["status"] == "cancelled"
        assert cancelled["invoice_number"] == invoice["invoice_number"]
        assert cancelled["cancel_reason"] == "billed to table 7"
        voided = (await api_client.get(f"{ORDERS}/{order['id']}", headers=_auth(token))).json()
        assert voided["status"] == "voided"
        assert await _count(db_session, AuditLog, AuditLog.action == "invoice.cancel") == 1
        # Cancelling moves no money: the payment stays, and nothing negative appears.
        assert await _count(db_session, Payment, Payment.amount < 0) == 0

    async def test_a_waiter_cannot_cancel_an_invoice(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Cancelling a paid cash bill is how the cash disappears."""
        _, _, token, _, invoice = await _settled(db_session, api_client)

        response = await _cancel(api_client, token, invoice)

        assert response.status_code == 403

    async def test_an_invoice_from_an_earlier_business_day_cannot_be_cancelled(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """After its own day, a reduction is a credit note — which carries lines, tax and a reason,
        where a cancellation would simply make yesterday's takings smaller."""
        world, _, _, _, _ = await _settled(db_session, api_client)
        manager = await _token(api_client, "manager")
        now = datetime.now(UTC)
        two_days_ago = calendar_date_of(now, _KOLKATA) - timedelta(days=2)
        old_order = Order(
            restaurant_id=world.restaurant.id,
            order_number="99",
            type="takeaway",
            channel="pos",
            status="settled",
            placed_at=now - timedelta(days=2),
            settled_at=now - timedelta(days=2),
            business_date=two_days_ago,
            subtotal=Decimal("470.00"),
            grand_total=Decimal("470.00"),
        )
        db_session.add(old_order)
        await db_session.flush()
        old_invoice = Invoice(
            restaurant_id=world.restaurant.id,
            order_id=old_order.id,
            document_type="bill_of_supply",
            financial_year=financial_year_of(two_days_ago),
            sequence=900,
            invoice_number=f"{financial_year_of(two_days_ago)}/000900",
            status="issued",
            issued_at=now - timedelta(days=2),
            invoice_date=two_days_ago,
            business_date=two_days_ago,
            supplier_name=world.restaurant.name,
            taxable_total=Decimal("470.00"),
            grand_total=Decimal("470.00"),
        )
        db_session.add(old_invoice)
        await db_session.commit()

        response = await _cancel(api_client, manager, {"id": str(old_invoice.id)})

        assert response.status_code == 409
        assert response.json()["code"] == "invoice.cancel_window_closed"

    async def test_a_cancelled_invoice_cannot_be_cancelled_again(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, _, _, _, invoice = await _settled(db_session, api_client)
        manager = await _token(api_client, "manager")
        assert (await _cancel(api_client, manager, invoice)).status_code == 200

        again = await _cancel(api_client, manager, invoice)

        assert again.status_code == 409
        assert again.json()["code"] == "invoice.already_cancelled"

    async def test_an_invoice_with_a_credit_note_cannot_be_cancelled_as_though_issued_in_error(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, _, _, _, invoice = await _settled(db_session, api_client)
        manager = await _token(api_client, "manager")
        assert (await _credit(api_client, manager, invoice)).status_code == 201

        response = await _cancel(api_client, manager, invoice)

        assert response.status_code == 409
        assert response.json()["code"] == "invoice.has_credit_notes"


class TestCreditNotes:
    """Acceptance criterion 13: after settlement, a reduction is a credit note and a refund is a
    negative payment naming it."""

    async def test_a_dish_sent_back_is_credited_and_refunded_against_the_invoice(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, _, token, order, invoice = await _settled(db_session, api_client)
        manager = await _token(api_client, "manager")

        response = await _credit(
            api_client, manager, invoice, refunds=[{"method": "cash", "amount": "493.50"}]
        )

        assert response.status_code == 201, response.text
        note = response.json()
        year = financial_year_of(calendar_date_of(datetime.now(UTC), _KOLKATA))
        assert note["credit_note_number"] == f"CN/{year}/00001"
        assert note["grand_total"] == "493.50"
        (line,) = note["lines"]
        assert (line["quantity"], line["taxable_value"], line["cgst_amount"]) == (
            1,
            "470.00",
            "11.75",
        )
        (refund,) = note["refunds"]
        assert (refund["amount"], refund["credit_note_id"]) == ("-493.50", note["id"])

        still = (await api_client.get(f"{ORDERS}/{order['id']}", headers=_auth(token))).json()
        unchanged = (
            await api_client.get(f"{INVOICES}/{invoice['id']}", headers=_auth(token))
        ).json()
        assert still["status"] == "settled"
        assert unchanged["grand_total"] == "987.00"
        assert len(unchanged["payments"]) == 2

    async def test_crediting_every_portion_one_at_a_time_adds_up_to_the_bill_exactly(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Three portions at ₹101: CGST on ₹303 is ₹7.575, billed as ₹7.58. Each note is the
        difference between running totals rounded once: a third is ₹2.53, two thirds ₹5.05, all
        three ₹7.58. So the notes take ₹2.53, ₹2.52 and ₹2.53, adding up to the bill exactly, and
        at no point has more been credited than was billed — the property rounding each note on
        its own lost on a cheap dish credited a portion at a time (second reader, finding 5)."""
        world, menu, token = await _setup(db_session, api_client)
        await _registered(db_session, world)
        await db_session.execute(
            update(MenuItemVariant)
            .where(MenuItemVariant.id == menu.dal)
            .values(price=Decimal("101.00"))
        )
        await db_session.commit()
        order = await _added(
            api_client, token, await _open(api_client, token, menu), menu.dal, quantity=3
        )
        invoice = (await _settle(api_client, token, order)).json()
        assert invoice["cgst_total"] == "7.58"
        manager = await _token(api_client, "manager")

        notes = []
        for _ in range(3):
            response = await _credit(api_client, manager, invoice)
            assert response.status_code == 201, response.text
            notes.append(response.json())

        assert [note["cgst_total"] for note in notes] == ["2.53", "2.52", "2.53"]
        assert sum(Decimal(note["taxable_total"]) for note in notes) == Decimal("303.00")
        assert sum(Decimal(note["grand_total"]) for note in notes) == Decimal(
            invoice["grand_total"]
        )

    async def test_a_dish_cannot_be_credited_more_times_than_it_was_billed(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, _, _, _, invoice = await _settled(db_session, api_client)
        manager = await _token(api_client, "manager")
        assert (await _credit(api_client, manager, invoice, quantity=2)).status_code == 201

        response = await _credit(api_client, manager, invoice)

        assert response.status_code == 422
        assert response.json()["code"] == "credit_note.more_than_billed"

    async def test_a_refund_larger_than_the_credit_note_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, _, _, _, invoice = await _settled(db_session, api_client)
        manager = await _token(api_client, "manager")

        response = await _credit(
            api_client, manager, invoice, refunds=[{"method": "cash", "amount": "500.00"}]
        )

        assert response.status_code == 422
        assert response.json()["code"] == "credit_note.refund_exceeds"
        assert await _count(db_session, CreditNote) == 0

    async def test_a_refund_on_account_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, _, _, _, invoice = await _settled(db_session, api_client)
        manager = await _token(api_client, "manager")

        response = await _credit(
            api_client, manager, invoice, refunds=[{"method": "due", "amount": "100.00"}]
        )

        assert response.status_code == 422

    async def test_a_cancelled_invoice_has_nothing_to_credit(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, _, _, _, invoice = await _settled(db_session, api_client)
        manager = await _token(api_client, "manager")
        assert (await _cancel(api_client, manager, invoice)).status_code == 200

        response = await _credit(api_client, manager, invoice)

        assert response.status_code == 409
        assert response.json()["code"] == "invoice.cancelled"

    async def test_a_credit_note_tapped_twice_is_issued_once(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, _, _, _, invoice = await _settled(db_session, api_client)
        manager = await _token(api_client, "manager")
        key = str(uuid.uuid4())

        first = await _credit(api_client, manager, invoice, key=key)
        again = await _credit(api_client, manager, invoice, key=key)

        assert (first.status_code, again.status_code) == (201, 201), again.text
        assert again.headers.get("Idempotent-Replayed") == "true"
        assert await _count(db_session, CreditNote) == 1

    async def test_a_waiter_cannot_issue_a_credit_note(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, _, token, _, invoice = await _settled(db_session, api_client)

        response = await _credit(api_client, token, invoice)

        assert response.status_code == 403


# --------------------------------------------------------------------------- the second reader


class TestCreditNotesNeverOvershootTheBill:
    """Second reader, finding 5: one note per portion must add up to the line, never past it."""

    def test_nineteen_single_portion_notes_never_credit_more_tax_than_was_billed(self) -> None:
        """19 of a ₹3 dish at 5%: the line carries CGST ₹1.43. Rounding each note's own share
        gives ₹0.08 a note and ₹1.44 after eighteen, more than was billed, leaving a nineteenth
        that would have to credit minus a paisa. Rounding the running share cannot drift."""
        line_id = uuid.uuid4()
        line = SimpleNamespace(
            quantity=19,
            taxable_value=Decimal("57.00"),
            cgst_amount=Decimal("1.43"),
            tax_amount=Decimal("2.86"),
            tax_regime="gst",
        )
        billed = cast(Any, {line_id: line})
        so_far: dict[uuid.UUID, CreditedSoFar] = {}

        for _ in range(19):
            credit = ReversalService._credit_for(
                billed, so_far, CreditLineInput(order_line_id=line_id, quantity=1)
            )
            before = so_far.get(line_id, CreditedSoFar())
            so_far[line_id] = CreditedSoFar(
                quantity=before.quantity + 1,
                taxable=before.taxable + credit.taxable,
                cgst=before.cgst + credit.cgst,
                tax=before.tax + credit.tax,
            )
            assert credit.cgst >= 0
            assert so_far[line_id].cgst <= Decimal("1.43")

        total = so_far[line_id]
        assert (total.taxable, total.cgst, total.tax) == (
            Decimal("57.00"),
            Decimal("1.43"),
            Decimal("2.86"),
        )


class TestARefundNeedsMoneyReceived:
    async def test_a_bill_settled_on_account_cannot_be_refunded_in_cash(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Second reader, finding 6. A bill settled as `due` received no money. A credit note may
        reduce what the customer owes; it may not hand cash over the counter for it."""
        world, menu, token = await _setup(db_session, api_client)
        await _registered(db_session, world)
        order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)
        settled = await _settle(
            api_client, token, order, payments=[{"method": "due", "amount": order["grand_total"]}]
        )
        assert settled.status_code == 201, settled.text
        invoice = settled.json()
        manager = await _token(api_client, "manager")

        refused = await _credit(
            api_client, manager, invoice, refunds=[{"method": "cash", "amount": "493.50"}]
        )

        assert refused.status_code == 422, refused.text
        assert refused.json()["code"] == "credit_note.refund_exceeds_received"
        assert (await _credit(api_client, manager, invoice)).status_code == 201


class TestTheInvoiceSaysWhatWasCredited:
    """Backlog row "The invoice screen does not show what has already been credited". A manager
    crediting a second dish could not see what an earlier note already took off."""

    async def test_each_dish_carries_what_earlier_credit_notes_took_off(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, _, token, _, invoice = await _settled(db_session, api_client)
        manager = await _token(api_client, "manager")
        before = (await api_client.get(f"{INVOICES}/{invoice['id']}", headers=_auth(token))).json()

        credited = await _credit(api_client, manager, invoice)

        assert credited.status_code == 201, credited.text
        order = (
            await api_client.get(f"{ORDERS}/{invoice['order_id']}", headers=_auth(token))
        ).json()
        after = (await api_client.get(f"{INVOICES}/{invoice['id']}", headers=_auth(token))).json()
        assert before["credited"] == []
        assert after["credited"] == [
            {"order_line_id": order["lines"][0]["id"], "quantity": 1, "amount": "493.50"}
        ]


class TestTheInvoiceListsItsCreditNotes:
    """Decision D27 (backlog-issues B12): a credit note is always viewable from its invoice. It was
    shown once, as it was issued, and never again."""

    async def test_each_note_is_on_the_invoice_with_its_dishes(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, _, token, _, invoice = await _settled(db_session, api_client)
        manager = await _token(api_client, "manager")
        credited = await _credit(api_client, manager, invoice)
        assert credited.status_code == 201, credited.text

        after = (await api_client.get(f"{INVOICES}/{invoice['id']}", headers=_auth(token))).json()

        [note] = after["credit_notes"]
        assert note["credit_note_number"] == credited.json()["credit_note_number"]
        assert note["reason"] == "the dal came out cold"
        assert note["grand_total"] == "493.50"
        assert [line["quantity"] for line in note["lines"]] == [1]
