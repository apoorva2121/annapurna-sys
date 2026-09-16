// Which notice a *staff*-captured consent is recorded against.
//
// The words themselves live in `src/guest/consentNotice.ts`, because a guest is who reads them —
// and ADR 0009 forbids the staff bundle importing anything from `src/guest/`, in either direction
// of reasoning: the boundary exists so the guest bundle cannot contain staff code, and crossing it
// the other way would make one file belong to both bundles.
//
// So the version is stated twice, and `backend/tests/test_consent_notice.py` holds all of them to
// the same value: this file, `src/guest/consentNotice.ts`, `app/core/consent.py` and
// `docs/consent-notices.md`. Two copies that can drift will drift; four that are asserted equal
// cannot.
//
// **A version is never edited, only added.** Rows already written point at the old one and must keep
// resolving to the words those people were shown.

export const CURRENT_NOTICE_VERSION = '2026-09-16.1';
export const NOTICE_LANGUAGE = 'en';
