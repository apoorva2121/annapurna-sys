"""The menu, built by M03's persona filter and routed for the first time here.

Either scope reads it: somebody holding a bill token is sitting at a table too.

**`ETag` and `If-None-Match`**, which M03 already built for the staff tree — `version` is "the
`ETag` a conditional GET compares against". `docs/security.md` asks for guest menu responses to be
"cached and cheap", and this is what makes them so: the menu is the most-requested thing on this
surface and it changes a few times a week. A 304 also costs the rate limiter nothing a diner would
notice, which matters on the one endpoint a whole restaurant hits at once.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response, status

from app.api.guest_deps import GuestDep, GuestSessionDep
from app.core.rate_limit import rate_limit
from app.schemas.guest import GuestMenuResponse
from app.services.menu import MenuService
from app.services.menu_tree import guest_tree

router = APIRouter()


@router.get("/menu", response_model=GuestMenuResponse, dependencies=[Depends(rate_limit("read"))])
async def guest_menu(
    session: GuestSessionDep,
    scope: GuestDep,
    response: Response,
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
) -> GuestMenuResponse | Response:
    version, categories = await MenuService(session).load_guest_tree(scope.restaurant_id)
    etag = f'W/"{version}"'
    if if_none_match == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
    response.headers["ETag"] = etag
    return guest_tree(version, categories)
