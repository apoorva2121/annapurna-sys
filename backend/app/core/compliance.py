"""The rule catalogue: ten rules, each with the instrument it comes from and the date somebody
checked it.

**This is code rather than a table**, and the reason is the same one M14 gave about notifications: a
rule is *a query plus a citation*, and a query does not live in a row. A `compliance_rule` table
would hold the half that does not matter — the words — and leave the detection in a different file,
free to disagree with it.

**`docs/compliance-rules.md` exists because research returned stale-but-confident law three times in
one session.** So every rule here carries four things, and `tests/test_m18_compliance.py` refuses
the build if any is missing:

- the **instrument** it comes from, by name;
- its **commencement** — when it started, or starts, to bind;
- the date somebody **checked** it, because a citation with no check date is a rumour;
- the **status**, which is one of four and is never guessed.

**Only `IN_FORCE` may raise a `critical`.** A rule commencing in 2027 may inform and must say so in
words. Conflating *in force* with *notified but not in force* with *unsettled* with *unverified* is
the specific failure that file was written to prevent, and here it is a test rather than a habit.

**No rule states a penalty.** The product says what is wrong, what it risks in general terms, and
what to do next. Anything past that is legal advice, and this is not qualified to give it.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum


class RuleStatus(StrEnum):
    """The four states `docs/compliance-rules.md` forbids conflating.

    *"Only the first is safe to build on, and only the first may block a user."*
    """

    IN_FORCE = "in_force"
    NOTIFIED_NOT_IN_FORCE = "notified_not_in_force"
    UNSETTLED = "unsettled"
    UNVERIFIED = "unverified"


class Severity(StrEnum):
    """Legal exposure, not annoyance.

    `CRITICAL` means *operating illegally right now*. `WARNING` means *will be, on a known date*.
    `ADVISORY` means good practice with no statutory basis binding today. Using `CRITICAL` for
    anything else is how an owner learns to dismiss the card.
    """

    CRITICAL = "critical"
    WARNING = "warning"
    ADVISORY = "advisory"


@dataclass(frozen=True, slots=True)
class Facts:
    """Everything the catalogue is allowed to look at.

    A plain snapshot rather than a session: a rule that could run its own query could run one
    nobody reviewed, and the point of this module is that every alarm can state its evidence.
    """

    today: date
    fssai_licence: str | None
    fssai_expires_on: date | None
    gstin: str | None
    gst_scheme: str
    annual_turnover: Decimal | None
    invoices_issued: int
    service_charge_rate: Decimal
    live_menu_items: int
    items_without_allergens: int
    items_without_calories: int
    outlets: int
    tax_groups_without_a_current_rate: int
    customers_without_consent: int


@dataclass(frozen=True, slots=True)
class Finding:
    """One thing that is wrong, with the evidence that says so."""

    code: str
    severity: Severity
    # What is wrong.
    title: str
    # What it risks — in general terms, never a quantified penalty.
    risk: str
    # What to do next.
    action: str
    # The facts that raised it, so a person can check the product's working.
    evidence: dict[str, object]


@dataclass(frozen=True, slots=True)
class Rule:
    code: str
    title: str
    instrument: str
    commencement: date
    checked_on: date
    status: RuleStatus
    severity: Severity
    evaluate: Callable[[Facts], Finding | None]

    def __post_init__(self) -> None:
        # The rule this module exists to keep, kept structurally rather than by review.
        if self.severity is Severity.CRITICAL and self.status is not RuleStatus.IN_FORCE:
            raise ValueError(
                f"{self.code}: only a rule in force may be critical. This one is "
                f"{self.status.value}, so it may inform and must not block."
            )


# `docs/compliance-rules.md` §A3. Fourteen digits; the first is the type — 1 licence, 2 basic
# registration — and nothing else is issued. **There is no check digit**, so a well-formed number
# cannot be shown to have been issued: this removes typos and lazy fabrications and nothing more.
FSSAI_PATTERN = re.compile(r"^[12][0-9]{13}$")

# The standard structural GSTIN shape: two state digits, a ten-character PAN, an entity digit, `Z`,
# and a checksum character. Structural only — the same caveat as above.
GSTIN_PATTERN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]$")

# `docs/compliance-rules.md` §A4, w.e.f. 1 Apr 2026. The older ₹12 lakh / ₹20 crore figures are
# superseded and mis-tier most Indian restaurants.
BASIC_REGISTRATION_CEILING = Decimal("15000000")  # ₹1.5 crore
STATE_LICENCE_CEILING = Decimal("500000000")  # ₹50 crore

# §B1. A calorie declaration binds a Central Licence holder *or* ten or more outlets. A Central
# licence is state code `00` in digits 2—3 of the number.
CALORIE_OUTLET_THRESHOLD = 10

EXPIRY_WARNING_DAYS = 30


def _licence_is_central(licence: str | None) -> bool:
    """State code `00` in digits 2 and 3 means a Central licence."""
    return licence is not None and len(licence) == 14 and licence[1:3] == "00"


def _expired(facts: Facts) -> Finding | None:
    if facts.fssai_expires_on is None or facts.fssai_expires_on >= facts.today:
        return None
    return Finding(
        code="fssai.expired",
        severity=Severity.CRITICAL,
        title="The FSSAI licence has expired.",
        risk="The restaurant is trading without a valid licence, and the number is printed on "
        "every bill it issues.",
        action="Renew it on FoSCoS, then update the licence and its expiry in Restaurant settings.",
        evidence={"expired_on": facts.fssai_expires_on.isoformat()},
    )


def _expiring(facts: Facts) -> Finding | None:
    if facts.fssai_expires_on is None or facts.fssai_expires_on < facts.today:
        return None
    days = (facts.fssai_expires_on - facts.today).days
    if days > EXPIRY_WARNING_DAYS:
        return None
    return Finding(
        code="fssai.expiring",
        severity=Severity.WARNING,
        title=f"The FSSAI licence expires in {days} days.",
        risk="Trading after it lapses means trading without a licence, and renewal is not instant.",
        action="Start the renewal on FoSCoS now rather than in the last week.",
        evidence={"expires_on": facts.fssai_expires_on.isoformat(), "days": days},
    )


def _malformed_licence(facts: Facts) -> Finding | None:
    """Quiet until a bill has been issued, on the same reasoning as `_gstin`.

    A restaurant that has not yet issued a bill has an *incomplete setup*, which is M02's business
    and not a licence risk. Raising a red `critical` at a tenant who has been in the product for
    four minutes is how a compliance screen teaches its owner to ignore it, and the one thing this
    module cannot afford is to be ignored when it is right.
    """
    if facts.invoices_issued == 0:
        return None
    if facts.fssai_licence and FSSAI_PATTERN.match(facts.fssai_licence):
        return None
    return Finding(
        code="fssai.malformed",
        severity=Severity.CRITICAL,
        title="The FSSAI number is missing or is not a valid number.",
        risk="It prints on every bill. A wrong or absent number on an issued bill is the thing an "
        "inspection looks at first.",
        action="Check the number on the licence itself: fourteen digits, starting with 1 or 2.",
        evidence={"licence": facts.fssai_licence or "", "invoices_issued": facts.invoices_issued},
    )


def _tier(facts: Facts) -> Finding | None:
    """Turnover against the tier the licence actually is.

    The thresholds moved on 1 Apr 2026 and the old ones mis-tier most Indian restaurants, which is
    why they are constants with a citation rather than numbers in a condition.
    """
    if facts.annual_turnover is None or not facts.fssai_licence:
        return None
    registration = facts.fssai_licence.startswith("2")
    central = _licence_is_central(facts.fssai_licence)
    if registration and facts.annual_turnover > BASIC_REGISTRATION_CEILING:
        needed = "a State Licence"
    elif not central and facts.annual_turnover > STATE_LICENCE_CEILING:
        needed = "a Central Licence"
    else:
        return None
    return Finding(
        code="fssai.tier",
        severity=Severity.WARNING,
        title=f"Turnover has passed the band this licence covers. It needs {needed}.",
        risk="Operating above the band the licence covers is operating outside it.",
        action=f"Apply to upgrade to {needed} on FoSCoS.",
        evidence={"annual_turnover": str(facts.annual_turnover)},
    )


def _gstin(facts: Facts) -> Finding | None:
    if facts.gst_scheme == "composition" or facts.invoices_issued == 0:
        return None
    if facts.gstin and GSTIN_PATTERN.match(facts.gstin):
        return None
    return Finding(
        code="gst.gstin_missing",
        severity=Severity.CRITICAL,
        title="Tax invoices are being issued without a valid GSTIN on them.",
        risk="Rule 46 requires the supplier's GSTIN on a tax invoice. Bills already issued carry "
        "whatever is configured now.",
        action="Put the GSTIN into Restaurant settings, exactly as it appears on the certificate.",
        evidence={"gstin": facts.gstin or "", "invoices_issued": facts.invoices_issued},
    )


def _stale_tax_rate(facts: Facts) -> Finding | None:
    if facts.tax_groups_without_a_current_rate == 0:
        return None
    return Finding(
        code="gst.rate_missing",
        severity=Severity.CRITICAL,
        title="A tax group in use has no rate in force today.",
        risk="Bills are being priced against a rate that has lapsed, or against none at all. Both "
        "GST slabs changed on 22 September 2025 and a configuration that was right became wrong.",
        action="Open Tax rates and add a rate effective from today for each group in use.",
        evidence={"groups": facts.tax_groups_without_a_current_rate},
    )


def _allergens(facts: Facts) -> Finding | None:
    if facts.items_without_allergens == 0:
        return None
    return Finding(
        code="labelling.allergens",
        severity=Severity.WARNING,
        title=(
            f"{facts.items_without_allergens} dishes on the live menu say nothing about allergens."
        ),
        risk="Allergen information has to appear on the menu, and a dish nobody has checked is a "
        "dish nobody can answer a question about.",
        action="Open each dish and write what it contains, or say that it has been checked and "
        "contains none.",
        evidence={"items": facts.items_without_allergens, "live_items": facts.live_menu_items},
    )


def _calories(facts: Facts) -> Finding | None:
    """Conditional, and the condition is the point.

    Most tenants of this product are not covered. A global setting would make it everybody's
    problem; deriving it per restaurant makes it the problem of the restaurants it binds.
    """
    covered = _licence_is_central(facts.fssai_licence) or facts.outlets >= CALORIE_OUTLET_THRESHOLD
    if not covered or facts.items_without_calories == 0:
        return None
    return Finding(
        code="labelling.calories",
        severity=Severity.WARNING,
        title=f"{facts.items_without_calories} dishes have no calorie figure, and this restaurant "
        "is covered by the requirement.",
        risk="The declaration binds a Central Licence holder or a chain of ten or more outlets. "
        "This restaurant is one of those.",
        action="Add the calorie figure and serving size to each dish.",
        evidence={
            "items": facts.items_without_calories,
            "outlets": facts.outlets,
            "central_licence": _licence_is_central(facts.fssai_licence),
        },
    )


def _dpdp(facts: Facts) -> Finding | None:
    """**Notified, not in force.** It may inform and it must say so in words.

    This rule earns its place by being the one that proves the state machine: it can never raise a
    `critical`, however much data the restaurant holds.
    """
    if facts.customers_without_consent == 0:
        return None
    return Finding(
        code="dpdp.consent",
        severity=Severity.ADVISORY,
        title=f"{facts.customers_without_consent} customers are on file with no consent recorded.",
        risk="The DPDP Act's core obligations commence on 13 May 2027 — **this is not law today**. "
        "Consent cannot be obtained retrospectively, so what is not captured now is lost.",
        action="Nothing is required today. When customer details are collected, the product "
        "records the consent and the notice version automatically.",
        evidence={
            "commences": "2027-05-13",
            "customers_without_consent": facts.customers_without_consent,
        },
    )


def _service_charge(facts: Facts) -> Finding | None:
    """**Unsettled**, and says so: a first-instance ruling with an appeal pending."""
    if facts.service_charge_rate <= 0:
        return None
    return Finding(
        code="ccpa.service_charge",
        severity=Severity.ADVISORY,
        title="A service charge is configured.",
        risk="The CCPA's 2022 guidelines say it may not be added by default. A Delhi High Court "
        "judge upheld them in March 2025 and **an appeal is pending**, so the position is not "
        "settled.",
        action="It is added only where somebody chooses to add it, which is how this product "
        "already works. Worth knowing the position is live.",
        evidence={"rate": str(facts.service_charge_rate)},
    )


CATALOGUE: tuple[Rule, ...] = (
    Rule(
        code="fssai.expired",
        title="FSSAI licence expired",
        instrument="FSS (Licensing and Registration) Regulations, 2011",
        commencement=date(2011, 8, 5),
        checked_on=date(2026, 9, 13),
        status=RuleStatus.IN_FORCE,
        severity=Severity.CRITICAL,
        evaluate=_expired,
    ),
    Rule(
        code="fssai.expiring",
        title="FSSAI licence expiring within 30 days",
        instrument="FSS (Licensing and Registration) Regulations, 2011",
        commencement=date(2011, 8, 5),
        checked_on=date(2026, 9, 13),
        status=RuleStatus.IN_FORCE,
        severity=Severity.WARNING,
        evaluate=_expiring,
    ),
    Rule(
        code="fssai.malformed",
        title="FSSAI number missing or malformed",
        instrument="FSS (Licensing and Registration) Regulations, 2011; format per "
        "docs/compliance-rules.md §A3",
        commencement=date(2011, 8, 5),
        checked_on=date(2026, 9, 13),
        status=RuleStatus.IN_FORCE,
        severity=Severity.CRITICAL,
        evaluate=_malformed_licence,
    ),
    Rule(
        code="fssai.tier",
        title="Licence tier below what turnover requires",
        instrument="FSS (Licensing and Registration) Amendment Regulations, 2026",
        commencement=date(2026, 4, 1),
        checked_on=date(2026, 9, 13),
        status=RuleStatus.IN_FORCE,
        severity=Severity.WARNING,
        evaluate=_tier,
    ),
    Rule(
        code="gst.gstin_missing",
        title="Tax invoices issued without a valid GSTIN",
        instrument="CGST Rules, Rule 46",
        commencement=date(2017, 7, 1),
        checked_on=date(2026, 9, 13),
        status=RuleStatus.IN_FORCE,
        severity=Severity.CRITICAL,
        evaluate=_gstin,
    ),
    Rule(
        code="gst.rate_missing",
        title="A tax group in use with no rate in force",
        instrument="CGST Act s.14; notification 09/2025-CTR",
        commencement=date(2017, 7, 1),
        checked_on=date(2026, 9, 13),
        status=RuleStatus.IN_FORCE,
        severity=Severity.CRITICAL,
        evaluate=_stale_tax_rate,
    ),
    Rule(
        code="labelling.allergens",
        title="Live menu item with no allergen statement",
        instrument="FSS (Labelling and Display) Regulations, 2020",
        commencement=date(2022, 7, 1),
        checked_on=date(2026, 9, 13),
        status=RuleStatus.IN_FORCE,
        severity=Severity.WARNING,
        evaluate=_allergens,
    ),
    Rule(
        code="labelling.calories",
        title="Calorie declaration required and absent",
        instrument="FSS (Labelling and Display) Regulations, 2020",
        commencement=date(2022, 7, 1),
        checked_on=date(2026, 9, 13),
        status=RuleStatus.IN_FORCE,
        severity=Severity.WARNING,
        evaluate=_calories,
    ),
    Rule(
        code="dpdp.consent",
        title="DPDP consent architecture",
        instrument="Digital Personal Data Protection Act, 2023",
        commencement=date(2027, 5, 13),
        checked_on=date(2026, 9, 19),
        status=RuleStatus.NOTIFIED_NOT_IN_FORCE,
        severity=Severity.ADVISORY,
        evaluate=_dpdp,
    ),
    Rule(
        code="ccpa.service_charge",
        title="Service charge levied by default",
        instrument="CCPA guidelines, 4 Jul 2022; Delhi HC (single judge), 28 Mar 2025",
        commencement=date(2022, 7, 4),
        checked_on=date(2026, 9, 13),
        status=RuleStatus.UNSETTLED,
        severity=Severity.ADVISORY,
        evaluate=_service_charge,
    ),
)


def evaluate(facts: Facts) -> list[tuple[Rule, Finding]]:
    """Every rule that fires against these facts, worst first.

    A rule that returns `None` is a rule with nothing to say, which is most of them most of the
    time — and the reason the owner's card is silent when nothing is wrong.
    """
    found = [(rule, finding) for rule in CATALOGUE if (finding := rule.evaluate(facts)) is not None]
    order = {Severity.CRITICAL: 0, Severity.WARNING: 1, Severity.ADVISORY: 2}
    return sorted(found, key=lambda pair: order[pair[1].severity])


def rule_for(code: str) -> Rule | None:
    return next((rule for rule in CATALOGUE if rule.code == code), None)


def codes() -> Sequence[str]:
    return tuple(rule.code for rule in CATALOGUE)
