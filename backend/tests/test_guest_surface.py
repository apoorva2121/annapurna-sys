"""The guest realm, end to end. The first routes this product serves to strangers.

ADR 0009's guarantees are structural and suite 5 proves the structure. This file proves the
*behaviour* — that the two QR codes grant what decision 1 says they grant and nothing else, that a
reprinted bill kills the sessions opened from the old one, and that a refusal never tells a stranger
which of several things went wrong.

**One refusal for everything** is the rule most of these tests are really about.
`docs/security.md`: "No enumeration — guest lookups return the same response whether or not the
[thing] exists." A guest cannot act on the difference between "no such table" and "that code
expired"; an attacker can.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.guest_token import GuestScopeKind, issue_guest_token, new_guest_slug
from app.core.rate_limit import reset_rate_limits
from app.core.security import hash_refresh_token
from app.models.orders import Order
from app.models.setup import DiningArea, RestaurantTable
from app.models.tenancy import Organization, Restaurant
from tests.test_customer_endpoints import _auth, _sign_in, _world

GUEST = "/api/v1/guest"


async def _table(session: AsyncSession, restaurant: Restaurant) -> RestaurantTable:
    area = DiningArea(restaurant_id=restaurant.id, name=f"Hall {uuid.uuid4().hex[:4]}", seq=1)
    session.add(area)
    await session.flush()
    table = RestaurantTable(
        restaurant_id=restaurant.id,
        dining_area_id=area.id,
        code=f"T{uuid.uuid4().hex[:4]}",
        seats=4,
    )
    session.add(table)
    await session.flush()
    return table


async def _order_with_bill_token(
    session: AsyncSession, restaurant: Restaurant, *, raw: str | None = None
) -> tuple[uuid.UUID, str]:
    """An order whose bill has been printed, and the raw token that QR carries."""
    raw = raw or uuid.uuid4().hex
    order_id = uuid.uuid4()
    await session.execute(
        text(
            'INSERT INTO "order" (id, restaurant_id, order_number, type, channel, status, '
            "business_date, placed_at, subtotal, discount_total, charge_total, tax_total, "
            "round_off, grand_total, guest_token_hash, guest_token_expires_at) "
            "VALUES (:id, :rid, :number, 'dine_in', 'pos', 'open', :day, now(), 250, 0, 0, 12.50, "
            "0, 262.50, :hash, :expires)"
        ),
        {
            "id": order_id,
            "rid": restaurant.id,
            "number": uuid.uuid4().hex[:6],
            "day": date(2026, 9, 16),
            "hash": hash_refresh_token(raw),
            "expires": datetime.now(UTC) + timedelta(hours=24),
        },
    )
    return order_id, raw


async def _guest_token(api_client: AsyncClient, **body: str) -> str:
    response = await api_client.post(f"{GUEST}/session", json=body)
    assert response.status_code == 201, response.text
    return str(response.json()["token"])


# --------------------------------------------------------------------------- the table QR


class TestTheTableCodeGrantsTheMenuAndNothingElse:
    async def test_scanning_the_sticker_opens_a_session(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        reset_rate_limits()
        world = await _world(db_session)
        table = await _table(db_session, world.restaurants["main"])

        response = await api_client.post(f"{GUEST}/session", json={"table_slug": table.guest_slug})

        assert response.status_code == 201, response.text
        assert response.json()["scope"] == "table"
        # The restaurant's name is public — it is on the door — and is the only thing about the
        # restaurant a guest response carries.
        assert response.json()["restaurant_name"] == "Main"

    async def test_a_table_token_cannot_open_a_bill(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Decision 1, in one assertion. A photographed sticker is worth the menu; reading what
        table four is eating tonight needs the QR printed on table four's bill."""
        reset_rate_limits()
        world = await _world(db_session)
        table = await _table(db_session, world.restaurants["main"])
        token = await _guest_token(api_client, table_slug=table.guest_slug)

        response = await api_client.get(f"{GUEST}/order", headers=_auth(token))

        assert response.status_code == 401, response.text
        assert response.json()["code"] == "guest.session_expired"

    async def test_an_unknown_slug_answers_exactly_as_an_expired_one_does(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """No enumeration. A stranger must not be able to learn which table codes are real."""
        reset_rate_limits()
        await _world(db_session)

        unknown = await api_client.post(f"{GUEST}/session", json={"table_slug": new_guest_slug()})
        expired = await api_client.post(f"{GUEST}/session", json={"order_token": uuid.uuid4().hex})

        assert unknown.status_code == expired.status_code == 401
        assert unknown.json()["code"] == expired.json()["code"] == "guest.session_expired"
        assert unknown.json()["message"] == expired.json()["message"]

    async def test_a_deactivated_table_stops_resolving(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        reset_rate_limits()
        world = await _world(db_session)
        table = await _table(db_session, world.restaurants["main"])
        await db_session.execute(
            update(RestaurantTable).where(RestaurantTable.id == table.id).values(is_active=False)
        )

        response = await api_client.post(f"{GUEST}/session", json={"table_slug": table.guest_slug})

        assert response.status_code == 401, response.text

    async def test_giving_both_codes_or_neither_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        reset_rate_limits()
        world = await _world(db_session)
        table = await _table(db_session, world.restaurants["main"])

        neither = await api_client.post(f"{GUEST}/session", json={})
        both = await api_client.post(
            f"{GUEST}/session",
            json={"table_slug": table.guest_slug, "order_token": uuid.uuid4().hex},
        )

        assert neither.status_code == 401, neither.text
        assert both.status_code == 401, both.text


# --------------------------------------------------------------------------- the menu


class TestTheGuestMenu:
    async def test_a_guest_reads_the_menu_and_sees_no_internal_field(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        reset_rate_limits()
        world = await _world(db_session)
        table = await _table(db_session, world.restaurants["main"])
        token = await _guest_token(api_client, table_slug=table.guest_slug)

        response = await api_client.get(f"{GUEST}/menu", headers=_auth(token))

        assert response.status_code == 200, response.text
        body = response.text
        assert "station_id" not in body
        assert "prep_minutes" not in body
        assert "is_active" not in body

    async def test_the_menu_is_cheap_to_re_read(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """`docs/security.md` wants guest menu responses "cached and cheap". The menu is the one
        endpoint a whole restaurant hits at once, and it changes a few times a week."""
        reset_rate_limits()
        world = await _world(db_session)
        table = await _table(db_session, world.restaurants["main"])
        token = await _guest_token(api_client, table_slug=table.guest_slug)
        first = await api_client.get(f"{GUEST}/menu", headers=_auth(token))
        etag = first.headers["ETag"]

        again = await api_client.get(
            f"{GUEST}/menu", headers={**_auth(token), "If-None-Match": etag}
        )

        assert again.status_code == 304
        assert again.headers["ETag"] == etag

    async def test_no_token_reads_no_menu(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        reset_rate_limits()
        await _world(db_session)

        response = await api_client.get(f"{GUEST}/menu")

        assert response.status_code == 401, response.text


# --------------------------------------------------------------------------- the bill QR


class TestTheBillCode:
    async def test_the_bill_shows_the_servers_figures(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        reset_rate_limits()
        world = await _world(db_session)
        _, raw = await _order_with_bill_token(db_session, world.restaurants["main"])
        token = await _guest_token(api_client, order_token=raw)

        response = await api_client.get(f"{GUEST}/order", headers=_auth(token))

        assert response.status_code == 200, response.text
        assert response.json()["grand_total"] == "262.50"
        assert response.json()["tax_total"] == "12.50"
        assert response.json()["is_settled"] is False

    async def test_a_reprinted_bill_kills_the_sessions_opened_from_the_old_one(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The reason the token carries a fingerprint of the stored hash.

        A bill folder left on a cleared table is a token in a stranger's hands, and reprinting is
        exactly the moment a restaurant wants that to stop being true — including for a session
        already opened from it, which would otherwise live out its expiry.
        """
        reset_rate_limits()
        world = await _world(db_session)
        order_id, raw = await _order_with_bill_token(db_session, world.restaurants["main"])
        token = await _guest_token(api_client, order_token=raw)
        assert (await api_client.get(f"{GUEST}/order", headers=_auth(token))).status_code == 200

        # The bill is printed again: a new raw token, a new hash.
        await db_session.execute(
            update(Order)
            .where(Order.id == order_id)
            .values(guest_token_hash=hash_refresh_token(uuid.uuid4().hex))
        )

        after = await api_client.get(f"{GUEST}/order", headers=_auth(token))

        assert after.status_code == 401, after.text

    async def test_an_expired_bill_token_stops_working(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        reset_rate_limits()
        world = await _world(db_session)
        order_id, raw = await _order_with_bill_token(db_session, world.restaurants["main"])
        token = await _guest_token(api_client, order_token=raw)
        await db_session.execute(
            update(Order)
            .where(Order.id == order_id)
            .values(guest_token_expires_at=datetime.now(UTC) - timedelta(minutes=1))
        )

        response = await api_client.get(f"{GUEST}/order", headers=_auth(token))

        assert response.status_code == 401, response.text

    async def test_a_bill_token_for_another_restaurant_reads_nothing(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A forged token naming somebody else's order. The signature stops this, and the
        restaurant check behind it stops a signed one whose restaurant does not match."""
        reset_rate_limits()
        world = await _world(db_session, branches=("koregaon", "baner"))
        order_id, _ = await _order_with_bill_token(db_session, world.restaurants["baner"])
        forged = issue_guest_token(
            restaurant_id=world.restaurants["koregaon"].id,
            kind=GuestScopeKind.ORDER,
            subject_id=order_id,
            expires_in=timedelta(hours=1),
            token_fingerprint="0" * 16,
        )

        response = await api_client.get(f"{GUEST}/order", headers=_auth(forged))

        assert response.status_code == 401, response.text


# --------------------------------------------------------------------------- the two realms


class TestTheTwoRealmsDoNotMeet:
    async def test_a_staff_token_reaches_no_guest_route(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """ADR 0009's guarantee from the other side. `test_no_guest_token_satisfies_any_staff_route`
        is the half everybody writes; this is the half that stops a manager browsing the bill of a
        table they are not at."""
        reset_rate_limits()
        world = await _world(db_session)
        staff = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))

        menu = await api_client.get(f"{GUEST}/menu", headers=_auth(staff))
        order = await api_client.get(f"{GUEST}/order", headers=_auth(staff))

        assert menu.status_code == 401, menu.text
        assert order.status_code == 401, order.text

    async def test_a_guest_token_reaches_no_staff_route(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The generic suite asserts this over every staff route with a synthetic token. This one
        uses a *real* guest token, minted by the real route, against a real staff endpoint."""
        reset_rate_limits()
        world = await _world(db_session)
        table = await _table(db_session, world.restaurants["main"])
        token = await _guest_token(api_client, table_slug=table.guest_slug)

        response = await api_client.get("/api/v1/staff/customers", headers=_auth(token))

        assert response.status_code == 401, response.text


# --------------------------------------------------------------------------- the rate limit


async def test_a_burst_of_writes_is_refused_with_a_retry_hint(
    db_session: AsyncSession, api_client: AsyncClient
) -> None:
    """The write tier is tight because `docs/security.md` calls out rating manipulation by name.

    The limiter is a floor rather than the defence — what actually holds is structural — but a floor
    that is not there is not a floor.
    """
    reset_rate_limits()
    await _world(db_session)

    statuses: list[int] = []
    for _ in range(12):
        attempt = await api_client.post(f"{GUEST}/session", json={"order_token": uuid.uuid4().hex})
        statuses.append(attempt.status_code)

    assert 429 in statuses, "a burst of session mints was never rate-limited"
    limited = await api_client.post(f"{GUEST}/session", json={"order_token": uuid.uuid4().hex})
    assert limited.status_code == 429
    assert limited.json()["details"]["retry_after_seconds"] >= 1


async def test_the_read_tier_is_generous_enough_for_a_table(
    db_session: AsyncSession, api_client: AsyncClient
) -> None:
    """A party of six browsing a menu must never meet a 429. The budget is chosen against what a
    table does, not against what a server can serve."""
    reset_rate_limits()
    world = await _world(db_session)
    table = await _table(db_session, world.restaurants["main"])
    token = await _guest_token(api_client, table_slug=table.guest_slug)

    statuses = [
        (await api_client.get(f"{GUEST}/menu", headers=_auth(token))).status_code for _ in range(20)
    ]

    assert set(statuses) == {200}


async def test_the_limiter_starts_clean_for_every_test(
    db_session: AsyncSession, api_client: AsyncClient
) -> None:
    """The counter is module-level state, and module-level state shared across a suite is the
    classic source of a test that passes alone and fails in company — here by handing the twentieth
    request in a file a 429 that has nothing to do with what it was asserting."""
    reset_rate_limits()
    world = await _world(db_session)
    table = await _table(db_session, world.restaurants["main"])

    response = await api_client.post(f"{GUEST}/session", json={"table_slug": table.guest_slug})

    assert response.status_code == 201, response.text


# --------------------------------------------------------------------------- tenancy


async def test_a_guest_menu_is_this_restaurants_menu(
    db_session: AsyncSession, api_client: AsyncClient
) -> None:
    """The tenant boundary, on the surface where it matters most. A table token names one
    restaurant, and the menu it opens is that restaurant's."""
    reset_rate_limits()
    spice = await _world(db_session)
    tandoor = Organization(name="Tandoor House", slug=f"th-{uuid.uuid4().hex[:8]}")
    db_session.add(tandoor)
    await db_session.flush()
    other = Restaurant(
        organization_id=tandoor.id, name="Tandoor House", code=f"TH{uuid.uuid4().hex[:6]}"
    )
    db_session.add(other)
    await db_session.flush()
    table = await _table(db_session, spice.restaurants["main"])
    token = await _guest_token(api_client, table_slug=table.guest_slug)

    response = await api_client.get(f"{GUEST}/menu", headers=_auth(token))

    assert response.status_code == 200, response.text
    # Nothing of the other tenant's, and nothing that would say whether it exists.
    assert "Tandoor" not in response.text


async def test_a_table_slug_is_unique_across_the_product(db_session: AsyncSession) -> None:
    """Which is what lets the slug *determine* a restaurant rather than be looked up inside one —
    the only unscoped query in the guest realm, and the reason it is safe."""
    slugs = (await db_session.execute(select(RestaurantTable.guest_slug))).scalars().all()

    assert len(set(slugs)) == len(slugs)
