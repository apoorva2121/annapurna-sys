"""The customer surface. Five routes, and the shape of them is the security design.

ADR 0009. Narrow, read-mostly, fully untrusted input, separate auth realm, separate rate limits.
Guest responses expose dish names, prices and the guest's own order — never cost, margin, recipe,
employee name, or another guest's anything.

**Every route here declares a rate limit the way a staff route declares a permission.** Not
middleware: `require_permission`'s docstring explains why and it applies unchanged here — "the
declaration matters as much as the enforcement: it is what lets a test walk the application's own
routing table and prove that no route was registered without a permission". Suite 5 walks for the
limit, and asserts the opposite for permissions: a guest route that declares one has had the staff
dependency chain wired into it, which is the exact failure ADR 0009 is structured to prevent.

**Every route answers from `app/schemas/guest.py`**, and every model reachable from those responses
is defined there too. Also suite 5. Writing that rule found two leaks that had been in the schema
since M03 and would have shipped the moment the menu was routed.

**Every write route commits.** The convention this codebase has broken twice.

**No route here is idempotent by key** (ADR 0010), and that is deliberate rather than an omission.
An idempotency key is a header a client sets, and the client here is a stranger's phone. The
double-submit that actually happens — a guest tapping Send twice on a slow network — is answered by
the unique index on `feedback.order_id` and a service that returns the existing row, which needs
nothing from the client at all.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.guest import consent, feedback, menu, order, session

router = APIRouter()
router.include_router(session.router)
router.include_router(menu.router)
router.include_router(order.router)
router.include_router(feedback.router)
router.include_router(consent.router)
