# M10 · Customers, Feedback & Guest App — Build Log

**Started 2026-09-16**, continuing the autonomous run from M08 and M09 on the owner's instruction
(*"After m09, go for m10, m11, m12, in a streak"*, *"don't stop until you are either done or tokens
are over"*).

Spec: `docs/modules/M10-customers-spec.md`. **Resume from the State table below.**

---

## State

| PR | Chunk | What | State | Commit |
|---|---|---|---|---|
| — | — | Research + spec | ☑ done | `a8d0da2` |
| 1 | A | Migration 0036 + models + repositories + `docs/schema.md` §9 | ☑ done | `33b8a99` |
| 1 | B | Migration 0037 permissions; customer service, staff CRUD, preferences, the order attach and the frozen allergy note | ☑ done | `f3310ea` |
| 1 | C | Consent and erasure — and their tests, which are the compliance evidence. **History and export moved to E**, where the feedback and complaints they list exist | ☑ done | `128602f` |
| 1 | — | **PR 1 gate: full `make check`** | ☐ | — |
| 2 | D | The guest realm: `guest_token.py`, `guest_deps.py`, `schemas/guest.py`, the rate limiter, the five guest routes, suite 5 | ☑ done | `206966e` |
| 2 | E | Feedback and complaints, plus the customer history and the DPDP export | ☐ | — |
| 2 | F | Staff screens | ☐ | — |
| 2 | G | The guest bundle: vite entry, eslint boundary, three screens, `brand.md` §7.1 | ☐ | — |
| 2 | H | Seed, adversarial review, manual script | ☐ | — |
| 2 | — | **PR 2 gate: full `make check`** | ☐ | — |
| — | — | **Your manual pass** — `docs/manual-tests/M10-customers.md` | ☐ | — |

---

## What M08 and M09 taught this module, before a line of it is written

Six things cost time in the last two modules and are cheap to avoid here.

**1 · Every write route commits.** M08 shipped a whole module of writes that returned 201 and rolled
back, and the same bug is documented at the top of `app/api/v1/staff/inventory.py` from an earlier
module. It has happened twice. Every test that writes does **two** requests: the write, and a read
that proves it survived.

**2 · A permission-catalogue change needs the *auth* suites re-run, not only the catalogue suites.**
Two tests assert a waiter's permissions as a literal set, deliberately, so that widening a waiter's
powers is an edit somebody makes on purpose. M10 adds six permissions and grants none of them to a
waiter — and the auth suites run anyway.

**3 · A new error code needs an issue number in the same commit.** `test_every_raised_code_has_an_
issue` walks the AST of `app/` and fails on any raised code without an entry. Migration 0038 is
written as codes are added, not after.

**4 · Check the design file, never the sentence in the spec.** M09's first draft said a waiter may
log waste; `seed/organization.yaml` says they may not. **The same mistake was made again while
writing M10's spec, in the opposite direction**: the first draft said "`customer.view` is not
granted to waiters by default", and the design grants exactly that — along with `feedback.view` —
because `docs/customer-experience.md` puts the regular's card on the waiter's screen. Caught by
reading the file rather than by a test. It also changed the threat section: if a waiter can see the
customer list, the control is the *shape of the surface*, not the permission.

**5 · Every new path parameter needs a victim row, or its routes leave the security suite.**
`test_every_path_parameter_has_a_victim_row` exists because "adding a route with a new parameter
name removed it from the product's most important security test without changing a single line of
this file". M10 adds `customer_id`, `preference_id`, `feedback_id` and `complaint_id`, and each
needs a row in `_victim_resources` — the customer in the *other organization*, since a customer is
organization-scoped rather than restaurant-scoped.

**6 · A route that never returns hangs the generic suites.** M08's `GET /kot/stream` stopped the
build dead until `RouteInfo.is_stream` existed. M10 adds no streaming route, and if one appears it
goes on that list with its cover named.

---

## Findings

*(appended as they happen — a finding recorded after the fact is a finding nobody learns from)*

---

## The test files this module owes, and what each one is for

Written down before any of them exists, because a test inventory decided afterwards is an inventory
shaped by what turned out to be easy.

| File | What it holds |
|---|---|
| `test_customer_schema.py` | Migration 0036 against real Postgres: the composite tenant keys, every check constraint refusing what it should, the `guest_slug` backfill producing distinct values, and up→down→up |
| `test_customer_service.py` | Every service method including failure paths: the duplicate phone, the erased customer, the phone normalisation that decides identity |
| `test_customer_endpoints.py` | Per endpoint: happy, validation, permission, not-found, conflict — and the **two-request** write test that would have caught M08's rollback |
| `test_consent.py` | One row per purpose; withdrawing marketing leaves order contact alone; a purpose never asked is absent rather than false; the notice version and language are stored as shown |
| `test_consent_notice.py` | The backend constant, the frontend constant and `docs/consent-notices.md` all name the same version — the `test_enum_mirror.py` mechanism, for the text somebody is held to |
| `test_erasure.py` | Revenue totals unchanged; preferences gone; the consent ledger intact; the placeholder phone not colliding; a second erasure refused |
| `test_guest_token.py` | A staff token refused by `decode_guest_token` and a guest token refused by `decode_access_token` — ADR 0009's guarantee, asserted in both directions |
| `test_guest_session.py` | Both QR codes; one refusal for every failure; a reprinted bill killing the old token *and* the sessions opened from it |
| `test_guest_surface.py` | The guest routes' behaviour: the menu's ETag, the bill's own order only, feedback once, withdrawal-only consent, 429 under a burst |
| `test_feedback.py` | Three questions; anonymous by default; the second submission returning the first row; the waiter derived from the order; **no phone number in any log record** |
| `test_complaints.py` | The workflow, the resolution constraint, and `customer_returned` derived from the order ledger with no endpoint able to write it |
| `test_seed_customers.py` | The planted state survives: regulars with preferences, a spread of ratings, one open complaint, one withdrawn consent, one order with no feedback |
| `test_generic_suites.py` | **Suite 5**, plus four new victim rows so suite 1 can probe the new path parameters |
| `wasteDiscipline.test.ts`'s sibling — `guestDiscipline.test.ts` | No pre-ticked consent control; no staff import inside `src/guest/`; the menu's single filter |
