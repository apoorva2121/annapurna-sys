"""One place decides whether two phone numbers are the same person.

`98765 43210`, `+91 98765 43210`, `09876543210` and `+919876543210` are one customer or four, and
which one it is must not depend on who was standing at the counter. `customer.phone` is the natural
key and carries a unique constraint, so the normalisation *is* the identity rule.

**Deliberately forgiving.** This does not validate that a number could be dialled. A validator
strict enough to be useful would refuse a real number at a busy counter — a landline, a number with
an extension, a foreign visitor's number — and the cost of refusing a real customer's number is
higher than the cost of storing an odd one. What it guarantees is only this: two spellings of the
same digits become the same string.

**The `+91` question, answered once.** An Indian mobile number is ten digits and the country code is
not part of what anybody says out loud. So a ten-digit number is stored as ten digits, a number
written with `+91` or a leading `0` in front of ten digits is stored as those ten, and anything else
is stored as its digits with a leading `+` if it had one. A guest typing their own number into the
feedback form and a manager typing it at the counter then reach the same row, which is the entire
point.
"""

from __future__ import annotations

import re

_NON_DIGIT = re.compile(r"[^0-9]")

# The national significant number for an Indian mobile. `+91` and a leading trunk `0` are both
# prefixes people write and nobody says.
_INDIAN_LENGTH = 10


def normalise_phone(raw: str) -> str:
    """The stored form. Never call `==` on a phone number that has not been through here."""
    had_plus = raw.strip().startswith("+")
    digits = _NON_DIGIT.sub("", raw)

    if len(digits) == _INDIAN_LENGTH:
        return digits
    if len(digits) == _INDIAN_LENGTH + 2 and digits.startswith("91"):
        return digits[2:]
    if len(digits) == _INDIAN_LENGTH + 1 and digits.startswith("0"):
        return digits[1:]
    # Something else — a landline, a foreign number, a number with an extension. Kept as typed,
    # minus the punctuation, because refusing it would refuse a real customer.
    return f"+{digits}" if had_plus else digits


def masked(phone: str) -> str:
    """For a screen that has to prove it holds the right number without printing it in full.

    Not for logs: a log line carries no phone number at all, masked or otherwise (Definition of
    Done, "no PII in logs"). This exists for the confirmation on the erasure screen, where somebody
    is about to destroy a person's details and should be able to see they have the right person.
    """
    if len(phone) <= 4:
        return "•" * len(phone)
    return "•" * (len(phone) - 4) + phone[-4:]
