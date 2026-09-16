"""Waste over HTTP: the permissions, the idempotency, and the rule about showing the cost.

`test_generic_suites.py` already proves every route here is tenant-isolated and declares a
permission. `test_waste_service.py` proves the event and its movement are one transaction. What is
left, and what this file is:

- **a waiter cannot log waste at all** — the design's own line, and the one this module's first
  draft spec got wrong;
- **the API has no field for a cost**, so a client that sends one is refused rather than ignored;
- **a double tap books it once** — the situation the idempotency key exists for, on a phone in a
  kitchen;
- **every write actually commits.** Each write here is followed by a *second request* that reads it
  back, because `app/api/v1/staff/inventory.py` documents a bug where every write returned 201 with
  a populated body and then vanished, and M08's kitchen routes reproduced it exactly. No
  single-request test can see it: inside one transaction the write is visible to the code that made
  it.
"""

from __future__ import annotations

import uuid
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import WastageStage
from tests.test_inventory_endpoints import _ingredient
from tests.test_setup_endpoints import _auth, _token, _world

STAFF = "/api/v1/staff"
WASTAGE = f"{STAFF}/wastage"


async def _stocked(
    session: AsyncSession, client: AsyncClient, *, roles: tuple[str, ...] = ()
) -> tuple[str, str]:
    """A restaurant with paneer on the shelf, and the owner's token. 5 kg at ₹0.36/g.

    `roles` are the *extra* people a test needs. The owner is always made and must not be repeated:
    `_world` creates one login per role it is given, and naming a role twice is a duplicate e-mail.
    """
    await _world(session, "owner", *roles)
    token = await _token(client, "owner")
    item_id = await _ingredient(client, token)
    receipt = await client.post(
        f"{STAFF}/stock/receipts",
        json={"stock_item_id": item_id, "quantity": "5000", "unit_cost": "0.36"},
        headers=_auth(token),
    )
    assert receipt.status_code == 201, receipt.text
    return item_id, token


