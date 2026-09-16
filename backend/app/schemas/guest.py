"""Every response the guest surface can produce. Nothing else may answer a guest route.

ADR 0009's consequence, verbatim: "Some serialisation logic is duplicated between staff and guest
schemas. **That duplication is the feature** — it means a field added for staff cannot silently
appear in a guest response."

That only holds if the duplication is structural, so three rules are enforced by
`tests/test_generic_suites.py` suite 5, walking the routing table rather than trusting review:

1. **Every guest route's `response_model` is defined in this module.** A guest route answering with
   a staff schema fails the build.
2. **Every model reachable from those is defined in this module too.** The leak is never in the
   top-level schema; it is three levels down, in something reused because it looked harmless.
3. **No field in that graph is named like an internal one** — `cost`, `margin`, `recipe`,
   `station`, `prep_minutes`, `employee`, `code`, `is_active`. `price` is allowed and named as the
   exception: it is what the guest pays.

Rule 2 found a real leak the day it was written. `GuestItem` used to carry the *staff*
`ModifierGroupResponse`, which has `code` and `is_active` on the group and on every modifier — so a
menu that carefully hid `BUTTER_CHICKEN` handed over `EXTRA_CHEESE` one level down. M03 excluded
internal codes from the item and the variant and reused a schema that put them back.
`tests/test_menu_tree_guest.py` did not catch it because it asserted about the fields it knew to
look at. A rule that walks the graph does not have that failure mode.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import ConsentPurpose, FoodType


class _Guest(BaseModel):
    """`extra="forbid"` on the way in; nothing implicit on the way out."""

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- the session


class GuestSessionRequest(_Guest):
    """One of the two, never both. The table slug comes off the sticker; the order token off the
    bill."""

    table_slug: str | None = Field(default=None, min_length=8, max_length=64)
    order_token: str | None = Field(default=None, min_length=8, max_length=64)


class GuestSessionResponse(_Guest):
    token: str
    expires_at: datetime
    # What the guest sees at the top of the screen. The restaurant's name is public — it is on the
    # door — and nothing else about it is here.
    restaurant_name: str
    scope: str


# --------------------------------------------------------------------------- the menu


class GuestModifier(_Guest):
    """A choice, as a diner sees it. No `code`, no `is_active`: `EXTRA_CHEESE` is a join key."""

    id: uuid.UUID
    name: str
    # A string in JSON, never a float (invariant 3). "no rice" may legitimately be negative.
    price_delta: Decimal


class GuestModifierGroup(_Guest):
    id: uuid.UUID
    name: str
    min_select: int
    max_select: int
    is_required: bool
    modifiers: list[GuestModifier]


class GuestVariant(_Guest):
    """What a diner may see of a variant: what it is called and what it costs.

    Not `prep_minutes` — a kitchen's standard time is an internal number, and a guest shown "11
    minutes" will hold the restaurant to it.
    """

    id: uuid.UUID
    name: str
    price: Decimal


class GuestItem(_Guest):
    """A dish, as a diner sees it. No station — one dish's station is harmless, a whole menu's
    stations describe how the kitchen is laid out and how many lines it runs."""

    id: uuid.UUID
    name: str
    description: str | None
    food_type: FoodType
    # What a guest with an allergy reads (`docs/compliance-rules.md` §A2): text, NULL when never
    # asked. The one field on this screen somebody's health depends on.
    allergen_statement: str | None = None
    # §B1, for a restaurant the calorie rule covers.
    calories_kcal: int | None = None
    serving_size: str | None = None
    image_url: str | None
    variants: list[GuestVariant]
    modifier_groups: list[GuestModifierGroup]


class GuestCategory(_Guest):
    id: uuid.UUID
    name: str
    items: list[GuestItem]


class GuestMenuResponse(_Guest):
    version: int
    categories: list[GuestCategory]


# --------------------------------------------------------------------------- the bill


class GuestBillLine(_Guest):
    """One line of what this table is having.

    The dish, how many, and what they come to at menu price. Not the waiter who took it, not the
    station it was cooked at, not what it cost the restaurant to make, and not the order line's id —
    a guest has nothing to do with one.

    `amount` is the line's `line_subtotal`: the menu price plus whatever the modifiers added, times
    the quantity, **before** any discount and before tax. That is the number a person expects beside
    a dish on an Indian bill, and it is the number that adds up to the `subtotal` below it. The
    discount and the tax are footer lines, where a guest can see them applying to the whole bill
    rather than having to reconcile eleven rows.
    """

    name: str
    quantity: int
    amount: Decimal


class GuestBillResponse(_Guest):
    """Every line before payment, and the same server-computed figures the staff bill shows.

    `docs/ui/brand.md` §7: "The bill shows every line before payment: dishes, discounts, charges,
    tax split, round-off, total." Every one of these is a field the staff bill already has,
    rendered rather than recomputed — a guest total that disagreed with the printed one by a paisa
    is an argument at the table.

    **No CGST/SGST split, and that is not an omission.** §7 asks for the "tax split", and the split
    is a *tax invoice* particular: `docs/compliance-rules.md` cites CGST Rules, Rule 46, and this
    product produces an invoice at settlement, not before. What a guest reads here is the
    provisional bill — what they will be charged, with the tax as one line, which is what the staff
    bill shows too (`OrderSummaryResponse` carries `tax_total` and no split). The split arrives with
    the rendered invoice, which `docs/compliance-rules.md` already lists as an open M07 gap.
    """

    lines: list[GuestBillLine]
    subtotal: Decimal
    discount_total: Decimal
    charge_total: Decimal
    tax_total: Decimal
    round_off: Decimal
    grand_total: Decimal
    is_settled: bool


# --------------------------------------------------------------------------- the three questions


class GuestFeedbackRequest(_Guest):
    """Food, service, would-you-return, and an optional word.

    `docs/customer-experience.md`: "Three questions maximum. Every extra question halves
    completion." A fourth rating is not accepted by this schema, which is the cheapest possible way
    to keep that true.

    `phone` and the consent that must accompany it are optional and independent: feedback with no
    phone is the default and is fully supported.
    """

    food_rating: int | None = Field(default=None, ge=1, le=5)
    service_rating: int | None = Field(default=None, ge=1, le=5)
    would_return: bool | None = None
    comment: str | None = Field(default=None, max_length=1000)
    phone: str | None = Field(default=None, min_length=8, max_length=20)
    # Never defaulted to true anywhere, on any layer. §B2: consent is explicit, and a pre-ticked box
    # is not consent.
    consents: list[ConsentPurpose] = Field(default_factory=list)
    notice_version: str | None = None
    notice_language: str | None = None


class GuestFeedbackResponse(_Guest):
    """What the guest sees after tapping Send: an acknowledgement, and nothing that could be used to
    check whether a phone number is known to us (`docs/security.md`: "No enumeration")."""

    id: uuid.UUID
    submitted_at: datetime
    # True when this submission created the row, false when it returned the one already there — a
    # guest who tapped twice on a slow connection sees "thank you" either way.
    already_submitted: bool


class GuestConsentWithdrawRequest(_Guest):
    """Withdrawal, and there is no schema for the other direction.

    §B2 asks that withdrawing be as easy as granting, and this is that. It cannot grant, because
    the shape has nowhere to say so: an anonymous surface cannot know whose phone is in whose hand,
    and a grant is a claim about a person. The only place a guest grants anything is the feedback
    form they typed their own number into.

    The notice is still recorded — what somebody was shown when they withdrew is part of the
    record too.
    """

    purpose: ConsentPurpose
    notice_version: str = Field(min_length=1, max_length=40)
    notice_language: str = Field(min_length=2, max_length=8)


class GuestConsentResponse(_Guest):
    purpose: ConsentPurpose
    granted: bool
    occurred_at: datetime
