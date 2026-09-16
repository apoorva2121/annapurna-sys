"""Two write paths that read once per row where once per request would do (backlog-issues B9).

Shapes, not budgets: each test compares two sizes, or compares reads with rows, so a fixed number
cannot hide a read per row.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from httpx import AsyncClient
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.menu import MenuItemModifierGroup
from app.seed.identity import seed_identity
from app.seed.menu import seed_menu
from app.seed.setup import seed_setup
from tests.test_procurement_endpoints import STAFF, _ingredient, _keyed, _supplier
from tests.test_setup_endpoints import _token, _world


@contextmanager
def _statements(session: AsyncSession) -> Iterator[list[str]]:
    bind: Any = session.get_bind()
    engine = getattr(bind.engine, "sync_engine", bind.engine)
    seen: list[str] = []

    def _record(_conn: Any, _cursor: Any, statement: str, *_args: Any) -> None:
        seen.append(statement)

    event.listen(engine, "before_cursor_execute", _record)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", _record)


def _reads_of(table: str, statements: list[str]) -> int:
    pattern = re.compile(rf"^\s*SELECT\b.*\bFROM {table}\b(?!_)", re.DOTALL)
    return sum(1 for statement in statements if pattern.search(statement))


async def _deliver(client: AsyncClient, token: str, supplier_id: str, items: list[str]) -> None:
    response = await client.post(
        f"{STAFF}/goods-receipts",
        json={
            "supplier_id": supplier_id,
            "lines": [
                {
                    "stock_item_id": item,
                    "quantity_invoiced": "1000.0000",
                    "quantity_received": "1000.0000",
                    "unit_price": "0.100000",
                }
                for item in items
            ],
        },
        headers=_keyed(token),
    )
    assert response.status_code == 201, response.text


class TestReceivingReadsEachItemOnce:
    async def test_one_more_line_is_one_more_read_of_the_stock_item(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        paneer = await _ingredient(api_client, token, "PANEER")
        ghee = await _ingredient(api_client, token, "GHEE")
        supplier_id = await _supplier(api_client, token)

        with _statements(db_session) as one:
            await _deliver(api_client, token, supplier_id, [paneer])
        with _statements(db_session) as two:
            await _deliver(api_client, token, supplier_id, [paneer, ghee])

        assert _reads_of("stock_item", two) - _reads_of("stock_item", one) == 1


class TestTheSeederReadsLinksOncePerRule:
    async def test_existing_links_are_not_read_dish_by_dish(self, db_session: AsyncSession) -> None:
        await seed_identity(db_session)
        await seed_setup(db_session)

        with _statements(db_session) as seen:
            await seed_menu(db_session)
            await db_session.flush()

        dishes_with_options = await db_session.scalar(
            select(func.count(func.distinct(MenuItemModifierGroup.menu_item_id)))
        )
        assert dishes_with_options is not None and dishes_with_options > 3
        assert _reads_of("menu_item_modifier_group", seen) < dishes_with_options
