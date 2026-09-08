"""Structured JSON logging with PII redaction installed at the handler.

The redaction filter sits on the *handler*, not on a logger, so no log call anywhere in the
codebase can bypass it (docs/observability.md §1). It is written in M00 — before a single customer
phone number exists — because retrofitting it after M10 means auditing every log call ever written.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

REDACTED = "[redacted]"
# Lives here rather than in main.py so the error handlers can use it without importing the app.
REQUEST_ID_HEADER = "X-Request-Id"
_MAX_DEPTH = 6

# Scrubbed wholesale by key name, per docs/observability.md §1.
# Log the customer_id, never the phone.
SENSITIVE_KEYS = frozenset(
    {
        "phone",
        "email",
        "full_name",
        "password",
        "token",
        "refresh_token",
        "gstin",
        "address",
    }
)

# Indian mobile numbers: ten digits opening 6-9, optionally +91/0091 prefixed. The three groupings
# are spelled out rather than allowing separators anywhere, because a permissive pattern also eats
# unrelated digit runs — and a log with every number redacted is as useless as one with none.
_CC = r"(?:(?:\+|00)?91[-\s]?)?"
_PHONE = re.compile(
    r"(?<!\d)(?:"
    rf"{_CC}[6-9]\d{{9}}"  # 9876543210
    rf"|{_CC}[6-9]\d{{4}}[-\s]\d{{5}}"  # 98765 43210
    rf"|{_CC}[6-9]\d{{2}}[-\s]\d{{3}}[-\s]\d{{4}}"  # 987 654 3210
    r")(?!\d)"
)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_GSTIN = re.compile(r"(?<![A-Z0-9])\d{2}[A-Z]{5}\d{4}[A-Z][A-Z0-9]Z[A-Z0-9](?![A-Z0-9])")

# Request-scoped context, attached to every line so per-tenant debugging is a filter, not a hunt.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
restaurant_id_var: ContextVar[str | None] = ContextVar("restaurant_id", default=None)
actor_id_var: ContextVar[str | None] = ContextVar("actor_id", default=None)

_RESERVED = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)


def redact_text(text: str) -> str:
    """Scrub PII patterns out of free text."""
    text = _EMAIL.sub(REDACTED, text)
    text = _GSTIN.sub(REDACTED, text)
    return _PHONE.sub(REDACTED, text)


def redact_value(key: str, value: Any, depth: int = 0) -> Any:
    """Scrub by key name first, then by pattern, recursing into structured fields."""
    if key.lower() in SENSITIVE_KEYS:
        return REDACTED
    if depth >= _MAX_DEPTH:
        return value
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: redact_value(str(k), v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_value(key, item, depth + 1) for item in value]
    return value


class RedactingFilter(logging.Filter):
    """Installed on the handler, so it cannot be bypassed by a new log call."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_text(record.getMessage())
        record.args = ()
        for key, value in list(record.__dict__.items()):
            if key not in _RESERVED:
                record.__dict__[key] = redact_value(key, value)
        return True


class JsonFormatter(logging.Formatter):
    """One event per line. A log you cannot filter is a log you will not read."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "msg": record.getMessage(),
        }
        for name, var in (
            ("request_id", request_id_var),
            ("restaurant_id", restaurant_id_var),
            ("actor_id", actor_id_var),
        ):
            value = var.get()
            if value is not None:
                payload[name] = value
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            # Tracebacks belong in the log, never in the response body.
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    """Replace root handlers with one redacting JSON handler on stdout."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactingFilter())

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level.upper())

    # uvicorn ships its own handlers; let them propagate to ours or they escape redaction.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
