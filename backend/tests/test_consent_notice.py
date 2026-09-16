"""The four copies of the consent notice agree, or the build fails.

`customer_consent.notice_version` is only worth having if it names words somebody can read back.
There are four places those words and that version live, and each exists for a reason:

- **`docs/consent-notices.md`** — the canonical text, versioned, with the rule that a version is
  added and never edited. This is what somebody reads back years later.
- **`backend/app/core/consent.py`** — what the server records against a consent.
- **`frontend/src/guest/consentNotice.ts`** — the words a guest actually reads, and the version the
  guest bundle sends.
- **`frontend/src/staff/consentVersion.ts`** — the version the *staff* bundle sends, when a manager
  records a consent somebody gave on the phone. Stated separately because ADR 0009 forbids the two
  bundles importing from each other, so it is a fourth copy — and a fourth copy asserted equal to
  the others cannot drift.

Two copies that can drift will drift. These four drifting means recording a consent against a
notice nobody was shown, which is a column that proves nothing — and `docs/compliance-rules.md`
§B2's whole mechanism is proof. Same shape as `tests/test_enum_mirror.py`, for the same reason.

**Nothing asserted here describes the DPDP obligations as currently in force.** They are notified
and commence 13 May 2027; this product builds to the standard now because consent architecture
cannot be retrofitted.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.core.consent import CURRENT_NOTICE_VERSION, DEFAULT_NOTICE_LANGUAGE, GUEST_OFFERABLE
from app.core.enums import ConsentPurpose

_ROOT = Path(__file__).resolve().parents[2]
_NOTICE_TS = _ROOT / "frontend" / "src" / "guest" / "consentNotice.ts"
_STAFF_TS = _ROOT / "frontend" / "src" / "staff" / "consentVersion.ts"
_NOTICE_DOC = _ROOT / "docs" / "consent-notices.md"


def _ts_constant(name: str) -> str:
    match = re.search(rf"export const {name} = '([^']+)'", _NOTICE_TS.read_text(encoding="utf-8"))
    assert match is not None, f"{name} is not exported from consentNotice.ts"
    return match.group(1)


def test_the_server_and_the_screen_name_the_same_notice_version() -> None:
    assert _ts_constant("CURRENT_NOTICE_VERSION") == CURRENT_NOTICE_VERSION


def test_the_staff_bundle_names_the_same_notice_version() -> None:
    """The fourth copy, and the reason there is one.

    ADR 0009 forbids the staff and guest bundles importing from each other, so the staff screen that
    records a consent a manager took on the phone cannot read the guest constant. It states the
    version itself, and this is what stops the two diverging the day somebody bumps one.
    """
    match = re.search(
        r"export const CURRENT_NOTICE_VERSION = '([^']+)'", _STAFF_TS.read_text(encoding="utf-8")
    )
    assert match is not None, "CURRENT_NOTICE_VERSION is not exported from consentVersion.ts"
    assert match.group(1) == CURRENT_NOTICE_VERSION


def test_the_server_and_the_screen_name_the_same_language() -> None:
    assert _ts_constant("NOTICE_LANGUAGE") == DEFAULT_NOTICE_LANGUAGE


def test_the_documented_notice_has_a_section_for_the_current_version() -> None:
    """The version the product records must be one somebody can look up.

    A constant pointing at a section that does not exist is the failure this catches: it would mean
    every consent captured from today names a notice nobody can read.
    """
    text = _NOTICE_DOC.read_text(encoding="utf-8")

    assert f"`{CURRENT_NOTICE_VERSION}`" in text


def test_the_screen_offers_exactly_the_purposes_the_server_will_accept() -> None:
    """`GUEST_OFFERABLE` bounds what the guest path may grant, and the screen shows those three.

    A fourth choice on the screen would be a tick that produces a 422 after somebody has already
    given their number; a missing one would be a purpose the server accepts and nobody can see.
    """
    source = _NOTICE_TS.read_text(encoding="utf-8")
    offered = set(re.findall(r"purpose: '([a-z_]+)'", source))

    assert offered == {str(purpose) for purpose in GUEST_OFFERABLE}


def test_feedback_followup_is_not_on_the_three_tap_form() -> None:
    """Deliberate, and worth its own test so it reads as a decision rather than an oversight.

    `feedback_followup` is granted by staff on the profile, when a customer agrees on the phone to
    be contacted about a complaint. `docs/customer-experience.md`: every extra question halves
    completion, and a fourth tick on a three-tap form is an extra question.
    """
    assert ConsentPurpose.FEEDBACK_FOLLOWUP not in GUEST_OFFERABLE


def test_no_consent_choice_is_pre_ticked_in_the_shared_definition() -> None:
    """The rule this module must never break, checked where the choices are defined.

    The screens that render them are checked separately by the frontend suite; this catches a
    default sneaking into the definition itself, which would pre-tick every screen at once.
    """
    source = _NOTICE_TS.read_text(encoding="utf-8")

    assert "checked" not in source
    assert "default" not in source.replace("DEFAULT_NOTICE_LANGUAGE", "")


def test_the_notice_does_not_call_the_obligation_current_law() -> None:
    """`docs/compliance-rules.md` §B2, and CLAUDE.md's second standing rule: never conflate *in
    force* with *notified but not in force*. A screen telling a guest this is required by law today
    would be this product saying something untrue about Indian law."""
    source = _NOTICE_TS.read_text(encoding="utf-8").lower()

    for phrase in ("required by law", "as required under", "legal requirement", "dpdp requires"):
        assert phrase not in source
