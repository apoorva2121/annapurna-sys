# M09 · Waste — Build Log

**Started 2026-09-16**, continuing the autonomous run from M08 on the owner's instruction
(*"continue with m08, m09, run autonomously"*).

Spec: `docs/modules/M09-waste-spec.md`. **Resume from the State table below.**

---

## State

| PR | Chunk | What | State | Commit |
|---|---|---|---|---|
| — | — | Research + spec | ☑ done | — |
| 1 | A | Migration 0033 + models + schema doc check | ☑ done | `b0fd9c9` |
| 1 | B | Migration 0034: `wastage.log` / `wastage.approve` | ☑ done | `7d7c44a` |
| 1 | C | Reasons CRUD + seeded reasons per stage | ☑ done | `8a79094`, `0e2812b` |
| 1 | D | `POST /wastage`: the paired write, the cost, idempotency | ☑ done | `0e2812b`, `0af0749` |
| 1 | — | **PR 1 gate: full `make check`** | ☐ | — |
| 2 | E | `GET /wastage` and the summary by stage and reason | ☑ done | `0e2812b` |
| 2 | F | The ten-second screen and the summary screen | ☑ done | `0abad84` |
| 2 | G | Seed, review, manual script | ☐ | — |
| 2 | — | **PR 2 gate: full `make check`** | ☐ | — |
| — | — | **Your manual pass** — `docs/manual-tests/M09-waste.md` | ☐ | — |

---

## What M08 taught this module, before a line of it is written

Four things cost time in M08 and are cheap to avoid here.

**1 · A change to the permission catalogue needs the auth suites re-run, not only the catalogue
suites.** Chunk C of M08 ran `test_permission_seed`, `test_permissions_catalogue` and
`test_database`, all green — and broke two tests that assert a waiter's permissions as a *literal
set*, in files it never ran. The literal is deliberate: widening a waiter's powers has to be an
edit somebody makes on purpose. M09 adds no permission to any role the design does not already give
it, and the check runs anyway.

**2 · Check the design file rather than the sentence in the spec.** The first draft of M09's spec
said "a waiter may log waste and may not approve". `seed/organization.yaml` says a waiter cannot log
waste at all — it is the chef, the kitchen staff, the manager and the store manager. Caught by
reading the file. The same mistake in code would have been caught by the permission matrix, a day
later.

**3 · A new error code needs an issue number in the same commit.** `test_every_raised_code_has_an_
issue` walks the syntax tree of `app/` and fails on any `raise ConflictError("x.y", …)` with no
entry in `issues.json` — and the catalogue needs its own migration, because a database that has
already run 0029 never re-reads the file.

**4 · Every write route commits; the service only flushes.** This is written at the top of
`app/api/v1/staff/inventory.py`, in a paragraph describing the exact symptom — "every write
returned `201` with a populated body and then vanished, because the session closed without
committing" — and M08's kitchen routes did it again anyway. **Twice in this codebase now.** No unit
test can catch it, because inside one transaction the write is visible to the code that made it;
only a second HTTP request sees the row is gone. M09's first endpoint test does two requests.

**5 · A route that never returns hangs a suite that calls everything.** M08's stream stopped a full
`make check` dead, because three of the generic suites walk the routing table. M09 adds no streaming
route, so this is a note rather than a risk — but `RouteInfo.is_stream` and the test pinning its one
member now exist, and a future module adding a second stream is covered.

**6 · Run the gate on a finished tree, not a moving one.** Two of M08's gate runs were abandoned
because the tree had changed underneath them. It takes about thirty-five minutes on this machine and
it blocks editing while it runs, so it is worth queueing properly rather than starting hopefully.

---

## Adversarial review — step 7 of the module loop

Checklist from `docs/testing-strategy.md` Part 1, walked over the whole M09 diff.

| Check | Result |
|---|---|
| Tenant leakage in a hand-written query | Clean — see below |
| Permission check in the route rather than the service | Clean; the generic matrix walks all seven routes |
| N+1 behind a lazy relationship | Clean — `WastageEvent.reason` is `lazy="raise"` and eager-loaded where the response needs it |
| Money touching a float | Clean — no `float(` anywhere in the module; `cost_value` is `Decimal` end to end and a string on the wire |
| Naive datetime | Clean — no bare `datetime.now()` |
| **Unit assumed rather than converted** | **Found and fixed** — see the commit `0af0749`. The API took base units, which would have forced the browser to convert |
| Unbounded query | Clean — the log pages, the summary is bounded by a date range, the reasons list is a restaurant's own dozen |
| Missing index for a new filter | Clean — `ix_wastage_event_restaurant_date` covers the summary and the log's date filter |
| Client-supplied cost trusted | **Structurally impossible**: there is no field for one, and `extra="forbid"` refuses a request carrying it |
| PII in a log line | Clean — ids, codes, stages and amounts |
| Error message leaking internals | Clean; and `wastage.approver_is_reporter` was written to avoid reading as an accusation |

**The summary's join is safe by construction, and it is worth contrasting with M08's.** The query
joins `wastage_reason` without a second tenant filter, exactly as M08's `routing_for` joins the
menu. The difference is the key: `wastage_event.wastage_reason_id` carries a **composite** foreign
key to `(wastage_reason.id, restaurant_id)`, which migration 0033 added, so a reason reached from a
scoped event cannot belong to another restaurant. M08's equivalent runs through
`menu_item_variant.menu_item_id`, which is a **plain** key from M03 — the backlog row that came out
of that review. Same shape of query, two different guarantees, and only one of them is airtight.

**No finding was left unfixed.** The unit-conversion one is the only thing this pass found, and it
was found before the screen that would have been wrong existed.