async def _reason(
    client: AsyncClient, token: str, code: str, stage: str, **flags: Any
) -> dict[str, Any]:
    response = await client.post(
        f"{WASTAGE}/reasons",
        json={"code": code, "name": code.title(), "stage": stage, **flags},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _log(
    client: AsyncClient,
    token: str,
    item_id: str,
    reason_id: str,
    *,
    quantity: str = "250",
    key: str | None = None,
) -> Any:
    return await client.post(
        WASTAGE,
        json={
            "stock_item_id": item_id,
            "wastage_reason_id": reason_id,
            "quantity": quantity,
        },
        headers={**_auth(token), "Idempotency-Key": key or str(uuid.uuid4())},
    )


class TestLoggingWaste:
    async def test_logging_waste_survives_the_request_that_made_it(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Two requests, deliberately. The first returns 201 with a body; only the second can tell
        whether anything was committed — which is the bug this codebase has now written twice."""
        item_id, token = await _stocked(db_session, api_client)
        reason = await _reason(api_client, token, "EXPIRED", WastageStage.STORAGE)

        created = await _log(api_client, token, item_id, reason["id"])
        assert created.status_code == 201, created.text

        listed = await api_client.get(WASTAGE, headers=_auth(token))
        assert listed.status_code == 200, listed.text
        assert [event["id"] for event in listed.json()["items"]] == [created.json()["id"]]

    async def test_the_cost_comes_back_and_was_never_asked_for(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """`docs/waste-model.md`: never ask the person logging what it cost, and show the rupee
        value afterwards, because it teaches. 250 g at ₹0.36/g is ₹90.00."""
        item_id, token = await _stocked(db_session, api_client)
        reason = await _reason(api_client, token, "EXPIRED", WastageStage.STORAGE)

        created = await _log(api_client, token, item_id, reason["id"])

        assert created.json()["cost_value"] == "90.00"

    async def test_a_client_that_sends_a_cost_is_refused_rather_than_ignored(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Stronger than dropping it. A client that sends a price believes the price it sent, and
        should be told otherwise — the same reasoning M07 applies to order lines."""
        item_id, token = await _stocked(db_session, api_client)
        reason = await _reason(api_client, token, "EXPIRED", WastageStage.STORAGE)

        response = await api_client.post(
            WASTAGE,
            json={
                "stock_item_id": item_id,
                "wastage_reason_id": reason["id"],
                "quantity": "250",
                "cost_value": "1.00",
            },
            headers={**_auth(token), "Idempotency-Key": str(uuid.uuid4())},
        )

        assert response.status_code == 422, response.text

    async def test_a_double_tap_books_it_once(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A phone in a kitchen, on a bad connection. Double-booked waste is not a duplicate row —
        it is a second consumption against the ledger and a food-cost figure wrong all month."""
        item_id, token = await _stocked(db_session, api_client)
        reason = await _reason(api_client, token, "EXPIRED", WastageStage.STORAGE)
        key = str(uuid.uuid4())

        first = await _log(api_client, token, item_id, reason["id"], key=key)
        second = await _log(api_client, token, item_id, reason["id"], key=key)

        assert first.status_code == 201, first.text
        assert second.json()["id"] == first.json()["id"]
        listed = await api_client.get(WASTAGE, headers=_auth(token))
        assert len(listed.json()["items"]) == 1

    async def test_logging_without_an_idempotency_key_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """422 and a readable sentence, matching every other ledger write (M07 chunk F). The key
        is made when the button is pressed, so a wrapper inventing one per request would give every
        retry a new key — which is the double booking the key exists to stop."""
        item_id, token = await _stocked(db_session, api_client)
        reason = await _reason(api_client, token, "EXPIRED", WastageStage.STORAGE)

        response = await api_client.post(
            WASTAGE,
            json={
                "stock_item_id": item_id,
                "wastage_reason_id": reason["id"],
                "quantity": "250",
            },
            headers=_auth(token),
        )

        assert response.status_code == 422, response.text
        assert response.json()["code"] == "idempotency.key_required"


class TestTheSummary:
    async def test_it_splits_by_stage_with_shares_that_add_up(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The report `docs/waste-model.md` exists for. The shares adding to a hundred is the first
        thing anybody checks, and the fastest way to lose their trust in the number."""
        item_id, token = await _stocked(db_session, api_client)
        storage = await _reason(api_client, token, "EXPIRED", WastageStage.STORAGE)
        prep = await _reason(api_client, token, "OVER_PREPARATION", WastageStage.PREP)

        await _log(api_client, token, item_id, storage["id"], quantity="250")
        await _log(api_client, token, item_id, prep["id"], quantity="750")

        summary = await api_client.get(f"{WASTAGE}/summary", headers=_auth(token))
        body = summary.json()

        assert body["total_cost"] == "360.00"
        shares = {line["stage"]: line["share_percent"] for line in body["lines"]}
        assert shares == {"prep": "75.0", "storage": "25.0"}
        assert sum(float(share) for share in shares.values()) == 100.0

    async def test_an_empty_range_is_zero_rather_than_an_error(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A restaurant that wasted nothing this week should see that it wasted nothing, not a
        blank screen — `docs/ui/conventions.md` on empty states."""
        _, token = await _stocked(db_session, api_client)

        summary = await api_client.get(f"{WASTAGE}/summary", headers=_auth(token))

        assert summary.status_code == 200, summary.text
        assert summary.json()["total_cost"] == "0.00"
        assert summary.json()["lines"] == []


class TestWhoMayDoWhat:
    async def test_a_waiter_cannot_log_waste(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The design's own line, and the one this module's first draft spec got wrong. Waste is a
        kitchen and storeroom event; a dish a customer sent back is recorded by whoever takes it
        off the bill."""
        item_id, token = await _stocked(db_session, api_client, roles=("waiter",))
        reason = await _reason(api_client, token, "EXPIRED", WastageStage.STORAGE)
        waiter = await _token(api_client, "waiter")

        response = await _log(api_client, waiter, item_id, reason["id"])

        assert response.status_code == 403, response.text

    async def test_a_chef_may_log_and_may_not_approve(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The separation of duties this module's approval exists for: the people who log most of
        the waste are not the people who sign it off."""
        item_id, token = await _stocked(db_session, api_client, roles=("chef",))
        reason = await _reason(
            api_client, token, "EXPIRED", WastageStage.STORAGE, requires_approval=True
        )
        chef = await _token(api_client, "chef")

        logged = await _log(api_client, chef, item_id, reason["id"])
        assert logged.status_code == 201, logged.text
        assert logged.json()["awaiting_approval"] is True

        approved = await api_client.post(
            f"{WASTAGE}/{logged.json()['id']}/approve", headers=_auth(chef)
        )
        assert approved.status_code == 403, approved.text

    async def test_a_manager_may_approve_what_somebody_else_logged(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        item_id, token = await _stocked(db_session, api_client, roles=("chef", "manager"))
        reason = await _reason(
            api_client, token, "EXPIRED", WastageStage.STORAGE, requires_approval=True
        )
        chef = await _token(api_client, "chef")
        manager = await _token(api_client, "manager")
        logged = await _log(api_client, chef, item_id, reason["id"])

        approved = await api_client.post(
            f"{WASTAGE}/{logged.json()['id']}/approve", headers=_auth(manager)
        )

        assert approved.status_code == 200, approved.text
        assert approved.json()["awaiting_approval"] is False
        assert approved.json()["approved_at"] is not None

    async def test_a_manager_cannot_approve_waste_they_logged_themselves(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The control is worth nothing if one person can be both people."""
        item_id, token = await _stocked(db_session, api_client, roles=("manager",))
        reason = await _reason(
            api_client, token, "EXPIRED", WastageStage.STORAGE, requires_approval=True
        )
        manager = await _token(api_client, "manager")
        logged = await _log(api_client, manager, item_id, reason["id"])

        response = await api_client.post(
            f"{WASTAGE}/{logged.json()['id']}/approve", headers=_auth(manager)
        )

        assert response.status_code == 409, response.text
        assert response.json()["issue"] > 0

    async def test_a_chef_cannot_invent_a_reason(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A reason carries the *stage* every report groups by, so adding one changes what the
        restaurant's numbers mean. It sits with the tax rates, behind `restaurant.configure`."""
        _, _ = await _stocked(db_session, api_client, roles=("chef",))
        chef = await _token(api_client, "chef")

        response = await api_client.post(
            f"{WASTAGE}/reasons",
            json={"code": "MINE", "name": "Mine", "stage": WastageStage.PREP},
            headers=_auth(chef),
        )

        assert response.status_code == 403, response.text


class TestReasons:
    async def test_a_reason_survives_the_request_that_made_it(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, token = await _stocked(db_session, api_client)
        created = await _reason(api_client, token, "expired", WastageStage.STORAGE)
        # Normalised, because the code is a permanent join key and "expired" and "EXPIRED" must not
        # become two reasons.
        assert created["code"] == "EXPIRED"

        listed = await api_client.get(f"{WASTAGE}/reasons", headers=_auth(token))
        assert [reason["code"] for reason in listed.json()["items"]] == ["EXPIRED"]

    async def test_a_duplicate_code_is_refused_with_a_number_to_quote(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, token = await _stocked(db_session, api_client)
        await _reason(api_client, token, "EXPIRED", WastageStage.STORAGE)

        response = await api_client.post(
            f"{WASTAGE}/reasons",
            json={"code": "EXPIRED", "name": "Expired again", "stage": WastageStage.STORAGE},
            headers=_auth(token),
        )

        assert response.status_code == 409, response.text
        assert response.json()["issue"] > 0

    async def test_the_stage_cannot_be_changed(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Changing it would move last quarter's waste between stages retrospectively, which is
        the one thing a waste report must never do. There is no field for it."""
        _, token = await _stocked(db_session, api_client)
        reason = await _reason(api_client, token, "EXPIRED", WastageStage.STORAGE)

        response = await api_client.patch(
            f"{WASTAGE}/reasons/{reason['id']}",
            json={"stage": WastageStage.PREP},
            headers=_auth(token),
        )

        assert response.status_code == 422, response.text

    async def test_a_withdrawn_reason_cannot_be_logged_against(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        item_id, token = await _stocked(db_session, api_client)
        reason = await _reason(api_client, token, "EXPIRED", WastageStage.STORAGE)
        withdrawn = await api_client.patch(
            f"{WASTAGE}/reasons/{reason['id']}",
            json={"is_active": False},
            headers=_auth(token),
        )
        assert withdrawn.status_code == 200, withdrawn.text

        response = await _log(api_client, token, item_id, reason["id"])

        assert response.status_code == 409, response.text


class TestUnitsAreConvertedByTheServer:
    """Backlog-issues B12e, applied to the screen whose whole promise is ten seconds.

    A cook thinks in half a kilo of paneer, not five hundred grams. So the presets are labelled in
    the item's purchase unit and the **server** converts — the same rule the receiving form follows,
    after a delivery typed against the wrong unit repriced cabbage to ₹40 *per gram* and made a
    plate of Veg Manchurian cost ₹5,207.
    """

    async def test_a_quantity_in_the_purchase_unit_is_converted(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Half a kilo of paneer is 500 g at ₹0.36/g — ₹180.00. Typed as "0.5" with the flag set.

        Without the conversion it would be half a *gram*, and the cook would see ₹0.18 for a tray
        they had just binned — a number so wrong it teaches them the screen is lying.
        """
        item_id, token = await _stocked(db_session, api_client)
        reason = await _reason(api_client, token, "EXPIRED", WastageStage.STORAGE)

        response = await api_client.post(
            WASTAGE,
            json={
                "stock_item_id": item_id,
                "wastage_reason_id": reason["id"],
                "quantity": "0.5",
                "per_purchase_unit": True,
            },
            headers={**_auth(token), "Idempotency-Key": str(uuid.uuid4())},
        )

        assert response.status_code == 201, response.text
        assert response.json()["quantity"] == "500.0000"
        assert response.json()["cost_value"] == "180.00"

    async def test_base_units_remain_the_default(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A caller that knows grams keeps working, unchanged — `per_purchase_unit` defaults to
        false, which is the old meaning."""
        item_id, token = await _stocked(db_session, api_client)
        reason = await _reason(api_client, token, "EXPIRED", WastageStage.STORAGE)

        response = await _log(api_client, token, item_id, reason["id"], quantity="500")

        assert response.json()["quantity"] == "500.0000"
        assert response.json()["cost_value"] == "180.00"
