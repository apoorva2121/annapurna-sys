"""UUIDv7 is a performance decision (ADR 0008), so its ordering property is the thing to test.

A v4 id would satisfy "is a unique uuid" just as well. What earns v7 is that ids generated later
sort after ids generated earlier, which keeps inserts appending to the right-hand edge of the index
instead of scattering across it. Test the ordering, or the tests would pass with v4 and the reason
for the decision would quietly disappear.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from unittest import mock
from uuid import UUID

from app.core import ids
from app.core.ids import uuid7


def test_is_a_version_7_uuid() -> None:
    assert uuid7().version == 7


def test_uses_the_rfc_4122_variant() -> None:
    # Bits 64-65 must be 0b10. Getting this wrong produces something that is not a UUID at all,
    # which Postgres will still happily store.
    assert (uuid7().int >> 62) & 0b11 == 0b10


def test_the_embedded_timestamp_is_now() -> None:
    before = time.time_ns() // 1_000_000
    embedded = uuid7().int >> 80
    after = time.time_ns() // 1_000_000
    assert before <= embedded <= after


def test_successive_ids_sort_in_creation_order() -> None:
    """The property the ADR is actually buying. Generated in a tight loop, so most of these land
    in the same millisecond — which is exactly the case a naive implementation gets wrong."""
    ids = [uuid7() for _ in range(1000)]
    assert ids == sorted(ids)


def test_ids_are_unique_under_concurrency() -> None:
    # Two workers in the same millisecond must not produce the same counter value.
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(lambda _: uuid7(), range(2000)))
    assert len(set(ids)) == len(ids)


def test_string_form_round_trips() -> None:
    generated = uuid7()
    assert UUID(str(generated)) == generated


def test_ordering_survives_the_counter_running_out_within_one_millisecond() -> None:
    """The counter holds ~2048 ids per millisecond. Past that the implementation borrows from the
    next millisecond, because wrapping the counter would emit an id that sorts *before* its
    predecessor — silently breaking both the index locality the ADR wants and any cursor built on
    the id. Reproduced by freezing the clock so every call lands in the same millisecond."""
    frozen_ms = 1_800_000_000_000

    with mock.patch("app.core.ids.time.time_ns", return_value=frozen_ms * 1_000_000):
        generated = [ids.uuid7() for _ in range(6000)]

    assert generated == sorted(generated)
    assert len(set(generated)) == len(generated)
    # Ids did move past the frozen millisecond rather than piling up inside it.
    assert (generated[-1].int >> 80) > frozen_ms
