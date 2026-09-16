"""A GSTIN at the API boundary: structure checked, capitals enforced.

One definition for the four request fields that accept one — a supplier (create and update), the
restaurant's own settings, and a registered customer on a tax invoice. Before this module each
schema carried its own copy of the pattern and none of them accepted lower case, so a correct GSTIN
typed on a phone keyboard was refused (backlog: "The API does not uppercase a GSTIN").

**A well-formed GSTIN is not a verified one.** There is no check digit (`docs/compliance-rules.md`
§A3), and nothing downstream may treat this as verification.
"""

from __future__ import annotations

from typing import Any

# 2-digit state code, 10-character PAN, entity digit, 'Z', checksum character.
GSTIN_PATTERN = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"


def capitalise_gstin(value: Any) -> Any:
    """Trim and uppercase before the pattern runs. Anything that is not a string is left for the
    type check to refuse."""
    return value.strip().upper() if isinstance(value, str) else value
