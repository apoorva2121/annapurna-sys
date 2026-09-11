"""The N+1 guard every later module uses.

Query counts are asserted, not eyeballed. This is the single most common performance defect in a
CRUD application and it is entirely preventable (docs/engineering-standards.md §3).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, event
from sqlalchemy.ext.asyncio import AsyncEngine


class QueryCount:
    """How many statements ran inside the block. Mutable, because the value is only final once the
    block has exited."""

    __slots__ = ("count",)

    def __init__(self) -> None:
        self.count = 0


def _sync_engine(engine: AsyncEngine | Engine) -> Engine:
    # Tests reach an engine two ways: an AsyncEngine they created, or the sync Engine behind the
    # session fixture's connection. Both end up at the same event target.
    return engine.sync_engine if isinstance(engine, AsyncEngine) else engine


@contextmanager
def count_queries(engine: AsyncEngine | Engine) -> Iterator[QueryCount]:
    """Count the statements a block issues.

    Prefer this over a fixed budget when the property under test is a *shape* — "the same number of
    queries whatever the page size" — rather than a number. A budget of six passes for a page of
    five rows while still hiding a query per row.
    """
    counter = QueryCount()
    target = _sync_engine(engine)

    def _count(*_args: Any, **_kwargs: Any) -> None:
        counter.count += 1

    event.listen(target, "before_cursor_execute", _count)
    try:
        yield counter
    finally:
        event.remove(target, "before_cursor_execute", _count)


@contextmanager
def assert_max_queries(engine: AsyncEngine | Engine, limit: int) -> Iterator[None]:
    """Fail if the block issues more than `limit` statements."""
    with count_queries(engine) as counter:
        yield
    if counter.count > limit:
        raise AssertionError(f"expected at most {limit} queries, {counter.count} were issued")
