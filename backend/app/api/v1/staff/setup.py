"""Restaurant setup endpoints: settings, the floor, the stations, the tax rates.

Every handler is authorise-call-shape and nothing else (engineering-standards §1). All of them sit
behind one permission, `restaurant.configure`, held by owner and admin only — a manager runs a
shift, and changing what a day means or what tax is charged is not running a shift.

`from_attributes` on the response schemas is what keeps this file short: the service returns the ORM
object and the schema names the fields that may leave the building, so a column added to a model
later cannot silently appear in a response.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import SessionDep, require_permission
from app.core.actor import Actor
from app.core.permissions import PermissionCode
from app.models.tenancy import Restaurant
from app.repositories.base import DEFAULT_PAGE_SIZE
from app.schemas.setup import (
    BusyWindowSettings,
    DiningAreaCreateRequest,
    DiningAreaListResponse,
    DiningAreaReorderRequest,
    DiningAreaResponse,
    DiningAreaUpdateRequest,
    RestaurantResponse,
    RestaurantUpdateRequest,
    StationCreateRequest,
    StationListResponse,
    StationResponse,
    StationUpdateRequest,
    TableCreateRequest,
    TableListResponse,
    TableResponse,
    TableSettingsBlock,
    TableStatusRequest,
    TableUpdateRequest,
    TaxGroupCreateRequest,
    TaxGroupListResponse,
    TaxGroupResponse,
    TaxGroupUpdateRequest,
    TaxRateCreateRequest,
    ThemeSettings,
)
from app.services.floor_rules import read_table_settings
from app.services.setup import SetupService, read_theme

router = APIRouter(tags=["setup"])

_ConfigureDep = Annotated[Actor, Depends(require_permission(PermissionCode.RESTAURANT_CONFIGURE))]

_LimitDep = Annotated[int | None, Query(ge=1, le=100)]
_CursorDep = Annotated[uuid.UUID | None, Query()]


def _next_cursor(items: list[object], limit: int | None) -> uuid.UUID | None:
    """Only offer a cursor when the page was full.

    Otherwise the client makes one more round trip to learn what it already knows — and a client
    that stops only on an empty page is the client that shows fifty rows and hides the rest.
    """
    if len(items) < (limit or DEFAULT_PAGE_SIZE):
        return None
    last = items[-1]
    return getattr(last, "id", None)


# --------------------------------------------------------------------------- the restaurant


def _restaurant_response(restaurant: Restaurant) -> RestaurantResponse:
    """The theme lives in `settings`, so it is assembled rather than read off the model.

    `ThemeSettings.model_validate` rather than `model_copy(update=...)`: `model_copy` assigns
    without validating, so the response would carry a bare dict where the schema promises a model —
    which serialises to the right JSON today and is a lie the type system cannot see.
    """
    body = RestaurantResponse.model_validate(restaurant)
    body.theme = ThemeSettings.model_validate(read_theme(restaurant.settings))
    # Read through the same rules the floor and settlement use, so the screen shows what actually
    # applies — including the five-minute default for a restaurant that never saved one.
    rules = read_table_settings(restaurant.settings)
    body.tables = TableSettingsBlock(
        cleaning_minutes=rules.cleaning_minutes,
        busy_windows=[
            BusyWindowSettings(starts=window.starts, ends=window.ends)
            for window in rules.busy_windows
        ],
    )
    return body


@router.get("/restaurant", response_model=RestaurantResponse)
async def get_restaurant(actor: _ConfigureDep, session: SessionDep) -> RestaurantResponse:
    restaurant = await SetupService(session).get_restaurant(actor)
    return _restaurant_response(restaurant)


@router.patch("/restaurant", response_model=RestaurantResponse)
async def update_restaurant(
    actor: _ConfigureDep, session: SessionDep, request: RestaurantUpdateRequest
) -> RestaurantResponse:
    restaurant = await SetupService(session).update_restaurant(actor, request)
    await session.commit()
    return _restaurant_response(restaurant)


# --------------------------------------------------------------------------- dining areas


@router.get("/setup/dining-areas", response_model=DiningAreaListResponse)
async def list_dining_areas(
    actor: _ConfigureDep,
    session: SessionDep,
    include_inactive: Annotated[bool, Query()] = False,
    limit: _LimitDep = None,
    cursor: _CursorDep = None,
) -> DiningAreaListResponse:
    areas = await SetupService(session).list_dining_areas(
        actor, include_inactive=include_inactive, limit=limit, after=cursor
    )
    items = [DiningAreaResponse.model_validate(area) for area in areas]
    return DiningAreaListResponse(items=items, next_cursor=_next_cursor(list(areas), limit))


@router.post(
    "/setup/dining-areas", response_model=DiningAreaResponse, status_code=status.HTTP_201_CREATED
)
async def create_dining_area(
    actor: _ConfigureDep, session: SessionDep, request: DiningAreaCreateRequest
) -> DiningAreaResponse:
    area = await SetupService(session).create_dining_area(actor, request)
    await session.commit()
    return DiningAreaResponse.model_validate(area)


@router.post("/setup/dining-areas/reorder", response_model=DiningAreaListResponse)
async def reorder_dining_areas(
    actor: _ConfigureDep, session: SessionDep, request: DiningAreaReorderRequest
) -> DiningAreaListResponse:
    """The whole floor plan's order in one request. Two PATCHes could half-fail and leave two areas
    on one position (backlog-issues B3)."""
    areas = await SetupService(session).reorder_dining_areas(actor, request.area_ids)
    await session.commit()
    return DiningAreaListResponse(items=[DiningAreaResponse.model_validate(area) for area in areas])


@router.patch("/setup/dining-areas/{area_id}", response_model=DiningAreaResponse)
async def update_dining_area(
    actor: _ConfigureDep,
    session: SessionDep,
    area_id: uuid.UUID,
    request: DiningAreaUpdateRequest,
) -> DiningAreaResponse:
    area = await SetupService(session).update_dining_area(actor, area_id, request)
    await session.commit()
    return DiningAreaResponse.model_validate(area)


# --------------------------------------------------------------------------- tables


@router.get("/setup/tables", response_model=TableListResponse)
async def list_tables(
    actor: _ConfigureDep,
    session: SessionDep,
    dining_area_id: Annotated[uuid.UUID | None, Query()] = None,
    include_inactive: Annotated[bool, Query()] = False,
    limit: _LimitDep = None,
    cursor: _CursorDep = None,
) -> TableListResponse:
    tables = await SetupService(session).list_tables(
        actor,
        dining_area_id=dining_area_id,
        include_inactive=include_inactive,
        limit=limit,
        after=cursor,
    )
    items = [TableResponse.model_validate(table) for table in tables]
    return TableListResponse(items=items, next_cursor=_next_cursor(list(tables), limit))


@router.post("/setup/tables", response_model=TableResponse, status_code=status.HTTP_201_CREATED)
async def create_table(
    actor: _ConfigureDep, session: SessionDep, request: TableCreateRequest
) -> TableResponse:
    table = await SetupService(session).create_table(actor, request)
    await session.commit()
    return TableResponse.model_validate(table)


@router.patch("/setup/tables/{table_id}", response_model=TableResponse)
async def update_table(
    actor: _ConfigureDep, session: SessionDep, table_id: uuid.UUID, request: TableUpdateRequest
) -> TableResponse:
    table = await SetupService(session).update_table(actor, table_id, request)
    await session.commit()
    return TableResponse.model_validate(table)


@router.post("/setup/tables/{table_id}/status", response_model=TableResponse)
async def set_table_status(
    actor: _ConfigureDep, session: SessionDep, table_id: uuid.UUID, request: TableStatusRequest
) -> TableResponse:
    table = await SetupService(session).set_table_status(actor, table_id, request.status)
    await session.commit()
    return TableResponse.model_validate(table)


# --------------------------------------------------------------------------- stations


@router.get("/setup/stations", response_model=StationListResponse)
async def list_stations(
    actor: _ConfigureDep,
    session: SessionDep,
    include_inactive: Annotated[bool, Query()] = False,
    limit: _LimitDep = None,
    cursor: _CursorDep = None,
) -> StationListResponse:
    stations = await SetupService(session).list_stations(
        actor, include_inactive=include_inactive, limit=limit, after=cursor
    )
    items = [StationResponse.model_validate(station) for station in stations]
    return StationListResponse(items=items, next_cursor=_next_cursor(list(stations), limit))


@router.post("/setup/stations", response_model=StationResponse, status_code=status.HTTP_201_CREATED)
async def create_station(
    actor: _ConfigureDep, session: SessionDep, request: StationCreateRequest
) -> StationResponse:
    station = await SetupService(session).create_station(actor, request)
    await session.commit()
    return StationResponse.model_validate(station)


@router.patch("/setup/stations/{station_id}", response_model=StationResponse)
async def update_station(
    actor: _ConfigureDep,
    session: SessionDep,
    station_id: uuid.UUID,
    request: StationUpdateRequest,
) -> StationResponse:
    station = await SetupService(session).update_station(actor, station_id, request)
    await session.commit()
    return StationResponse.model_validate(station)


# --------------------------------------------------------------------------- tax


@router.get("/setup/tax-groups", response_model=TaxGroupListResponse)
async def list_tax_groups(
    actor: _ConfigureDep,
    session: SessionDep,
    limit: _LimitDep = None,
    cursor: _CursorDep = None,
) -> TaxGroupListResponse:
    """Includes superseded rows. An invoice from March cites the rate that was effective in March,
    and someone checking that invoice has to be able to see it."""
    groups = await SetupService(session).list_tax_groups(actor, limit=limit, after=cursor)
    items = [TaxGroupResponse.model_validate(group) for group in groups]
    return TaxGroupListResponse(items=items, next_cursor=_next_cursor(list(groups), limit))


@router.post(
    "/setup/tax-groups", response_model=TaxGroupResponse, status_code=status.HTTP_201_CREATED
)
async def create_tax_group(
    actor: _ConfigureDep, session: SessionDep, request: TaxGroupCreateRequest
) -> TaxGroupResponse:
    """A tax class and the rate it charges from day one, created together.

    A group with no rate is a trap: a menu item could be attached to it and M07 would find nothing
    to charge at order time.
    """
    group = await SetupService(session).create_tax_group(actor, request)
    await session.commit()
    return TaxGroupResponse.model_validate(group)


@router.patch("/setup/tax-groups/{tax_group_id}", response_model=TaxGroupResponse)
async def update_tax_group(
    actor: _ConfigureDep,
    session: SessionDep,
    tax_group_id: uuid.UUID,
    request: TaxGroupUpdateRequest,
) -> TaxGroupResponse:
    """Name and active flag. Never the code — `menu_item_variant` and `seed/operations.yaml` join
    on it — and never a rate, which is a new row through the endpoint below."""
    group = await SetupService(session).update_tax_group(actor, tax_group_id, request)
    await session.commit()
    return TaxGroupResponse.model_validate(group)


@router.post(
    "/setup/tax-groups/{tax_group_id}/rates",
    response_model=TaxGroupResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_tax_rate(
    actor: _ConfigureDep,
    session: SessionDep,
    tax_group_id: uuid.UUID,
    request: TaxRateCreateRequest,
) -> TaxGroupResponse:
    """Charge a new rate from a future date. The rate in force until then is closed the day before,
    so the two periods meet exactly and no menu item is repointed.

    Returns the whole group, because what the caller needs to see is the new period *beside* the one
    it replaced — a bare 201 for the new row hides the half of the change that matters.
    """
    group = await SetupService(session).add_tax_rate(actor, tax_group_id, request)
    await session.commit()
    return TaxGroupResponse.model_validate(group)
