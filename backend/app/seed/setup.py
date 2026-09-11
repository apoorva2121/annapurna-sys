"""Seeds M02's master data: the floor, the stations and the tax rates.

The data has been in `seed/operations.yaml` since M00 and validated by `seed/validate.py` ever
since — it was simply never loaded, because nothing existed to load it into until M02 built the
tables. The result was that `make seed` produced a restaurant with staff and an empty floor, so
every M02 screen opened blank and the manual pass would have begun by hand-building a floor plan.

**Get-or-create by natural key**, like the identity seeder and for the same reason: `make seed` is
run casually and repeatedly, and the failure to design against is not "it crashed" but "it silently
made a second Terrace".

**Only Spice Garden Koregaon gets a floor.** `operations.yaml` describes one restaurant — it is the
demo world the manual script walks through. The second branch is deliberately left empty: a
restaurant with no dining areas is a real state the product has to handle on day one of onboarding
(`docs/onboarding-cold-start.md`), and the seed is the only place it is easy to see.

**The tax rates are back-dated and that is correct.** `GST5` starts 2025-04-01, which the service
would refuse — `create_tax_group` will not accept a rate starting before today. The seed writes the
rows directly because it is representing history rather than making a decision: these rates *were*
in force. The rule exists to stop someone back-dating a change today, not to deny that last year
happened.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import TableStatus
from app.models.setup import DiningArea, RestaurantTable, Station, TaxGroup
from app.models.tenancy import Restaurant
from app.seed.loader import find_seed_directory

logger = logging.getLogger(__name__)

_FILENAME = "operations.yaml"

# The restaurant `operations.yaml` describes. Named here rather than inferred, so adding a second
# branch to the seed does not silently give it a copy of this one's floor plan.
_FOR_RESTAURANT = "SG_KOREGAON"


class MissingSeedRestaurantError(RuntimeError):
    """`operations.yaml` describes a restaurant the identity seed did not create."""


@dataclass(frozen=True, slots=True)
class SetupSummary:
    dining_areas_created: int = 0
    tables_created: int = 0
    stations_created: int = 0
    tax_groups_created: int = 0

    @property
    def created_nothing(self) -> bool:
        return not any(
            (
                self.dining_areas_created,
                self.tables_created,
                self.stations_created,
                self.tax_groups_created,
            )
        )


def load_operations() -> dict[str, Any]:
    raw = (find_seed_directory() / _FILENAME).read_text(encoding="utf-8")
    parsed: dict[str, Any] = yaml.safe_load(raw)
    return parsed


async def seed_setup(session: AsyncSession, data: dict[str, Any] | None = None) -> SetupSummary:
    """Create the demo floor, stations and tax rates. Safe to run repeatedly.

    Does not commit — the caller owns the transaction, which is what lets the test suite seed inside
    a transaction it rolls back.
    """
    data = data or load_operations()
    restaurant = await session.scalar(select(Restaurant).where(Restaurant.code == _FOR_RESTAURANT))
    if restaurant is None:
        raise MissingSeedRestaurantError(
            f"{_FOR_RESTAURANT} does not exist. Seed identity first — operations.yaml describes "
            "that restaurant's floor and cannot stand on its own."
        )

    areas = await _dining_areas(session, restaurant.id, data.get("dining_areas", []))
    tables = await _tables(session, restaurant.id, areas, data.get("restaurant_tables", []))
    stations = await _stations(session, restaurant.id, data.get("stations", []))
    taxes = await _tax_groups(session, restaurant.id, data.get("tax_groups", []))

    await session.flush()
    summary = SetupSummary(
        dining_areas_created=len(areas.created),
        tables_created=tables,
        stations_created=stations,
        tax_groups_created=taxes,
    )
    logger.info("seed.setup.complete", extra={"summary": summary})
    return summary


@dataclass
class _Areas:
    """Areas by their YAML code, plus which ones this run actually created."""

    by_code: dict[str, DiningArea]
    created: list[str]


async def _dining_areas(
    session: AsyncSession, restaurant_id: Any, records: list[dict[str, Any]]
) -> _Areas:
    areas = _Areas(by_code={}, created=[])
    for record in records:
        name = str(record["name"])
        existing = await session.scalar(
            select(DiningArea).where(
                DiningArea.restaurant_id == restaurant_id, DiningArea.name == name
            )
        )
        if existing is not None:
            areas.by_code[str(record["code"])] = existing
            continue
        area = DiningArea(
            restaurant_id=restaurant_id,
            name=name,
            # The YAML numbers from 1; the column is 0-based, because a new area created through the
            # API goes to `next_seq()` which starts at 0. Mixing the two origins would put the first
            # seeded area and the first created one in the same slot.
            seq=int(record["seq"]) - 1,
            is_active=True,
        )
        session.add(area)
        areas.by_code[str(record["code"])] = area
        areas.created.append(str(record["code"]))
    await session.flush()
    return areas


async def _tables(
    session: AsyncSession, restaurant_id: Any, areas: _Areas, records: list[dict[str, Any]]
) -> int:
    created = 0
    for record in records:
        code = str(record["code"])
        existing = await session.scalar(
            select(RestaurantTable).where(
                RestaurantTable.restaurant_id == restaurant_id, RestaurantTable.code == code
            )
        )
        if existing is not None:
            continue
        area = areas.by_code.get(str(record["area"]))
        if area is None:
            raise MissingSeedRestaurantError(
                f"table {code} is in area {record['area']!r}, which operations.yaml does not"
                " define."
            )
        session.add(
            RestaurantTable(
                restaurant_id=restaurant_id,
                dining_area_id=area.id,
                code=code,
                seats=int(record["seats"]),
                # Every table starts free. A seeded `occupied` would be an order that does not
                # exist, and M07 is what puts tables into any other state.
                status=TableStatus.FREE,
                is_active=True,
            )
        )
        created += 1
    return created


async def _stations(
    session: AsyncSession, restaurant_id: Any, records: list[dict[str, Any]]
) -> int:
    created = 0
    for record in records:
        code = str(record["code"])
        existing = await session.scalar(
            select(Station).where(Station.restaurant_id == restaurant_id, Station.code == code)
        )
        if existing is not None:
            continue
        session.add(
            Station(
                restaurant_id=restaurant_id,
                code=code,
                name=str(record["name"]),
                seq=int(record["seq"]) - 1,
                is_active=True,
            )
        )
        created += 1
    return created


async def _tax_groups(
    session: AsyncSession, restaurant_id: Any, records: list[dict[str, Any]]
) -> int:
    created = 0
    for record in records:
        name = str(record["name"])
        existing = await session.scalar(
            select(TaxGroup).where(TaxGroup.restaurant_id == restaurant_id, TaxGroup.name == name)
        )
        if existing is not None:
            continue
        effective_from = record["effective_from"]
        session.add(
            TaxGroup(
                restaurant_id=restaurant_id,
                name=name,
                # `Decimal(str(...))` and never `Decimal(float)`: 0.05 as a float is
                # 0.05000000000000000277…, and that is what would be stored (CLAUDE.md invariant 3).
                rate=Decimal(str(record["rate"])),
                is_inclusive=bool(record.get("is_inclusive", False)),
                effective_from=(
                    effective_from
                    if isinstance(effective_from, date)
                    else date.fromisoformat(str(effective_from))
                ),
                effective_to=None,
            )
        )
        created += 1
    return created
