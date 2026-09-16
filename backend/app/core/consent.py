"""Which notice is current, and the four purposes it can be given for.

`docs/consent-notices.md` holds the words. This holds the version string those words were published
under, and `frontend/src/guest/consentNotice.ts` holds the same string beside the text a guest
actually reads. `tests/test_consent_notice.py` asserts the two match — the same mechanism as
`tests/test_enum_mirror.py`, for the same reason: two copies that can drift will drift, and these
two drifting means recording a consent against a notice nobody was shown.

**A version is never edited, only added.** Rows already written point at the old version and must
keep resolving to the words those people saw. `docs/consent-notices.md` says so in its own last
section, and this constant moving without a new section there is the failure that test prevents.

**Nothing here describes these obligations as current law.** `docs/compliance-rules.md` §B2: the
DPDP Act 2023's notice-and-consent provisions are notified and commence 13 May 2027. This product
builds to that standard now because consent architecture cannot be retrofitted — you cannot lawfully
re-derive consent that was never captured — and says nothing, anywhere a person can read it, that
calls the obligation current.
"""

from __future__ import annotations

from app.core.enums import ConsentPurpose

# The notice published in `docs/consent-notices.md`. Bump by adding a section there, never by
# editing one.
#
# **There is no endpoint that serves this.** `frontend/src/guest/consentNotice.ts` carries the same
# string beside the words a guest reads, and `tests/test_consent_notice.py` asserts the two match —
# so a client already knows the current version by construction, and a route to ask for it would be
# a second source of truth for a value that must have exactly one.
CURRENT_NOTICE_VERSION = "2026-09-16.1"

# The only language M10 can produce. The mechanism is built and the content is a person-shaped
# dependency: a consent notice is a text somebody is held to, and it ships when a native speaker has
# read it (`docs/backlog.md`).
DEFAULT_NOTICE_LANGUAGE = "en"

# What the three-tap guest form may offer. `FEEDBACK_FOLLOWUP` is deliberately absent: it is granted
# by staff on the profile, when a customer agrees on the phone to be contacted about a complaint. A
# fourth tick on a three-tap form is the fourth question `docs/customer-experience.md` says halves
# completion.
GUEST_OFFERABLE: frozenset[ConsentPurpose] = frozenset(
    {
        ConsentPurpose.ORDER_CONTACT,
        ConsentPurpose.SERVICE_RECOGNITION,
        ConsentPurpose.MARKETING,
    }
)
