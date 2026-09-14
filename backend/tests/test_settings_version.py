"""A settings save made from an out-of-date page is refused, not written over (backlog-issues B6).

Backlog row "Server-owned form state is never reconciled after a save". The settings screen copied
the server's values once and never again, and the theme is sent whole by design — so a festive
schedule saved in another tab was silently undone by the next Save anywhere, with a green "Saved"
over it. `restaurant.settings_version` counts saves of these settings, and a save carries the
version its page was read at.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_setup_endpoints import _auth, _token, _world

RESTAURANT = "/api/v1/staff/restaurant"


class TestTheSettingsVersion:
    async def test_a_save_answers_with_what_was_saved_and_the_next_version(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        read = (await api_client.get(RESTAURANT, headers=_auth(token))).json()

        saved = await api_client.patch(
            RESTAURANT,
            json={"currency": "inr", "settings_version": read["settings_version"]},
            headers=_auth(token),
        )

        assert saved.status_code == 200, saved.text
        assert saved.json()["currency"] == "INR"
        assert saved.json()["settings_version"] == read["settings_version"] + 1

    async def test_a_save_from_a_page_that_is_out_of_date_is_refused_and_changes_nothing(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        read = (await api_client.get(RESTAURANT, headers=_auth(token))).json()
        other_tab = await api_client.patch(
            RESTAURANT,
            json={"business_day_start": "04:30:00", "settings_version": read["settings_version"]},
            headers=_auth(token),
        )
        assert other_tab.status_code == 200, other_tab.text

        stale = await api_client.patch(
            RESTAURANT,
            json={"business_day_start": "06:00:00", "settings_version": read["settings_version"]},
            headers=_auth(token),
        )

        assert stale.status_code == 409, stale.text
        assert stale.json()["code"] == "restaurant.stale"
        assert stale.json()["details"]["current_version"] == read["settings_version"] + 1
        after = (await api_client.get(RESTAURANT, headers=_auth(token))).json()
        assert after["business_day_start"] == "04:30:00"
