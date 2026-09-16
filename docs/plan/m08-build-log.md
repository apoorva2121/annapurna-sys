# M08 · Kitchen / KOT — Build Log

**Started 2026-09-16**, continuing the autonomous run from M07 on the owner's instruction
(*"continue with m08, m09, run autonomously"*).

Spec: `docs/modules/M08-kitchen-spec.md`. **Resume from the State table below.**

---

## State

| PR | Chunk | What | State | Commit |
|---|---|---|---|---|
| — | — | Research + spec | ☑ done | — |
| 1 | A | Pure-ASGI request context middleware + `status_code` (M4) | ☐ | — |
| 1 | A2 | argon2 off the event loop (P1-9, G-6) | ☐ | — |
| 1 | B | Migration 0030 + models + schema doc + enums | ☐ | — |
| 1 | C | Migration 0031: `kot.view` / `kot.update` grants | ☐ | — |
| 1 | D | Repository + ticket creation from `send()` | ☐ | — |
| 1 | — | **PR 1 gate: full `make check`** | ☐ | — |
| 2 | E | Transition state machine, timestamps, per-line ready, remake | ☐ | — |
| 2 | F | Revision cursor, `GET /kot/stream`, heartbeat, replay | ☐ | — |
| 2 | G | Reconciliation with M07: serve, cancel, late | ☐ | — |
| 2 | — | **PR 2 gate: full `make check`** | ☐ | — |
| 3 | H | KDS rail, ticket detail, remake, SSE hook, readability test | ☐ | — |
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
