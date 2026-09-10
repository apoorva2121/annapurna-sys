"""UUIDv7 generation, per ADR 0008.

Not in the standard library at 3.13, and deliberately not a dependency either — RFC 9562 §5.7 is
forty lines and a supply-chain risk is a poor trade for that.

Why v7 rather than v4: the four largest tables in this product (stock_movement, order_line, message,
audit_log) are append-heavy. Random v4 ids scatter inserts across the whole B-tree, causing page
splits and index bloat that grows with table size. A v7 id leads with a millisecond timestamp, so
inserts append at the right-hand edge like a sequence, while keeping what we want from a UUID:
generated without a database round trip, safe in a URL, and leaking no row counts.

The counter in `rand_a` is what makes ids generated inside one millisecond still sort in creation
order (RFC 9562 §6.2, method 1). That turns the primary key into a valid cursor for pagination, and
makes "what happened next" answerable on an audit trail without a tiebreaker column.
"""

from __future__ import annotations

import secrets
import threading
import time
from uuid import UUID

_COUNTER_BITS = 12
_COUNTER_MAX = (1 << _COUNTER_BITS) - 1

_lock = threading.Lock()
_last_timestamp_ms = -1
_counter = 0


def _next_timestamp_and_counter() -> tuple[int, int]:
    """The only mutable state in the module, so it is the only thing that needs the lock."""
    global _last_timestamp_ms, _counter

    with _lock:
        now_ms = time.time_ns() // 1_000_000
        if now_ms > _last_timestamp_ms:
            _last_timestamp_ms = now_ms
            # Seeded below the ceiling rather than at zero: a fresh random start each millisecond
            # keeps ids from being guessable while leaving room to count upward.
            _counter = secrets.randbits(_COUNTER_BITS) >> 1
        elif _counter >= _COUNTER_MAX:
            # More than ~2048 ids in one millisecond. Borrow from the next millisecond rather than
            # wrap the counter, which would break ordering.
            _last_timestamp_ms += 1
            _counter = 0
        else:
            _counter += 1
        return _last_timestamp_ms, _counter


def uuid7() -> UUID:
    """A time-ordered UUID. Successive calls sort in creation order, always."""
    timestamp_ms, counter = _next_timestamp_and_counter()

    #  48 bits timestamp | 4 version | 12 counter | 2 variant | 62 random
    value = (timestamp_ms & 0xFFFF_FFFF_FFFF) << 80
    value |= 0x7 << 76
    value |= (counter & _COUNTER_MAX) << 64
    value |= 0b10 << 62
    value |= secrets.randbits(62)
    return UUID(int=value)
