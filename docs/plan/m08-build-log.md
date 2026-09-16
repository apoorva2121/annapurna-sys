# M08 · Kitchen / KOT — Build Log

**Started 2026-09-16**, continuing the autonomous run from M07 on the owner's instruction
(*"continue with m08, m09, run autonomously"*).

Spec: `docs/modules/M08-kitchen-spec.md`. **Resume from the State table below.**

---

## State

| PR | Chunk | What | State | Commit |
|---|---|---|---|---|
| — | — | Research + spec | ☑ done | — |
| 1 | A | Pure-ASGI request context middleware + `status_code` (M4) | ☑ done | `ea215ae` |
| 1 | A2 | argon2 off the event loop (P1-9, G-6) | ☑ done | `98b1720` |
| 1 | B | Migration 0030 + models + schema doc + enums | ☑ done | `e323c20` |
| 1 | C | Migration 0031: `kot.view` / `kot.update` grants | ☑ done | `6b054ea` |
| 1 | D | Repository + ticket creation from `send()` | ☑ done | `4f60a7f` |
| 1 | — | **PR 1 gate: full `make check`** | ☑ green on the third run — see below | — |
| 2 | E | Transition state machine, timestamps, per-line ready, remake | ☐ | — |
| 2 | F | Revision cursor, `GET /kot/stream`, heartbeat, replay | ☐ | — |
| 2 | G | Reconciliation with M07: serve, cancel, late | ☐ | — |
| 2 | — | **PR 2 gate: full `make check`** | ☐ | — |
| 3 | H | KDS rail, ticket detail, remake, SSE hook, readability test | ◑ the `fetch`-based SSE reader landed early, with PR 1 | `8aa6095` |
| 3 | I | Seed, review, second reader, manual script, deploy notes | ☐ | — |
| 3 | — | **PR 3 gate: full `make check`** | ☐ | — |
| — | — | **Your manual pass** — `docs/manual-tests/M08-kitchen.md` | ☐ | — |

**Full `make check` runs at the end of each PR**, not after every chunk, for the reason recorded in
`docs/plan/m07-build-log.md`: running it while the next chunk's files are half-written lets pytest
collect them and blame the wrong commit. Every chunk still has its targeted tests, the generic
suites, lint, types and both audits before it is committed.

---

## Notes carried forward from M07

- **Use `backend/.venv/Scripts/python -m pytest`, never bare `python`** — bare `python` here is
  Anaconda, whose `argon2` is too old for `app.core.security`.
- **Run pytest from `backend/`**, not the repository root: Alembic resolves `script_location`
  relatively.
- **Very long inline shell commands fail on this machine** (`ENAMETOOLONG`, or bash losing a
  heredoc). Write a script to the scratchpad and run it.
- **Two bill images sit untracked at the repository root.** They carry a real restaurant's phone
  number and GSTIN. Never `git add -A`; commit by explicit path.

---

## PR 1 gate — three runs, and what the first two were for

**Run 1 failed at `lint-api`, exit 2, while printing `All checks passed!`.** That is the trap
CLAUDE.md documents: the gate's own last lines belong to whichever sub-target printed last, and a
mypy error four lines earlier scrolls past. Reading the exit code rather than the tail is the whole
of the discipline, and it is why this project writes `make check > check.log 2>&1; echo $?`.

The error was real: chunk A changed `route_template` to take an ASGI scope, and `tests/test_ops.py`
still handed it a `Request`. Nothing a targeted run would have caught, because the targeted run for
chunk A was `test_request_context.py` and `test_ops.py` is a different file testing the same
function.

**Run 2 found two more, both of them a test doing its job.**
`test_auth_service.py::test_the_permissions_come_from_the_seeded_catalogue` and its sibling in
`test_auth_switch.py` assert a waiter's permissions as a **literal set**, with a comment saying why:
so that widening a waiter's powers has to be a deliberate edit rather than a resolver quietly
returning more. Chunk C widened them by one — `kot.view` — and both tests failed exactly as
designed. Updated, with the reason recorded beside the set.

The lesson for the rest of this module: **a change to the permission catalogue needs the auth
suites re-run, not only the catalogue suites.** Chunk C ran `test_permission_seed`,
`test_permissions_catalogue` and `test_database`, all green, and the two tests that actually
encode the design's line were in neither list.

Run 2 was stopped part-way rather than left to finish, because by then the tree had moved on:
migration 0032 had been added and the run was measuring something that no longer existed.

**Run 3 found a third:** `test_issue_catalogue.py::test_every_raised_code_has_an_issue`, which
walks the syntax tree of `app/` and fails on any `raise ConflictError("x.y", …)` whose code has no
entry in `app/core/issues.json`. Ten new kitchen codes had none. Migration 0032 gives them numbers
1173–1182, so a chef who meets a refusal has something to read out on the phone (D11, D12).

