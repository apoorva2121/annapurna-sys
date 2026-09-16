// The exact words a guest reads before giving us their phone number, and the version they were
// shown under.
//
// `docs/consent-notices.md` holds the canonical text; `backend/app/core/consent.py` holds the same
// version string; `backend/tests/test_consent_notice.py` asserts all three agree. Two copies that
// can drift will drift, and these drifting means recording a consent against a notice nobody saw —
// which is a `notice_version` column that proves nothing.
//
// **A version is never edited, only added.** Rows already written point at the old version and must
// keep resolving to the words those people read.
//
// Nothing here describes these obligations as current law. The DPDP Act 2023's notice-and-consent
// provisions are notified and commence 13 May 2027 (`docs/compliance-rules.md` §B2). This product
// builds to that standard now because consent architecture cannot be retrofitted — you cannot
// lawfully re-derive consent that was never captured.

export const CURRENT_NOTICE_VERSION = '2026-09-16.1';
export const NOTICE_LANGUAGE = 'en';

/**
 * The three ticks, in the order they are shown.
 *
 * `feedback_followup` is deliberately absent: it is granted by staff, on the profile, when a
 * customer agrees on the phone to be contacted about a complaint. A fourth tick on a three-tap form
 * is the fourth question `docs/customer-experience.md` says halves completion.
 *
 * **None of these is ever pre-ticked**, on any layer, and a test reads this file's screens to prove
 * it. A pre-ticked box is not consent.
 */
export const CONSENT_CHOICES = [
  {
    purpose: 'order_contact',
    label: 'About this visit',
    detail: 'So the restaurant can reach you about this order or this feedback.',
  },
  {
    purpose: 'service_recognition',
    label: 'Remembering how you like things',
    detail: 'Your usual order, allergies, spice level, so nobody has to ask you again.',
  },
  {
    purpose: 'marketing',
    label: 'Offers and news',
    detail: 'Occasional messages about this restaurant.',
  },
] as const;

/** The notice itself, shown above the choices. Kept in one place so it cannot drift between screens. */
export const NOTICE_TEXT = {
  heading: 'Your phone number is optional.',
  body: 'You can send this feedback without it. If you give it, we will use it only for what you tick below. Each one is separate, and you can turn any of them off later — from this screen, or by asking any member of staff.',
  footer: 'Your number is not sold, and is not shared with anyone outside this restaurant.',
} as const;
