"""Capture what the application really writes to its log.

Installed on the root logger with the *production* formatter and filter, so what a test asserts is
what production would emit — not pytest's own record format, which never sees the context
variables. Lifted out of `test_logging_context.py` when M08's middleware tests became its second
caller.
"""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from app.core.logging import JsonFormatter, RedactingFilter


@contextmanager
def captured_lines() -> Iterator[list[dict[str, Any]]]:
    """Every JSON line the application writes while the block runs, parsed, **in order**.

    The order matters to M08: a streaming response's access line must come *after* the body it
    describes, and the only way to see that is to keep the sequence.
    """
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactingFilter())
    root = logging.getLogger()
    root.addHandler(handler)
    lines: list[dict[str, Any]] = []
    try:
        yield lines
    finally:
        root.removeHandler(handler)
        lines.extend(json.loads(raw) for raw in stream.getvalue().splitlines() if raw.strip())
