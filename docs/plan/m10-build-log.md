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
| 2 | E | Feedback and complaints, plus the customer history and the DPDP export | ☑ done | `701770b` |
| 2 | F | Staff screens | ☑ done | `c97f1a8` |
| 2 | G | The guest bundle: vite entry, eslint boundary, three screens, `brand.md` §7.1 | ☑ done | `94c753b` |
| 2 | H | Seed, adversarial review, manual script | ☑ done | `d6843a9` |
| 2 | — | **PR 2 gate: full `make check`** | ☐ **not yet run to completion** | — |
| — | — | **Your manual pass** — `docs/manual-tests/M10-customers.md` | ☐ | — |

---

## Resume here

**Every chunk A–H is written, committed and individually green.** What is outstanding is one thing:
the module gate has not run to completion.

| Run | What happened |
|---|---|
| 1 | Failed at `lint-api` in ~1 minute: one line over 100 characters in `tests/test_seed_customers.py`. Fixed. |
| 2 | **Killed by the harness for low memory**, about 5% into the test phase. Not a failure — the machine had 1.5 GB free of 13 GB, and `make check` starts a Postgres testcontainer on top of whatever is already running. |
| 3 | Stopped by the owner, who is restarting the machine. |

**Before the next attempt:** `docker compose stop` (the dev stack had been up fifteen hours and was
holding the memory the testcontainer needed — it is stopped now, and `make dev` brings it back).
Then the usual: `make check > check.log 2>&1; echo $?` and **read the number, not the last lines**.

Everything below the gate line is already true: lint, mypy, eslint, tsc and every suite in this
module were run and green as each chunk landed — 24 customer and complaint tests, 17 endpoint tests,
16 consent and erasure tests, 19 guest-surface tests, 10 seed tests, 29 generic suites including
suite 5, and 396 frontend tests. What the gate adds is *all of them at once*, which is exactly the
thing that has caught the last two modules out.

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

### 1 · Two internal codes were reaching a guest, three levels down (chunk D)

Writing suite 5's reachability rule found them. `GuestItem.modifier_groups` was the *staff*
`ModifierGroupResponse`, which carries `code` and `is_active` on the group and on every modifier
inside it; and `GuestVariant` carried a `code` of its own. A menu that carefully withheld
`BUTTER_CHICKEN` handed over `EXTRA_CHEESE`.

Nothing shipped them — there has been no guest route until this module — but routing M03's tree is
exactly what would have, and they had been in the schema since M03.
`tests/test_menu_tree_guest.py` missed both for ten modules because it asserts about the fields
somebody thought to check: the *dish*.

**The lesson is about the shape of the rule, not the bug.** A field blocklist needs a person to
think of `code` on a modifier three levels down. A rule that walks the model graph does not have
that failure mode, which is why suite 5's second rule — *every model reachable from a guest response
is defined in the guest module* — is the one that matters.

### 2 · A guardrail cried wolf, and tightening it found something real (chunk D)

G-8 flagged `async def update(` in a service as "a service builds SQL directly". It is a method
*name*. A guardrail that reports a false positive is one somebody starts skipping, so the check now
excludes `def` — and running it again surfaced a true finding underneath: the guest bill route was
reaching a repository directly, bypassing its service.

Both are in `scripts/audit_guardrails.py` with the reasoning, and G-8's row in
`docs/engineering-guardrails.md` names its two exemptions rather than leaving them in the script.

### 3 · Visit counts were a column nothing wrote (chunk H, adversarial review)

`customer.visit_count`, `lifetime_value`, `first_visit_at` and `last_visit_at` are columns in
`docs/schema.md` §9 and **nothing in this product maintains them**. The profile screen read them, so
a waiter would have seen "7th visit" frozen at whatever the seed wrote, for ever.

That is precisely the failure `customer_returned` was *removed* to avoid — a stored value sitting
beside a derivation that is always right — and it shipped anyway. Decision 8 argued the case in
writing and chunk B did the opposite four files away.

Derived now, in one grouped query so a list of forty customers costs one round trip. The columns are
left alone and `docs/backlog.md` carries what should happen to them.

**What to take from it:** the review that caught this was reading the *screen* back, not the code. A
number on a screen is a claim, and "what keeps this true?" is a question worth asking of every one.

### 4 · A settled bill cannot take a customer, and the database said so (chunk H)

The seeder tried to attach a regular to a settled order and Postgres refused: *"A settled order is
immutable (invariant 6). Void it or credit-note it."* The trigger was right, and the seeder was
wrong — but so was `POST /staff/orders/{id}/customer`, which had no such check and would have
rendered that refusal to a waiter as "Something went wrong".

Two fixes. The service refuses first, with a sentence that says where the customer goes instead
(*"Put the customer on their next order"*, issue 1207). And the seeder now attaches the regular
**while the bill is still open**, which is when it happens in life — so the seed runs in two passes
with the orders seeder between them.

**What to take from it:** the invariant was enforced at the database and nowhere else, so the first
code path to meet it was a seeder rather than a person. An invariant with a trigger behind it and no
service check in front of it is a good error waiting to reach somebody as a bad one.

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
