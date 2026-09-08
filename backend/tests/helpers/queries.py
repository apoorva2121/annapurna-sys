"""The N+1 guard every later module uses.

Query counts are asserted, not eyeballed. This is the single most common performance defect in a
CRUD application and it is entirely preventable (docs/engineering-standards.md §3).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine


@contextmanager
def assert_max_queries(engine: AsyncEngine, limit: int) -> Iterator[None]:
    """Fail if the block issues more than `limit` statements."""
    count = 0

    def _count(*_args: Any, **_kwargs: Any) -> None:
        nonlocal count
        count += 1

    event.listen(engine.sync_engine, "before_cursor_execute", _count)
    try:
        yield
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _count)
    if count > limit:
        raise AssertionError(f"expected at most {limit} queries, {count} were issued")
