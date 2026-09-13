"""The rule for saving a whole order at once (backlog-issues B3).

A floor plan and a menu used to be reordered by swapping two rows' `seq` in two PATCHes. When the
second failed, two rows shared a position and nothing said so. A reorder is now one request naming
the new order, applied in one transaction — and refused whole when it is not a whole order.

"Whole" means **every active row exactly once**. Deactivated rows may be named, which is what a
screen sends while it is showing them, and are otherwise left where they are: a screen hiding them
must not be refused for not naming what it cannot see.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Collection, Iterable, Sequence

from app.core.errors import AppError


def require_whole_order(
    named: Sequence[uuid.UUID],
    known: Collection[uuid.UUID],
    active: Iterable[uuid.UUID],
    *,
    code: str,
    noun: str,
) -> None:
    """Refuse, in words, a new order that repeats a row, names one this restaurant does not have,
    or leaves an active one out. The same code for all three: the fix is the same — reload."""
    if len(set(named)) != len(named):
        raise AppError(code, f"Each {noun} can appear only once in the new order.", status_code=422)
    if any(row_id not in known for row_id in named):
        raise AppError(
            code,
            f"The new order names a {noun} this restaurant does not have. Reload and try again.",
            status_code=422,
        )
    missing = sorted(str(row_id) for row_id in set(active) - set(named))
    if missing:
        raise AppError(
            code,
            f"The new order leaves out {len(missing)} {noun}(s). Reload and try again.",
            status_code=422,
            details={"missing": missing},
        )


def renumber[Row](
    named: Sequence[uuid.UUID], rows: Sequence[Row], id_of: Callable[[Row], uuid.UUID]
) -> None:
    """Named rows take positions 0..n-1 in the order given; rows left unnamed (deactivated ones a
    screen was hiding) follow in their current order. Every row ends on its own `seq`, so a hidden
    row can never tie with a visible one."""
    position = {row_id: seq for seq, row_id in enumerate(named)}
    rest = [row for row in rows if id_of(row) not in position]
    for seq, row in enumerate(rest, start=len(named)):
        row.seq = seq  # type: ignore[attr-defined]
    for row in rows:
        if id_of(row) in position:
            row.seq = position[id_of(row)]  # type: ignore[attr-defined]
