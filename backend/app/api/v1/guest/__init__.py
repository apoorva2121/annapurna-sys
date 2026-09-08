"""The customer surface.

ADR 0009. Narrow, read-mostly, fully untrusted input, separate auth realm (table token or phone
OTP), separate rate limits. Guest responses expose dish names, prices and the guest's own order —
never cost, margin, recipe, employee name, or another guest's anything.

Empty until M10.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()
