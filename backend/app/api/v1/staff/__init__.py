"""The employee surface.

ADR 0009: staff and guest are two applications, not two roles. This router and the guest router
share no middleware, no dependency chain and no handler. A guest request cannot physically enter
this routing tree — that is a structural property, not a discipline.

Empty until M01. The seam exists now precisely so it never has to be retrofitted.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()
