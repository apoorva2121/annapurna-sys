"""The rules for configuring a restaurant: its settings, its floor, its stations, its tax rates.

Most of this is ordinary master-data CRUD. Four rules are not, and they are the reason this file is
longer than the endpoints it serves:

**1 · A timezone is validated against the IANA database, not stored as typed.** `Asia/Calcutta` is
real, `Asia/Kolkta` is a typo, and both are strings. An unrecognised zone makes `business_date_of`
raise on every order the restaurant takes afterwards — at write time, in the middle of service. It
is refused here instead, where the person who typed it is still looking at the screen.

**2 · Changing `business_day_start` is audited with before and after.** It moves takings between
days without touching a single order, which is precisely what makes it worth auditing: a manager
shifting it to hide a bad day leaves no other trace (M02 spec threat table).

**3 · A tax rate is never edited, only superseded.** The rate is copied onto every order line and
cited by an invoice, so editing one in place silently restates tax already charged and reported.
Superseding is done in one call, so the old row's end and the new row's start cannot drift apart.

**4 · `effective_from` may not be before today's business date.** Back-dating a rate is how a
change that looks legitimate reaches invoices that were already issued. Today is the *restaurant's*
today (ADR 0004) — at 01:00 in Pune the business date is still yesterday, and a rate starting
"today" by the server's UTC clock would silently start a day early.

Deactivation everywhere, deletion nowhere (ADR 0008): a table that hosted an order last year must
still resolve when that order is read.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.business_day import business_date_of
from app.core.enums import TableStatus
from app.core.errors import AppError, ConflictError, NotFoundError
from app.models.audit import AuditLog
from app.models.setup import DiningArea, RestaurantTable, Station, TaxGroup
from app.models.tenancy import Restaurant
from app.repositories.setup import (
    DiningAreaRepository,
    RestaurantRepository,
    RestaurantTableRepository,
    StationRepository,
    TaxGroupRepository,
)
from app.schemas.setup import (
    DiningAreaCreateRequest,
    DiningAreaUpdateRequest,
    RestaurantUpdateRequest,
    StationCreateRequest,
    StationUpdateRequest,
    TableCreateRequest,
    TableUpdateRequest,
    TaxGroupCreateRequest,
)

# The settings whose change is worth a row in `audit_log`. Not every field: an address correction
# is not an event anybody will investigate, while the four below all move money or change what a
# number means.
_AUDITED_SETTINGS = frozenset({"timezone", "currency", "business_day_start", "gstin"})

# A rate's period ends the day before its replacement's begins, so the two meet exactly.
_ONE_DAY = timedelta(days=1)


class SetupService:
    """One service for the whole setup surface, because it is one screen area behind one permission.

    Owns its transaction boundary the way the rest of the application does: the caller commits.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------ repositories

    def _restaurant(self, actor: Actor) -> RestaurantRepository:
        return RestaurantRepository(self.session, actor.scope)

    def _areas(self, actor: Actor) -> DiningAreaRepository:
        return DiningAreaRepository(self.session, actor.scope)

    def _tables(self, actor: Actor) -> RestaurantTableRepository:
        return RestaurantTableRepository(self.session, actor.scope)

    def _stations(self, actor: Actor) -> StationRepository:
        return StationRepository(self.session, actor.scope)

    def _taxes(self, actor: Actor) -> TaxGroupRepository:
        return TaxGroupRepository(self.session, actor.scope)

    # ------------------------------------------------------------------ the restaurant

    async def get_restaurant(self, actor: Actor) -> Restaurant:
        restaurant = await self._restaurant(actor).get()
        if restaurant is None:
            # Only reachable if the restaurant was deleted between minting the token and using it.
            raise NotFoundError("restaurant.not_found", "This restaurant no longer exists.")
        return restaurant

    async def update_restaurant(self, actor: Actor, request: RestaurantUpdateRequest) -> Restaurant:
        restaurant = await self._restaurant(actor).get_for_update()
        if restaurant is None:
            raise NotFoundError("restaurant.not_found", "This restaurant no longer exists.")

        changes = request.model_dump(exclude_unset=True)
        # The theme is configuration and lives in `settings`, not in a column of its own. Pulled out
        # here so the loop below only ever sets real columns — assigning `restaurant.theme` would
        # silently do nothing, which is the quietest possible way to lose a setting.
        theme = changes.pop("theme", None)
        if "timezone" in changes and changes["timezone"] is not None:
            _require_known_timezone(changes["timezone"])
        if "currency" in changes and changes["currency"] is not None:
            changes["currency"] = _require_currency_code(changes["currency"])

        before = {field: getattr(restaurant, field) for field in changes}
        for field, value in changes.items():
            setattr(restaurant, field, value)
        if theme is not None:
            # Replaced whole rather than merged: the client sends the complete theme settings, so a
            # removed festive window is expressible. A merge would make deletion impossible.
            #
            # Reassigned rather than mutated, because SQLAlchemy does not track mutation inside a
            # JSONB dict — `settings["theme"] = ...` would flush nothing and the save would appear
            # to succeed while changing nothing at all.
            restaurant.settings = {**restaurant.settings, "theme": _jsonable_theme(theme)}
        await self.session.flush()

        audited = {field for field in changes if field in _AUDITED_SETTINGS}
        if audited:
            await self._audit(
                actor,
                action="restaurant.settings_changed",
                entity_type="restaurant",
                entity_id=restaurant.id,
                old_value={field: before[field] for field in audited},
                new_value={field: changes[field] for field in audited},
            )
        return restaurant

    # ------------------------------------------------------------------ dining areas

    async def list_dining_areas(
        self,
        actor: Actor,
        *,
        include_inactive: bool = False,
        limit: int | None = None,
        after: uuid.UUID | None = None,
    ) -> Sequence[DiningArea]:
        return await self._areas(actor).list_all(
            include_inactive=include_inactive, limit=limit, after=after
        )

    async def create_dining_area(
        self, actor: Actor, request: DiningAreaCreateRequest
    ) -> DiningArea:
        areas = self._areas(actor)
        if await areas.name_exists(request.name):
            raise ConflictError(
                "dining_area.name_taken",
                f"This restaurant already has an area called {request.name!r}.",
            )
        area = DiningArea(
            restaurant_id=actor.restaurant_id,
            name=request.name,
            seq=request.seq if request.seq is not None else await areas.next_seq(),
            is_active=True,
        )
        self.session.add(area)
        await self.session.flush()
        return area

    async def update_dining_area(
        self, actor: Actor, area_id: uuid.UUID, request: DiningAreaUpdateRequest
    ) -> DiningArea:
        areas = self._areas(actor)
        area = await areas.get(area_id)
        if area is None:
            raise NotFoundError("dining_area.not_found", "That dining area does not exist.")

        changes = request.model_dump(exclude_unset=True)
        if changes.get("name") is not None and await areas.name_exists(
            changes["name"], excluding=area_id
        ):
            raise ConflictError(
                "dining_area.name_taken",
                f"This restaurant already has an area called {changes['name']!r}.",
            )
        if changes.get("is_active") is False:
            # Refusing with the count, rather than refusing: "move or deactivate its 6 tables first"
            # tells someone what to do next, and "cannot deactivate" does not.
            occupied = await self._tables(actor).count_in_area(area_id)
            if occupied:
                raise ConflictError(
                    "dining_area.has_tables",
                    f"Move or deactivate this area's {occupied} table(s) first. Tables are never "
                    "deleted, so an order taken here last year still resolves.",
                    details={"active_tables": occupied},
                )

        for field, value in changes.items():
            if value is not None:
                setattr(area, field, value)
        await self.session.flush()
        return area

    # ------------------------------------------------------------------ tables

    async def list_tables(
        self,
        actor: Actor,
        *,
        dining_area_id: uuid.UUID | None = None,
        include_inactive: bool = False,
        limit: int | None = None,
        after: uuid.UUID | None = None,
    ) -> Sequence[RestaurantTable]:
        return await self._tables(actor).list_all(
            dining_area_id=dining_area_id,
            include_inactive=include_inactive,
            limit=limit,
            after=after,
        )

    async def create_table(self, actor: Actor, request: TableCreateRequest) -> RestaurantTable:
        tables = self._tables(actor)
        await self._require_area(actor, request.dining_area_id)
        if await tables.code_exists(request.code):
            raise ConflictError(
                "table.code_taken", f"This restaurant already has a table {request.code!r}."
            )
        table = RestaurantTable(
            restaurant_id=actor.restaurant_id,
            dining_area_id=request.dining_area_id,
            code=request.code,
            seats=request.seats,
            status=TableStatus.FREE,
            is_active=True,
        )
        self.session.add(table)
        await self.session.flush()
        return table

    async def update_table(
        self, actor: Actor, table_id: uuid.UUID, request: TableUpdateRequest
    ) -> RestaurantTable:
        tables = self._tables(actor)
        table = await tables.get(table_id)
        if table is None:
            raise NotFoundError("table.not_found", "That table does not exist.")

        changes = request.model_dump(exclude_unset=True)
        if changes.get("dining_area_id") is not None:
            # Re-checked on every move, not only on create. A table moved into another tenant's
            # area would be the tenant-isolation bug this module exists to avoid.
            await self._require_area(actor, changes["dining_area_id"])
        if changes.get("code") is not None and await tables.code_exists(
            changes["code"], excluding=table_id
        ):
            raise ConflictError(
                "table.code_taken", f"This restaurant already has a table {changes['code']!r}."
            )

        for field, value in changes.items():
            if value is not None:
                setattr(table, field, value)
        await self.session.flush()
        return table

    async def _require_area(self, actor: Actor, area_id: uuid.UUID) -> DiningArea:
        """The area a table is being put in must belong to *this* restaurant and be usable.

        404 rather than 403 for an area in another restaurant: the repository scopes the lookup, so
        a real id belonging to someone else is indistinguishable from one that does not exist —
        which is the point. Answering 403 would confirm the id is real.
        """
        area = await self._areas(actor).get(area_id)
        if area is None:
            raise NotFoundError("dining_area.not_found", "That dining area does not exist.")
        if not area.is_active:
            raise ConflictError(
                "dining_area.inactive", f"{area.name!r} is deactivated, so it takes no new tables."
            )
        return area

    # ------------------------------------------------------------------ stations

    async def list_stations(
        self,
        actor: Actor,
        *,
        include_inactive: bool = False,
        limit: int | None = None,
        after: uuid.UUID | None = None,
    ) -> Sequence[Station]:
        return await self._stations(actor).list_all(
            include_inactive=include_inactive, limit=limit, after=after
        )

    async def create_station(self, actor: Actor, request: StationCreateRequest) -> Station:
        stations = self._stations(actor)
        if await stations.code_exists(request.code):
            raise ConflictError(
                "station.code_taken",
                f"This restaurant already has a station {request.code!r}. Codes are permanent "
                "because the menu routes dishes by them.",
            )
        station = Station(
            restaurant_id=actor.restaurant_id,
            code=request.code,
            name=request.name,
            seq=request.seq if request.seq is not None else await stations.next_seq(),
            is_active=True,
        )
        self.session.add(station)
        await self.session.flush()
        return station

    async def update_station(
        self, actor: Actor, station_id: uuid.UUID, request: StationUpdateRequest
    ) -> Station:
        station = await self._stations(actor).get(station_id)
        if station is None:
            raise NotFoundError("station.not_found", "That station does not exist.")
        # No `code` branch: the schema has no such field. Renaming a code would orphan the menu
        # routing that points at it, so the display name is editable and the identifier is not.
        for field, value in request.model_dump(exclude_unset=True).items():
            if value is not None:
                setattr(station, field, value)
        await self.session.flush()
        return station

    # ------------------------------------------------------------------ tax

    async def list_tax_groups(
        self, actor: Actor, *, limit: int | None = None, after: uuid.UUID | None = None
    ) -> Sequence[TaxGroup]:
        return await self._taxes(actor).list_all(limit=limit, after=after)

    async def create_tax_group(self, actor: Actor, request: TaxGroupCreateRequest) -> TaxGroup:
        """Create a rate, or replace one.

        With `supersedes_id`, the old row is closed the day before the new one opens — in this one
        call, so the two cannot end up overlapping or leaving a gap between them.
        """
        today = await self.business_today(actor)
        if request.effective_from < today:
            raise AppError(
                "tax_group.back_dated",
                f"A rate cannot start before today ({today.isoformat()}). Tax already charged and "
                "reported must not move; set a future date instead.",
                details={"business_date": today.isoformat()},
                status_code=422,
            )

        superseded: TaxGroup | None = None
        if request.supersedes_id is not None:
            superseded = await self._taxes(actor).get_for_update(request.supersedes_id)
            if superseded is None:
                raise NotFoundError("tax_group.not_found", "That tax rate does not exist.")
            if superseded.effective_to is not None:
                raise ConflictError(
                    "tax_group.already_superseded",
                    f"{superseded.name!r} already ended on {superseded.effective_to.isoformat()}.",
                )
            if request.effective_from <= superseded.effective_from:
                raise AppError(
                    "tax_group.starts_too_early",
                    f"A replacement must start after the rate it replaces, which began on "
                    f"{superseded.effective_from.isoformat()}.",
                    status_code=422,
                )

        replacement = TaxGroup(
            restaurant_id=actor.restaurant_id,
            name=request.name,
            rate=request.rate,
            is_inclusive=request.is_inclusive,
            effective_from=request.effective_from,
            effective_to=None,
        )
        self.session.add(replacement)
        if superseded is not None:
            # The day before, so the two periods meet exactly. Same day would mean two live rates
            # on one date, and an order line would take whichever the query happened to return.
            superseded.effective_to = request.effective_from - _ONE_DAY
        await self.session.flush()

        await self._audit(
            actor,
            action="tax_group.created",
            entity_type="tax_group",
            entity_id=replacement.id,
            old_value=(
                None
                if superseded is None
                else {"id": superseded.id, "rate": superseded.rate, "name": superseded.name}
            ),
            new_value={"rate": replacement.rate, "effective_from": replacement.effective_from},
        )
        return replacement

    async def rename_tax_group(self, actor: Actor, tax_group_id: uuid.UUID, name: str) -> TaxGroup:
        """The only edit a tax row allows. The rate and the dates are immutable once the row exists
        — see the schema, which offers no field for them."""
        group = await self._taxes(actor).get(tax_group_id)
        if group is None:
            raise NotFoundError("tax_group.not_found", "That tax rate does not exist.")
        group.name = name
        await self.session.flush()
        return group

    # ------------------------------------------------------------------ shared

    async def business_today(self, actor: Actor) -> date:
        """The restaurant's today, which is not the server's.

        At 01:00 in Pune the business date is still yesterday (ADR 0004). A rate validated against
        the server's UTC date would refuse a legitimate "today" for five and a half hours a day, and
        accept a back-dated one for the same window.
        """
        restaurant = await self.get_restaurant(actor)
        return business_date_of(
            datetime.now(UTC), restaurant.timezone, restaurant.business_day_start
        )

    async def _audit(
        self,
        actor: Actor,
        *,
        action: str,
        entity_type: str,
        entity_id: uuid.UUID,
        old_value: dict[str, Any] | None,
        new_value: dict[str, Any] | None,
    ) -> None:
        self.session.add(
            AuditLog(
                restaurant_id=actor.restaurant_id,
                actor_employee_id=actor.employee_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                old_value=None if old_value is None else _jsonable(old_value),
                new_value=None if new_value is None else _jsonable(new_value),
                occurred_at=datetime.now(UTC),
            )
        )
        await self.session.flush()


