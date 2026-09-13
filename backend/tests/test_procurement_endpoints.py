"""Procurement over HTTP. The acceptance criteria in `docs/modules/M06-procurement-spec.md`.

`test_generic_suites.py` already proves every route here is tenant-isolated and declares a
permission — it is a loop over the route table and it covered these the moment they registered.
What it cannot express is the arithmetic, and the arithmetic is the module.

The golden case is criterion 1 and it is the one to read first: **ordered 50 kg, invoiced 50 kg,
received 47 kg, rejected 0.5 kg at ₹42/kg.** Every number this module will ever report is one of
those four or a difference between them, and if this test is wrong the product tells restaurants a
comfortable lie about their suppliers.

Quantities are in base units throughout (invariant 5), so 50 kg of paneer is `50000` grams and
₹42/kg is `0.042` per gram.
"""

from __future__ import annotations

import uuid
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_setup_endpoints import _auth, _token, _world

STAFF = "/api/v1/staff"

# 50 kg, in grams.
FIFTY_KG = "50000.0000"
# ₹42.00 per kg, per gram.
PER_GRAM = "0.042000"


def _keyed(token: str) -> dict[str, str]:
    """Auth plus a fresh idempotency key, which every delivery post needs since M07 chunk F.

    Fresh per call on purpose: these tests post *different* deliveries, and one shared key would
    turn every second post into a 409 for reusing it.
    """
    return _auth(token) | {"Idempotency-Key": str(uuid.uuid4())}


