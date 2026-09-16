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