---

## The owner's verdict on section B — two metres

**2026-09-16, owner, asked directly: "chef can do it".**

Recorded against **section B of `docs/manual-tests/M08-kitchen.md` only** — the two-metre
readability question — and not as the module's manual pass. The distinction is the same one M05's
row in `docs/checklist.md` makes, and for the same reason: the column means "you have run it and
every step passes", and a checklist that overstates what was checked is the exact failure R9 built
a gate against.

What this settles, and it is the thing I could not settle myself: a chef can work from the rail.
Section B is the only part of this module that no test can reach — a test asserts a font is 40px; it
cannot say that somebody looks up mid-service and knows what to cook. That question is now answered
yes.

**Still open, and still the owner's:** sections A, C, D, E, F, G and the H charter. Two of them
matter more than the rest and neither is a check:

- **D2** — whether `ready` belonging to the kitchen and `served` belonging to the floor is right in
  a real kitchen. It is the module's main internal control and it is cheap to change today.
- **H** — at what point the rail stops being readable as tickets pile up, and whether the elapsed
  clock makes somebody act or becomes wallpaper.

---

## Adversarial review — step 7 of the module loop

Checklist from `docs/testing-strategy.md` Part 1, walked over the whole M08 diff.

| Check | Result |
|---|---|
| Tenant leakage in a hand-written query | See finding 1 |
| Permission check in the route rather than the service | Clean — every route declares one; the generic suite walks them |
| N+1 behind a lazy relationship | Clean — every relationship is `lazy="raise"`, and two tests assert flat query counts |
| Money touching a float | **Nothing in the module touches money at all**, asserted by a test over `information_schema` |
| Naive datetime | Clean — no bare `datetime.now()` anywhere in the module |
| Unit assumed rather than converted | N/A — the kitchen handles no quantities in stock units |
| Unbounded query | Clean — `rail` and `since` page; the rest are bounded by an order's own line ids |
| Missing index for a new filter | Clean — `ix_kot_ticket_rail` and `ix_kot_ticket_revision` cover both |
| Client-supplied price or total trusted | N/A, and structurally impossible: no money column exists here |
| PII in a log line | Clean — ids, ticket numbers and counts only |
| Error message leaking internals | Clean — messages name a ticket number and a status |

## 1 · `routing_for` joins the menu without a tenant filter on the joined tables

`OrderLine` is scoped, and `order_line.menu_item_variant_id` carries a **composite** foreign key to
`(menu_item_variant.id, restaurant_id)`, so the variant is guaranteed same-tenant. But
`menu_item_variant.menu_item_id` is a **plain** foreign key to `menu_item.id` — M03's schema, not
M08's — so nothing in the database forbids a variant pointing at another restaurant's item.

**It fails closed rather than leaking**, which is why it is a note and not a fix. If such a row
existed, `routing_for` would return the other restaurant's `station_id`, and `kot_ticket`'s own
composite foreign key on `(station_id, restaurant_id)` would refuse the insert: the send fails
loudly instead of routing a dish onto a stranger's rail.

**Do not "fix" it by adding a filter to the join.** That would convert a refused send into a
silently missing dish, which is strictly worse. The real fix is `UNIQUE (id, restaurant_id)` on
`menu_item` plus a composite key from the variant — M03's to make, and a backlog row.

## 2 · The concurrent-stream cap in the spec was not built

The spec's threat question proposed "a per-token concurrent-stream cap". It is not implemented, and
on reflection it should not be, in this shape:

- A cap enforced per worker is not a cap. With `max-instances=3` a client opens three times the
  limit by reconnecting, and the number in the code would read as a control while being a
  suggestion.
- The two things actually holding this down are built: a stream ends on its own deadline
  (`MAX_SECONDS`), and it re-checks the session every tick, so a revoked token cannot hold one open.
- The remaining exposure is an authenticated member of staff opening many streams on purpose. That
  is a person with a login doing something visible, not an anonymous attacker.

Recorded in `docs/backlog.md` with the condition that would make it worth building: a real
deployment where connection-pool pressure from displays is measured rather than imagined.

## 3 · `served` arriving before `ready` is repaired, not refused

`serve_order_lines` fills in `ready_at` when a counter-service order is served off the pass without
anybody pressing Ready. Worth naming because it is a service quietly satisfying a CHECK constraint,
which is usually a smell.

It is right here: the constraint exists so a prep time is never unanswerable, and "the pass and the
handover happened at the same instant" is the true answer for counter service, not a fabrication.
The alternative — refusing the serve — would make the product unusable for exactly the restaurants
that take money before they cook. Tested explicitly.