async def _ingredient(client: AsyncClient, token: str, code: str = "PANEER") -> str:
    response = await client.post(
        f"{STAFF}/stock-items",
        json={
            "kind": "ingredient",
            "code": code,
            "name": code.title(),
            "base_unit": "g",
            "category": "dairy",
            "storage_type": "chilled",
            "current_unit_cost": "0.360000",
            "ingredient": {
                "purchase_unit": "kg",
                "purchase_to_base": "1000",
                "yield_factor": "0.98",
                "shelf_life_days": 4,
            },
        },
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def _supplier(client: AsyncClient, token: str, name: str = "Sharma Traders") -> str:
    response = await client.post(f"{STAFF}/suppliers", json={"name": name}, headers=_auth(token))
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def _order(
    client: AsyncClient,
    token: str,
    supplier_id: str,
    item_id: str,
    *,
    quantity: str = FIFTY_KG,
    send: bool = True,
) -> dict[str, Any]:
    response = await client.post(
        f"{STAFF}/purchase-orders",
        json={
            "supplier_id": supplier_id,
            "lines": [
                {
                    "stock_item_id": item_id,
                    "quantity_ordered": quantity,
                    "unit_price": PER_GRAM,
                }
            ],
        },
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    order = dict(response.json())
    if send:
        sent = await client.post(
            f"{STAFF}/purchase-orders/{order['id']}/send", headers=_auth(token)
        )
        assert sent.status_code == 200, sent.text
        order = dict(sent.json())
    return order


# --------------------------------------------------------------------------- the golden case


class TestTheThreeWayVariance:
    """Acceptance criterion 1. The report this module exists for rests on exactly this."""

    async def test_ordered_invoiced_received_and_rejected_stay_four_numbers(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, token)
        supplier_id = await _supplier(api_client, token)
        order = await _order(api_client, token, supplier_id, item_id)

        response = await api_client.post(
            f"{STAFF}/purchase-orders/{order['id']}/receive",
            json={
                "invoice_number": "4471",
                "lines": [
                    {
                        "stock_item_id": item_id,
                        # They billed for all 50 kg.
                        "quantity_invoiced": FIFTY_KG,
                        # 47 kg came off the lorry.
                        "quantity_received": "47000.0000",
                        # And half a kilo of that was mouldy.
                        "quantity_rejected": "500.0000",
                        "rejection_reason": "Sour on arrival",
                    }
                ],
            },
            headers=_keyed(token),
        )

        assert response.status_code == 201, response.text
        line = response.json()["lines"][0]
        assert line["ordered"] == FIFTY_KG
        assert line["invoiced"] == FIFTY_KG
        assert line["received"] == "47000.0000"
        assert line["rejected"] == "500.0000"
        # What actually went on a shelf: 46.5 kg, not 47.
        assert line["accepted"] == "46500.0000"
        # Billed and not delivered: 3 kg at ₹42 = ₹126.00. This is the money sentence.
        assert line["short_delivery"] == "3000.0000"
        assert line["short_delivery_value"] == "126.00"
        # Still owed against the order: 50 less 46.5 = 3.5 kg. Different from the short delivery,
        # because the rejected half-kilo arrived and was refused.
        assert line["order_shortfall"] == "3500.0000"
        assert response.json()["short_delivery_value"] == "126.00"

    async def test_the_accepted_quantity_is_what_reaches_the_ledger(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """46.5 kg on hand, not 47 and not 50. The rejected stock never existed here."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, token)
        supplier_id = await _supplier(api_client, token)
        order = await _order(api_client, token, supplier_id, item_id)

        await api_client.post(
            f"{STAFF}/purchase-orders/{order['id']}/receive",
            json={
                "lines": [
                    {
                        "stock_item_id": item_id,
                        "quantity_invoiced": FIFTY_KG,
                        "quantity_received": "47000.0000",
                        "quantity_rejected": "500.0000",
                        "rejection_reason": "Sour on arrival",
                    }
                ]
            },
            headers=_keyed(token),
        )

        on_hand = await api_client.get(f"{STAFF}/stock/on-hand", headers=_auth(token))
        assert on_hand.json()["items"][0]["quantity"] == "46500.0000"

    async def test_a_line_delivering_nothing_writes_no_movement(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Acceptance criterion 5.

        *"They billed 50 kg and delivered nothing"* is a real row and it must be recorded — but a
        zero-quantity movement is refused by `ck_stock_movement_quantity_delta`, and rightly,
        because it pollutes every average after it. So the receipt line exists and the ledger does
        not move.
        """
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, token)
        supplier_id = await _supplier(api_client, token)
        order = await _order(api_client, token, supplier_id, item_id)

        response = await api_client.post(
            f"{STAFF}/purchase-orders/{order['id']}/receive",
            json={
                "lines": [
                    {
                        "stock_item_id": item_id,
                        "quantity_invoiced": FIFTY_KG,
                        "quantity_received": "0.0000",
                    }
                ]
            },
            headers=_keyed(token),
        )

        assert response.status_code == 201, response.text
        assert response.json()["lines"][0]["short_delivery"] == FIFTY_KG
        movements = await api_client.get(
            f"{STAFF}/stock/items/{item_id}/movements", headers=_auth(token)
        )
        assert movements.json() == []
        # The receipt itself is on the record, which is the point: the supplier billed for stock
        # that never arrived, and that is exactly what the variance report must be able to say.
        receipts = await api_client.get(f"{STAFF}/goods-receipts", headers=_auth(token))
        assert len(receipts.json()["receipts"]) == 1


class TestLandedCost:
    """Acceptance criterion 3, and `docs/compliance-rules.md` §A6.

    A restaurant on the 5% composition scheme **bears** input GST and cannot reclaim it, so the tax
    on the invoice is part of what the stock cost. Storing only the quoted price understates food
    cost by the whole tax rate — on the product's headline number.
    """

    async def test_tax_is_apportioned_pro_rata_by_line_value(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        paneer = await _ingredient(api_client, token, "PANEER")
        ghee = await _ingredient(api_client, token, "GHEE")
        supplier_id = await _supplier(api_client, token)

        # Two lines worth ₹1,000 and ₹3,000, and ₹200 of tax on the invoice. Pro rata by value,
        # that is ₹50 on the first and ₹150 on the second — a 5% uplift on both, because both
        # lines happen to carry the same rate, which is the ordinary case for one invoice.
        response = await api_client.post(
            f"{STAFF}/goods-receipts",
            json={
                "supplier_id": supplier_id,
                "tax_amount": "200.00",
                "invoice_amount": "4200.00",
                "lines": [
                    {
                        "stock_item_id": paneer,
                        "quantity_invoiced": "10000.0000",
                        "quantity_received": "10000.0000",
                        "unit_price": "0.100000",
                    },
                    {
                        "stock_item_id": ghee,
                        "quantity_invoiced": "10000.0000",
                        "quantity_received": "10000.0000",
                        "unit_price": "0.300000",
                    },
                ],
            },
            headers=_keyed(token),
        )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["invoice_line_total"] == "4000.00"
        first, second = body["lines"]
        assert first["landed_unit_cost"] == "0.105000"
        assert second["landed_unit_cost"] == "0.315000"
        # And that is what the stock is valued at: 10,000 at 0.105 plus 10,000 at 0.315.
        assert first["accepted_value"] == "1050.00"
        assert second["accepted_value"] == "3150.00"

    async def test_with_no_tax_the_landed_cost_is_the_quoted_price(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """An unregistered market trader charges none, and nothing must be invented for them."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, token)
        supplier_id = await _supplier(api_client, token)

        response = await api_client.post(
            f"{STAFF}/goods-receipts",
            json={
                "supplier_id": supplier_id,
                "lines": [
                    {
                        "stock_item_id": item_id,
                        "quantity_invoiced": "1000.0000",
                        "quantity_received": "1000.0000",
                        "unit_price": PER_GRAM,
                    }
                ],
            },
            headers=_keyed(token),
        )

        assert response.json()["lines"][0]["landed_unit_cost"] == PER_GRAM

    async def test_receiving_moves_the_item_onto_its_own_purchase_price(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Acceptance criterion 10.

        `CostSource` is a confidence ordering and its docstring says M06 is what starts writing the
        top of it. Before this module a restaurant's food cost rested on a researched national
        average; after a single delivery it rests on their own supplier's bill.
        """
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, token)
        supplier_id = await _supplier(api_client, token)

        await api_client.post(
            f"{STAFF}/goods-receipts",
            json={
                "supplier_id": supplier_id,
                "tax_amount": "20.00",
                "lines": [
                    {
                        "stock_item_id": item_id,
                        "quantity_invoiced": "1000.0000",
                        "quantity_received": "1000.0000",
                        "unit_price": "0.400000",
                    }
                ],
            },
            headers=_keyed(token),
        )

        item = await api_client.get(f"{STAFF}/stock-items/{item_id}", headers=_auth(token))
        body = item.json()
        assert body["cost_source"] == "purchase"
        # ₹400 of value, ₹20 of tax: a 5% uplift on 0.40.
        assert body["current_unit_cost"] == "0.420000"


# --------------------------------------------------------------------------- the lifecycle


class TestThePurchaseOrderLifecycle:
    async def test_numbers_are_allocated_in_sequence(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, token)
        supplier_id = await _supplier(api_client, token)

        first = await _order(api_client, token, supplier_id, item_id, send=False)
        second = await _order(api_client, token, supplier_id, item_id, send=False)

        assert first["po_number"] == "PO-000001"
        assert second["po_number"] == "PO-000002"

    async def test_the_total_is_computed_from_the_lines(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """`docs/security.md` A04: a client that could send a total would be choosing what its own
        order cost."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, token)
        supplier_id = await _supplier(api_client, token)

        order = await _order(api_client, token, supplier_id, item_id, send=False)

        # 50,000 g at ₹0.042 = ₹2,100.
        assert order["total_amount"] == "2100.00"

    async def test_a_sent_order_cannot_have_its_lines_changed(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, token)
        supplier_id = await _supplier(api_client, token)
        order = await _order(api_client, token, supplier_id, item_id)

        response = await api_client.patch(
            f"{STAFF}/purchase-orders/{order['id']}",
            json={
                "lines": [
                    {
                        "stock_item_id": item_id,
                        "quantity_ordered": "1000.0000",
                        "unit_price": PER_GRAM,
                    }
                ]
            },
            headers=_auth(token),
        )

        assert response.status_code == 409, response.text
        assert response.json()["code"] == "purchase_order.not_draft"

    async def test_a_draft_order_cannot_be_received_against(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Acceptance criterion 9. Nothing can have arrived against an order nobody sent."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, token)
        supplier_id = await _supplier(api_client, token)
        order = await _order(api_client, token, supplier_id, item_id, send=False)

        response = await api_client.post(
            f"{STAFF}/purchase-orders/{order['id']}/receive",
            json={
                "lines": [
                    {
                        "stock_item_id": item_id,
                        "quantity_invoiced": FIFTY_KG,
                        "quantity_received": FIFTY_KG,
                    }
                ]
            },
            headers=_keyed(token),
        )

        assert response.status_code == 409, response.text
        assert response.json()["code"] == "purchase_order.not_sent"

    async def test_a_cancelled_order_cannot_be_received_against(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, token)
        supplier_id = await _supplier(api_client, token)
        order = await _order(api_client, token, supplier_id, item_id)

        cancelled = await api_client.post(
            f"{STAFF}/purchase-orders/{order['id']}/cancel",
            json={"reason": "Ordered twice by mistake"},
            headers=_auth(token),
        )
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "cancelled"
        assert cancelled.json()["cancel_reason"] == "Ordered twice by mistake"

        response = await api_client.post(
            f"{STAFF}/purchase-orders/{order['id']}/receive",
            json={
                "lines": [
                    {
                        "stock_item_id": item_id,
                        "quantity_invoiced": FIFTY_KG,
                        "quantity_received": FIFTY_KG,
                    }
                ]
            },
            headers=_keyed(token),
        )
        assert response.status_code == 409, response.text
        assert response.json()["code"] == "purchase_order.closed"

    async def test_a_partial_delivery_leaves_the_order_open(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Acceptance criterion 4. A supplier delivering 30 of 50 is the ordinary case."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, token)
        supplier_id = await _supplier(api_client, token)
        order = await _order(api_client, token, supplier_id, item_id)

        for delivered, expected in (("30000.0000", "partial"), ("20000.0000", "received")):
            response = await api_client.post(
                f"{STAFF}/purchase-orders/{order['id']}/receive",
                json={
                    "lines": [
                        {
                            "stock_item_id": item_id,
                            "quantity_invoiced": delivered,
                            "quantity_received": delivered,
                        }
                    ]
                },
                headers=_keyed(token),
            )
            assert response.status_code == 201, response.text
            current = await api_client.get(
                f"{STAFF}/purchase-orders/{order['id']}", headers=_auth(token)
            )
            assert current.json()["status"] == expected, delivered

    async def test_cancelling_a_delivered_order_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The stock is already on the shelf; a cancellation would leave it there unexplained."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, token)
        supplier_id = await _supplier(api_client, token)
        order = await _order(api_client, token, supplier_id, item_id)
        await api_client.post(
            f"{STAFF}/purchase-orders/{order['id']}/receive",
            json={
                "lines": [
                    {
                        "stock_item_id": item_id,
                        "quantity_invoiced": "1000.0000",
                        "quantity_received": "1000.0000",
                    }
                ]
            },
            headers=_keyed(token),
        )

        response = await api_client.post(
            f"{STAFF}/purchase-orders/{order['id']}/cancel",
            json={"reason": "Changed my mind"},
            headers=_auth(token),
        )
        assert response.status_code == 409, response.text
        assert response.json()["code"] == "purchase_order.not_cancellable"


# --------------------------------------------------------------------------- receiving rules


class TestReceivingRules:
    async def test_one_supplier_invoice_cannot_be_booked_twice(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Acceptance criterion 7, and the caller is told which receipt already holds it."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, token)
        supplier_id = await _supplier(api_client, token)
        body: dict[str, Any] = {
            "supplier_id": supplier_id,
            "invoice_number": "4471",
            "lines": [
                {
                    "stock_item_id": item_id,
                    "quantity_invoiced": "1000.0000",
                    "quantity_received": "1000.0000",
                    "unit_price": PER_GRAM,
                }
            ],
        }
        first = await api_client.post(f"{STAFF}/goods-receipts", json=body, headers=_keyed(token))
        assert first.status_code == 201, first.text

        again = await api_client.post(f"{STAFF}/goods-receipts", json=body, headers=_keyed(token))

        assert again.status_code == 409, again.text
        assert again.json()["code"] == "goods_receipt.invoice_already_booked"
        assert again.json()["details"]["goods_receipt_id"] == first.json()["receipt"]["id"]

    async def test_an_ad_hoc_receipt_creates_batches_with_no_order_behind_it(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Acceptance criterion 2 — the market purchase `docs/modules.md` M06 asks for by name.

        `order_shortfall` is **null**, not zero: nothing was ordered, so nothing was under-supplied,
        and those are different claims about the world.
        """
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, token)
        supplier_id = await _supplier(api_client, token)

        response = await api_client.post(
            f"{STAFF}/goods-receipts",
            json={
                "supplier_id": supplier_id,
                "lines": [
                    {
                        "stock_item_id": item_id,
                        "quantity_invoiced": "4000.0000",
                        "quantity_received": "4000.0000",
                        "unit_price": PER_GRAM,
                    }
                ],
            },
            headers=_keyed(token),
        )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["receipt"]["purchase_order_id"] is None
        assert body["lines"][0]["ordered"] is None
        assert body["lines"][0]["order_shortfall"] is None
        on_hand = await api_client.get(f"{STAFF}/stock/on-hand", headers=_auth(token))
        assert on_hand.json()["items"][0]["quantity"] == "4000.0000"

    async def test_an_ad_hoc_line_with_no_price_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """There is no order to take a price from, and guessing one would corrupt the batch cost."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, token)
        supplier_id = await _supplier(api_client, token)

        response = await api_client.post(
            f"{STAFF}/goods-receipts",
            json={
                "supplier_id": supplier_id,
                "lines": [
                    {
                        "stock_item_id": item_id,
                        "quantity_invoiced": "1000.0000",
                        "quantity_received": "1000.0000",
                    }
                ],
            },
            headers=_keyed(token),
        )

        assert response.status_code == 400, response.text
        assert response.json()["code"] == "goods_receipt.price_required"

    async def test_a_receipt_against_an_order_defaults_to_the_quoted_price(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Retyping the price is how a transcription error enters the one figure the variance
        report multiplies by."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, token)
        supplier_id = await _supplier(api_client, token)
        order = await _order(api_client, token, supplier_id, item_id)

        response = await api_client.post(
            f"{STAFF}/purchase-orders/{order['id']}/receive",
            json={
                "lines": [
                    {
                        "stock_item_id": item_id,
                        "quantity_invoiced": FIFTY_KG,
                        "quantity_received": FIFTY_KG,
                    }
                ]
            },
            headers=_keyed(token),
        )

        assert response.json()["lines"][0]["unit_price"] == PER_GRAM

    async def test_a_receipt_cannot_be_edited_or_deleted_over_http(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Acceptance criterion 6's other half.

        The database refuses both; this asserts the API never offers them, because a route implying
        otherwise would advertise something the server rejects.
        """
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, token)
        supplier_id = await _supplier(api_client, token)
        posted = await api_client.post(
            f"{STAFF}/goods-receipts",
            json={
                "supplier_id": supplier_id,
                "lines": [
                    {
                        "stock_item_id": item_id,
                        "quantity_invoiced": "1000.0000",
                        "quantity_received": "1000.0000",
                        "unit_price": PER_GRAM,
                    }
                ],
            },
            headers=_keyed(token),
        )
        receipt_id = posted.json()["receipt"]["id"]

        for method in ("PATCH", "PUT", "DELETE"):
            response = await api_client.request(
                method, f"{STAFF}/goods-receipts/{receipt_id}", json={}, headers=_auth(token)
            )
            assert response.status_code == 405, f"{method} -> {response.status_code}"


# --------------------------------------------------------------------------- the report


class TestTheSupplierVarianceReport:
    async def test_the_headline_sentence_is_answerable(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """*"Supplier A short-delivered ... — ₹18,400."* `docs/waste-model.md` §1.

        Three deliveries, each 1 kg short on a 10 kg line at ₹42/kg: ₹42 x 3 = ₹126.
        """
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, token)
        supplier_id = await _supplier(api_client, token)

        for invoice in ("A1", "A2", "A3"):
            response = await api_client.post(
                f"{STAFF}/goods-receipts",
                json={
                    "supplier_id": supplier_id,
                    "invoice_number": invoice,
                    "lines": [
                        {
                            "stock_item_id": item_id,
                            "quantity_invoiced": "10000.0000",
                            "quantity_received": "9000.0000",
                            "unit_price": PER_GRAM,
                        }
                    ],
                },
                headers=_keyed(token),
            )
            assert response.status_code == 201, response.text

        report = await api_client.get(
            f"{STAFF}/suppliers/{supplier_id}/variance", headers=_auth(token)
        )

        assert report.status_code == 200, report.text
        body = report.json()
        assert body["deliveries"] == 3
        assert body["invoiced"] == "30000.0000"
        assert body["received"] == "27000.0000"
        assert body["short_delivery_value"] == "126.00"
        assert body["rows"][0]["code"] == "PANEER"

    async def test_a_supplier_with_no_deliveries_reports_nothing_rather_than_zero_rows(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        supplier_id = await _supplier(api_client, token)

        report = await api_client.get(
            f"{STAFF}/suppliers/{supplier_id}/variance", headers=_auth(token)
        )

        assert report.status_code == 200, report.text
        assert report.json()["rows"] == []
        assert report.json()["deliveries"] == 0


# --------------------------------------------------------------------------- suppliers


class TestSuppliers:
    async def test_two_spellings_of_one_business_are_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Two rows for one supplier cannot be summed, and a variance report split across them
        understates the leak by exactly the amount that would have made somebody act."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        await _supplier(api_client, token, "Sharma Traders")

        response = await api_client.post(
            f"{STAFF}/suppliers",
            # Normalised at the boundary (G-18), so this is the same business.
            json={"name": "  Sharma   Traders "},
            headers=_auth(token),
        )

        assert response.status_code == 409, response.text
        assert response.json()["code"] == "supplier.name_taken"

    async def test_a_malformed_gstin_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """`docs/compliance-rules.md` §A5: structure, not merely length.

        A well-formed GSTIN is still not a *verified* one — there is no check digit (§A3) — and
        nothing downstream may treat it as such.
        """
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.post(
            f"{STAFF}/suppliers",
            json={"name": "Bad GSTIN Traders", "gstin": "27ABCDE1234"},
            headers=_auth(token),
        )

        assert response.status_code == 422, response.text

    async def test_a_supplier_is_deactivated_never_deleted(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        supplier_id = await _supplier(api_client, token)

        response = await api_client.patch(
            f"{STAFF}/suppliers/{supplier_id}", json={"is_active": False}, headers=_auth(token)
        )

        assert response.status_code == 200, response.text
        assert response.json()["is_active"] is False
        assert response.json()["deactivated_at"] is not None
        # Still there, because every historical receipt points at it.
        still = await api_client.get(f"{STAFF}/suppliers/{supplier_id}", headers=_auth(token))
        assert still.status_code == 200

    async def test_an_inactive_supplier_cannot_be_ordered_from(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, token)
        supplier_id = await _supplier(api_client, token)
        await api_client.patch(
            f"{STAFF}/suppliers/{supplier_id}", json={"is_active": False}, headers=_auth(token)
        )

        response = await api_client.post(
            f"{STAFF}/purchase-orders",
            json={
                "supplier_id": supplier_id,
                "lines": [
                    {
                        "stock_item_id": item_id,
                        "quantity_ordered": FIFTY_KG,
                        "unit_price": PER_GRAM,
                    }
                ],
            },
            headers=_auth(token),
        )

        assert response.status_code == 400, response.text
        assert response.json()["code"] == "supplier.inactive"


# --------------------------------------------------------------------------- who may do what


class TestSeparationOfDuties:
    """The grants come from `seed/organization.yaml`'s P1 design, and the line worth reading is the
    accountant: `purchase.manage` and **not** `stock.receive`.

    The person who reconciles supplier invoices may raise an order and may never sign for one. In a
    four-person restaurant one human holds both, which is ordinary — so `created_by` and
    `received_by` are stored and shown, making this a visibility control rather than a block it
    would be absurd to enforce.
    """

    async def test_an_accountant_may_raise_an_order(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "accountant")
        owner = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, owner)
        supplier_id = await _supplier(api_client, owner)

        token = await _token(api_client, "accountant")
        response = await api_client.post(
            f"{STAFF}/purchase-orders",
            json={
                "supplier_id": supplier_id,
                "lines": [
                    {
                        "stock_item_id": item_id,
                        "quantity_ordered": FIFTY_KG,
                        "unit_price": PER_GRAM,
                    }
                ],
            },
            headers=_auth(token),
        )

        assert response.status_code == 201, response.text

    async def test_an_accountant_may_not_sign_for_a_delivery(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "accountant")
        owner = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, owner)
        supplier_id = await _supplier(api_client, owner)

        token = await _token(api_client, "accountant")
        response = await api_client.post(
            f"{STAFF}/goods-receipts",
            json={
                "supplier_id": supplier_id,
                "lines": [
                    {
                        "stock_item_id": item_id,
                        "quantity_invoiced": "1000.0000",
                        "quantity_received": "1000.0000",
                        "unit_price": PER_GRAM,
                    }
                ],
            },
            headers=_keyed(token),
        )

        assert response.status_code == 403, response.text

    async def test_an_accountant_may_not_add_a_supplier(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Reconciling what a supplier billed is not choosing who the restaurant buys from."""
        await _world(db_session, "accountant")
        token = await _token(api_client, "accountant")

        response = await api_client.post(
            f"{STAFF}/suppliers", json={"name": "Cousin's Trading Co"}, headers=_auth(token)
        )

        assert response.status_code == 403, response.text

    async def test_a_chef_reaches_none_of_it(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A kitchen cannot book in a sack it then cooks."""
        await _world(db_session, "chef")
        token = await _token(api_client, "chef")

        for path in ("/suppliers", "/purchase-orders", "/goods-receipts"):
            response = await api_client.get(f"{STAFF}{path}", headers=_auth(token))
            assert response.status_code == 403, f"{path} -> {response.status_code}"

    async def test_a_store_manager_runs_the_whole_thing(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Because running the store room is the job."""
        await _world(db_session, "store_manager")
        token = await _token(api_client, "store_manager")

        for path in ("/suppliers", "/purchase-orders", "/goods-receipts"):
            response = await api_client.get(f"{STAFF}{path}", headers=_auth(token))
            assert response.status_code == 200, f"{path} -> {response.text}"


class TestTheRemainingRoutes:
    """The two read/write routes the golden cases do not happen to pass through, and they are not
    filler: a store manager's day is editing a draft and opening yesterday's delivery."""

    async def test_a_draft_order_can_be_edited_over_http(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, token)
        other_id = await _ingredient(api_client, token, "GHEE")
        supplier_id = await _supplier(api_client, token)
        order = await _order(api_client, token, supplier_id, item_id, send=False)

        response = await api_client.patch(
            f"{STAFF}/purchase-orders/{order['id']}",
            json={
                "expected_at": "2026-10-01T09:00:00Z",
                "lines": [
                    {
                        "stock_item_id": other_id,
                        "quantity_ordered": "1000.0000",
                        "unit_price": "0.900000",
                    }
                ],
            },
            headers=_auth(token),
        )

        assert response.status_code == 200, response.text
        body = response.json()
        # 1,000 g at ₹0.90 = ₹900, recomputed from the new lines rather than carried over.
        assert body["total_amount"] == "900.00"
        assert [line["stock_item_id"] for line in body["lines"]] == [other_id]
        assert body["expected_at"] is not None

    async def test_one_delivery_can_be_opened_by_id(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, token)
        supplier_id = await _supplier(api_client, token)
        posted = await api_client.post(
            f"{STAFF}/goods-receipts",
            json={
                "supplier_id": supplier_id,
                "invoice_number": "4471",
                "lines": [
                    {
                        "stock_item_id": item_id,
                        "quantity_invoiced": "10000.0000",
                        "quantity_received": "9500.0000",
                        "unit_price": PER_GRAM,
                    }
                ],
            },
            headers=_keyed(token),
        )
        receipt_id = posted.json()["receipt"]["id"]

        response = await api_client.get(
            f"{STAFF}/goods-receipts/{receipt_id}", headers=_auth(token)
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["invoice_number"] == "4471"
        # Both numbers, on the record, for ever. This is what an insider would want to edit and
        # what the append-only trigger refuses to let them.
        assert body["lines"][0]["quantity_invoiced"] == "10000.0000"
        assert body["lines"][0]["quantity_received"] == "9500.0000"
