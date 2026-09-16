# M09 · Waste — Build Log

**Started 2026-09-16**, continuing the autonomous run from M08 on the owner's instruction
(*"continue with m08, m09, run autonomously"*).

Spec: `docs/modules/M09-waste-spec.md`. **Resume from the State table below.**

---

## State

| PR | Chunk | What | State | Commit |
|---|---|---|---|---|
| — | — | Research + spec | ☑ done | — |
| 1 | A | Migration 0033 + models + schema doc check | ☐ | — |
| 1 | B | Migration 0034: `wastage.log` / `wastage.approve` | ☐ | — |
| 1 | C | Reasons CRUD + seeded reasons per stage | ☐ | — |
| 1 | D | `POST /wastage`: the paired write, the cost, idempotency | ☐ | — |
| 1 | — | **PR 1 gate: full `make check`** | ☐ | — |
| 2 | E | `GET /wastage` and the summary by stage and reason | ☐ | — |
| 2 | F | The ten-second screen and the summary screen | ☐ | — |
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