def _jsonable_theme(theme: dict[str, Any]) -> dict[str, Any]:
    """`date` does not survive a jsonb round trip; the windows carry two of them."""
    return {
        "default": theme.get("default"),
        "schedule": [
            {
                "theme": window["theme"],
                "starts_on": _one_jsonable(window["starts_on"]),
                "ends_on": _one_jsonable(window["ends_on"]),
            }
            for window in theme.get("schedule", [])
        ],
    }


def read_theme(settings: dict[str, Any]) -> dict[str, Any]:
    """The theme block out of `settings`, with the shape the schema expects.

    Tolerant on the way out and strict on the way in: a restaurant seeded before this existed has no
    `theme` key at all, and the settings screen must render for it rather than 500.
    """
    stored = settings.get("theme")
    if not isinstance(stored, dict):
        return {"default": None, "schedule": []}
    schedule = stored.get("schedule")
    return {
        "default": stored.get("default"),
        "schedule": schedule if isinstance(schedule, list) else [],
    }


def _require_known_timezone(timezone: str) -> None:
    """Refuse a zone `zoneinfo` does not know.

    Stored as typed, this surfaces much later and much worse: `business_date_of` raises on the next
    order the restaurant takes, in the middle of service, with nothing on screen connecting it to a
    settings change made last week.
    """
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise AppError(
            "restaurant.unknown_timezone",
            f"{timezone!r} is not a known timezone. Use an IANA name such as 'Asia/Kolkata'.",
            status_code=422,
        ) from error


def _require_currency_code(currency: str) -> str:
    """ISO 4217 is three letters, upper case. Accepted lower case and normalised, because the
    alternative is a validation error for typing `inr`."""
    code = currency.strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise AppError(
            "restaurant.bad_currency",
            f"{currency!r} is not a currency code. Use three letters, such as 'INR'.",
            status_code=422,
        )
    return code


def _jsonable(values: dict[str, Any]) -> dict[str, Any]:
    """dates, times, Decimals and UUIDs do not survive a jsonb round trip on their own."""
    return {key: _one_jsonable(value) for key, value in values.items()}


def _one_jsonable(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
