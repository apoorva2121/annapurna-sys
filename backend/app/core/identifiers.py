"""A login, stored one way (backlog-issues B4, guardrail G-18).

`98765 43210`, `+91 98765 43210` and `09876543210` are one phone number; `Ravi@Gmail.com` is
`ravi@gmail.com`. Stored as typed they were different logins (P1-7). Every login is normalised here,
at the boundary — creating one, signing in with one, seeding one — and the database's
per-organization uniqueness then holds for the person rather than for the spelling.

**India is the default country** because every restaurant this product serves today is in India. A
number with any other country code is kept as given. Something that is neither a phone number nor an
email is returned as typed: at sign-in it matches nobody, and creating a login with it is refused.
"""

from __future__ import annotations

import re

_SEPARATORS = re.compile(r"[\s\-().]")
_INDIA = "+91"


def normalise_identifier(raw: str) -> str:
    """Lowercase an email; write a phone number as E.164, adding +91 when no country is given."""
    value = raw.strip()
    if "@" in value:
        return value.lower()
    compact = _SEPARATORS.sub("", value)
    if compact.startswith("+"):
        digits = compact[1:]
        return f"+{digits}" if digits.isdigit() and 8 <= len(digits) <= 15 else value
    if not compact.isdigit():
        return value
    if compact.startswith("00") and 8 <= len(compact) - 2 <= 15:
        return f"+{compact[2:]}"
    if len(compact) == 10:
        return f"{_INDIA}{compact}"
    if len(compact) == 11 and compact.startswith("0"):
        return f"{_INDIA}{compact[1:]}"
    if len(compact) == 12 and compact.startswith("91"):
        return f"+{compact}"
    return value


def is_email(value: str) -> bool:
    local, _, domain = value.partition("@")
    return bool(local) and "." in domain and " " not in value


def is_phone(value: str) -> bool:
    """A normalised phone number: `+` and 8 to 15 digits."""
    return value.startswith("+") and value[1:].isdigit() and 8 <= len(value) - 1 <= 15
