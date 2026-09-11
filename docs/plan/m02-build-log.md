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
| A | Migration: 4 tables + `restaurant.fssai_licence` (S13) | ✅ done | `4a3c048` |
| B | The business-day helper, both languages (M11) | ✅ done | see below |
| C | Repositories, services, API — first use of `RestaurantScopedRepository` | ⬅ **NEXT** | — |
| D | shadcn components M02 needs: Select, Dialog/Sheet, Table, Switch, Label | ☐ | — |
| E | Four screens | ☐ | — |
| F | `POST /auth/switch` (S12) · theme settings · `reserved` by hand (S14) | ☐ | — |
| G | Manual script, adversarial review, `make check` | ☐ | — |

**Chunk B wanted high model effort** — see *Why B is the risky one* below. Everything else is
medium.

"Both languages" is Python and TypeScript — not SQL. There is no Postgres function in this module:
`business_date` is denormalised at insert by the application, so nothing in SQL needs to compute it
until M07 has orders to insert.

### What chunk B actually cost

The Python function was the small half. Four things came out of it that the chunk table did not
predict:

**1 · The IANA database was a host feature, not a dependency.** Sixteen of the first eighteen tests
failed on Windows with `ValueError: Unknown timezone 'Asia/Kolkata'`. `zoneinfo` reads the operating
system's copy, Debian ships one and Windows ships none — so the suite was green in the container and
red on the machine writing it. `tzdata` is now a runtime dependency, and `PYTHONTZPATH=""` in the
Dockerfile stops the image reading Debian's copy instead of the locked one. The first half fixes the
crash; the second half is the one that matters, because two hosts reading two different copies can
disagree about a timezone rule while both look perfectly healthy. Verified in a built image:
`TZPATH = ()`, `tzdata 2026.3`, same answer as the host.

**2 · `business_day_start` was not in the API contract.** The browser cannot apply the rule with the
zone alone, and the frontend helper is the whole point of M11 riding along here. Added to
`RestaurantSummary`, asserted on *both* `/auth/login` and `/auth/me` — a field present in only one of
them is a bug that appears on refresh and not on login.

**3 · Two frontend session fixtures had silently drifted from the contract.** They were untyped
object literals, so TypeScript inferred their shape instead of checking it against
`RestaurantSummary`, and they went on describing a response the server no longer sends. Now typed;
confirmed that removing a field fails compilation.

**4 · Defect 1 of M02 — `NewEmployeeScreen` defaulted "joined on" to the browser's UTC date.**
Between local midnight and 05:30 IST that is *yesterday*, so anyone adding staff on a late shift
recorded a joining date one day early, pre-filled and looking entirely reasonable. The existing
comment admitted the placeholder; nothing tested it, and no test rendered the screen at all.

### Two tests that lied, and the lesson repeating

`test_it_disagrees_with_utc_truncation_across_the_business_boundary` asserted that the business date
and the UTC date were **equal**, and said in a comment that they agreed by coincidence — under a name
claiming it proved they diverge. A reviewer reading the name would have believed the divergence was
covered. Replaced with a pair that is verified to reject each wrong implementation: truncating in UTC
fails one, truncating in local time fails the other, and neither can be caught by testing against the
other.

Then the same mistake happened again in the new frontend tests, and was caught the same way — by
running them against the old implementation instead of trusting a green run. Three of five passed
with the bug still in place.

**The rule this chunk earned:** a test that has never been observed to fail is not evidence. Both
defects were invisible to a green suite and obvious the moment the implementation was reverted under
them. This is the third appearance of the project's recurring lesson — a name or docstring asserting
a property the adjacent code does not provide.

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
