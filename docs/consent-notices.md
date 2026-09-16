# Consent notices

The exact words shown to a guest when this product asks for a phone number, version by version.

**Why this file exists.** `customer_consent.notice_version` is worth nothing if it names a notice
nobody can read back. `docs/compliance-rules.md` §B2 asks for the notice version *and* language to be
retained, because what somebody was shown is part of what they agreed to — a consent record whose
words are unrecoverable is not evidence of anything.

**How it is kept honest.** `app/core/consent.py` names the current version;
`frontend/src/guest/consentNotice.ts` carries the same constant and the words the guest actually
reads; `tests/test_consent_notice.py` asserts the two match, and that the text below matches both.
The same mechanism as `tests/test_enum_mirror.py`, for the same reason: two copies that can drift
will drift, and this pair drifting means recording a version nobody was shown.

**Status of the obligations this is built against.** The DPDP Act 2023's notice-and-consent
provisions are **notified and not yet commenced** — Phase 3, 13 May 2027 (`docs/compliance-rules.md`
§B2). This product builds to that standard now because consent architecture cannot be retrofitted;
nothing here should be described, in a screen or anywhere else, as a current legal requirement.

---

## Version `2026-09-16.1` · English (`en`)

Shown above the phone-number field on the guest feedback screen. Every tick is separate and none is
pre-ticked.

> **Your phone number is optional.** You can send this feedback without it.
>
> If you give it, we will use it only for what you tick below. Each one is separate, and you can
> turn any of them off later — from this screen, or by asking any member of staff.
>
> - **About this visit** — so the restaurant can reach you about this order or this feedback.
> - **Remembering how you like things** — your usual order, allergies, spice level, so nobody has to
>   ask you again.
> - **Offers and news** — occasional messages about this restaurant.
>
> Your number is not sold, and is not shared with anyone outside this restaurant.

### The three ticks, and the rows they write

| Tick | `purpose` |
|---|---|
| About this visit | `order_contact` |
| Remembering how you like things | `service_recognition` |
| Offers and news | `marketing` |

`feedback_followup` is not offered on this screen. It is granted by staff, on the profile, when a
customer agrees on the phone to be contacted about a complaint — a fourth tick on a three-tap form
is the fourth question `docs/customer-experience.md` says halves completion.

---

## Languages

The mechanism is built and exactly one language ships. `customer_consent.notice_language` records
which one, `en` is the only value M10 can produce, and adding a language is adding a section here
plus an entry in `consentNotice.ts`.

**A translation is not a text a machine here should produce.** These words are what somebody is held
to have agreed to. A Hindi or Marathi version ships when a native speaker has read it, not before —
and until it does, a guest who cannot read the English notice is a guest this product should not be
taking a phone number from. Tracked in `docs/backlog.md`.

---

## Changing a notice

A new version is a **new section in this file and a new constant**, never an edit to an old one.
Rows already written point at the old version and must keep resolving to the words those people saw.
