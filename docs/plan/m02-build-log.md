# M02 · Restaurant Setup — build log

**Resume from here.** If a session ended mid-module, read this file first, then `git log --oneline`
to see which chunks actually landed. Written after each chunk is committed, so it can be trusted
about the past and not about the future.

Spec: `docs/modules/M02-restaurant-setup-spec.md` (approved 2026-09-11, four decisions answered).
Branch: `feat/m01-identity` — M01 and its remediation are merged into this line of work.
Before any code: `docs/engineering-guardrails.md` and `.claude/skills/restaurant-ui/SKILL.md`.

---

## State

| Chunk | What | State | Commit |
|---|---|---|---|
| A | Migration: 4 tables + `restaurant.fssai_licence` (S13) | ⬅ **NEXT** | — |
| B | The business-day helper, both languages (M11) | ☐ | — |
| C | Repositories, services, API — first use of `RestaurantScopedRepository` | ☐ | — |
| D | shadcn components M02 needs: Select, Dialog/Sheet, Table, Switch, Label | ☐ | — |
| E | Four screens | ☐ | — |
| F | `POST /auth/switch` (S12) · theme settings · `reserved` by hand (S14) | ☐ | — |
| G | Manual script, adversarial review, `make check` | ☐ | — |

**Chunk B wants high model effort** — see *Why B is the risky one* below. Everything else is
medium.

---

## Why B is the risky one

`business_date_of(moment, timezone, day_starts_at)` decides what a *day* means. Every report in
M13, every shift figure in M17 and the 120-day generator in M15 group on the `business_date` it
produces.

It is dangerous because **wrong answers are plausible rather than obviously broken.** A 01:30 order
booked to the wrong day looks completely normal until a month-end total is out by one night's
takings, and by then the data is months deep. Nothing downstream can detect it, because everything
downstream trusts it.

The test that matters most is the one that deliberately contrasts it with naive
`date_trunc('day', created_at)` — the implementation someone reaches for when they have forgotten
this module exists.

---

## Decisions carried in from the spec

1. `business_day_start` and tax rates: **owner/admin only**.
2. A tax rate is **never edited in place** — a change is a new effective-dated row.
3. `restaurant_table.status = 'reserved'` **stays**, set by hand (S14 closed).
4. `POST /auth/switch` is **in** (S12 closed).

## Inherited obligations

- **G-13** — the schema checklist is answered for all four tables in the spec. Do not add a fifth
  table without answering it again.
- **G-17** — identity-touching tests run against the two-branch, two-organization fixture. `auth/switch`
  is identity-touching.
- **ADR 0008** — master data is deactivated, never deleted.
- Every new route declares a permission, or the route-declaration suite fails the build.
