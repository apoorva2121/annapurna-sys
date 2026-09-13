"""Plain-language sentences for the API's validation rules.

A validation error reaches a person, usually a restaurant manager halfway through a form.
Pydantic's own words describe the rule to a programmer, and for a format rule they *are* the
regular expression. So every problem gets a stable code a client can switch on and a sentence that
says what to type instead.

Found in the M03 manual pass on 2026-09-13: adding a menu section, a supplier and a station each
failed with "The request was not valid." and nothing a person could act on.
`tests/test_validation_messages.py` fails the build when a `pattern=` has no sentence here, and
when a sentence outlives its rule.

Codes (`docs/engineering-standards.md` §4 — stable strings, never rephrased):
`field.required` · `field.too_short` · `field.too_long` · `field.too_few` · `field.too_many` ·
`field.out_of_range` · `field.not_a_number` · `field.too_precise` · `field.format` ·
`field.choice` · `field.invalid_date` · `field.invalid_time` · `field.unknown` · `field.invalid`
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

# Keyed by the exact pattern a schema declares. A closed list such as `^(veg|non_veg|egg)$` needs no
# entry: `_choices` explains it mechanically.
PATTERN_MESSAGES: dict[str, str] = {
    r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$": (
        "Use the 15-character GSTIN, for example 27AAPFU0939F1ZV."
    ),
    r"^[1-9][0-9]{5}$": "Use the 6-digit PIN code, for example 411001.",
    # The first digit is the document type — `docs/compliance-rules.md` §A3.
    r"^[12][0-9]{13}$": (
        "Use the 14-digit FSSAI number. It starts with 1 for a licence or 2 for a registration."
    ),
    r"^[A-Z][A-Z0-9_]*$": (
        "Use capital letters, digits and underscores only, with no spaces, starting with a letter "
        "— for example VEG_STARTERS."
    ),
    r"^[a-z][a-z0-9_]*$": (
        "Use small letters, digits and underscores only, with no spaces, starting with a letter "
        "— for example tandoor."
    ),
}

_CHOICE = re.compile(r"^\^\(((?:[a-z0-9_]+\|)*[a-z0-9_]+)\)\$$")

_WHOLE_NUMBER = ("field.not_a_number", "Enter a whole number.")
_NUMBER = ("field.not_a_number", "Enter a number.")
_DATE = ("field.invalid_date", "Enter a valid date.")
_DATETIME = ("field.invalid_date", "Enter a valid date and time.")
_TIME = ("field.invalid_time", "Enter a valid time.")
_UNKNOWN = ("field.invalid", "This value is not valid.")

# Pydantic error type → (code, sentence). A sentence may name keys from the error's `ctx`.
_RULES: dict[str, tuple[str, str]] = {
    "missing": ("field.required", "This is required."),
    "string_too_long": ("field.too_long", "Use at most {max_length} characters."),
    "too_short": ("field.too_few", "Add at least {min_length}."),
    "too_long": ("field.too_many", "Use at most {max_length}."),
    "greater_than_equal": ("field.out_of_range", "Must be {ge} or more."),
    "greater_than": ("field.out_of_range", "Must be more than {gt}."),
    "less_than_equal": ("field.out_of_range", "Must be {le} or less."),
    "less_than": ("field.out_of_range", "Must be less than {lt}."),
    "int_parsing": _WHOLE_NUMBER,
    "int_type": _WHOLE_NUMBER,
    "int_from_float": _WHOLE_NUMBER,
    "decimal_parsing": _NUMBER,
    "decimal_type": _NUMBER,
    "float_parsing": _NUMBER,
    "float_type": _NUMBER,
    "finite_number": _NUMBER,
    "decimal_max_places": ("field.too_precise", "Use at most {decimal_places} decimal places."),
    "decimal_max_digits": ("field.too_precise", "Use at most {max_digits} digits."),
    "decimal_whole_digits": (
        "field.too_precise",
        "Use at most {whole_digits} digits before the decimal point.",
    ),
    "enum": ("field.choice", "Choose one of: {expected}."),
    "literal_error": ("field.choice", "Choose one of: {expected}."),
    "extra_forbidden": ("field.unknown", "This field is not accepted."),
    "uuid_parsing": ("field.invalid", "This is not a valid reference."),
    "uuid_type": ("field.invalid", "This is not a valid reference."),
    "bool_parsing": ("field.invalid", "Choose yes or no."),
    "bool_type": ("field.invalid", "Choose yes or no."),
    "string_type": ("field.invalid", "Enter text."),
    "date_parsing": _DATE,
    "date_type": _DATE,
    "date_from_datetime_parsing": _DATE,
    "datetime_parsing": _DATETIME,
    "datetime_type": _DATETIME,
    "datetime_from_date_parsing": _DATETIME,
    "timezone_aware": ("field.invalid_date", "Include the time zone with the date and time."),
    "time_parsing": _TIME,
    "time_type": _TIME,
}


def pattern_sentence(pattern: str) -> str:
    """What to type for a format rule, never the rule itself."""
    if pattern in PATTERN_MESSAGES:
        return PATTERN_MESSAGES[pattern]
    choice = _CHOICE.match(pattern)
    if choice is not None:
        return f"Choose one of: {', '.join(choice.group(1).split('|'))}."
    return "This is not in the expected format."


def describe(error: Mapping[str, Any]) -> tuple[str, str]:
    """One pydantic error as `(code, sentence)`."""
    kind = str(error.get("type", ""))
    ctx: dict[str, Any] = dict(error.get("ctx") or {})
    if kind == "string_too_short":
        minimum = ctx.get("min_length", 1)
        if minimum == 1:
            return "field.required", "This is required."
        return "field.too_short", f"Use at least {minimum} characters."
    if kind == "string_pattern_mismatch":
        return "field.format", pattern_sentence(str(ctx.get("pattern", "")))
    if kind == "value_error":
        # Raised by this codebase's own validators, whose messages are written for people already.
        return "field.invalid", str(error.get("msg", "")).removeprefix("Value error, ")
    code, template = _RULES.get(kind, _UNKNOWN)
    try:
        return code, template.format(**ctx)
    except (KeyError, IndexError, ValueError):
        return _UNKNOWN


def summary(count: int) -> str:
    """The notice title: how many things to fix, never "the request was not valid"."""
    if count <= 1:
        return "Please fix the highlighted field."
    return f"Please fix the {count} highlighted fields."
