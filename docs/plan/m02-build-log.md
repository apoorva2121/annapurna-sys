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
| B | The business-day helper, both languages (M11) | ✅ done | `38ba3bd` |
| C | Repositories, services, API — first use of `RestaurantScopedRepository` | ✅ done | `c086e59` |
| D | shadcn components M02 needs: Select, Dialog/Sheet, Table, Switch, Label | ✅ done | `e9caff2` |
| E | Four screens | ⬅ **NEXT** | — |
| F | `POST /auth/switch` (S12) · theme settings · ~~`reserved` by hand (S14)~~ done in C | ☐ | — |
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

---

## What chunk C actually cost

11 endpoints, 5 repositories, 1 service, 19 schemas and migration 0005, behind one permission
(`restaurant.configure`, owner and admin only). 366 backend tests, 98% coverage.

The CRUD was the small half. Three defects came out of it, and **all three were invisible to a
green test suite** — which is the only thing about this chunk worth remembering.

### Defect 1 · The permission-seed guard could not fail

`tests/test_permission_seed.py` says, in its own docstring: *"editing the file without shipping a
migration fails the build and says so."* It cannot. Migration 0002 **reads** `permissions.json` at
migration time, and the test database is built by running migrations — so the file and the database
always agree, whatever the file says. Adding `restaurant.configure` to the catalogue with no
migration left all eight of those tests green.

The case it misses is the only one that matters: a database that has already run 0002. Alembic will
not re-run it, the permission never arrives, and owner and admin silently lack it **in staging**
while every test passes locally.

Fixed by fingerprinting the catalogue's content (canonical JSON, `_` keys excluded) and asserting
some migration declares that exact hash. Verified in both directions: a real access-control change
fails the build and names the migration to copy; a readme edit does not.

### Defect 2 · The tenant-isolation suite covered none of this module

Suite 1 is titled "across every staff route". It matched `{employee_id}` and `continue`d past
everything else. M02 added four PATCH routes taking `{area_id}`, `{table_id}`, `{station_id}` and
`{tax_group_id}` — the four routes in this module where a cross-tenant **write** would happen — and
the suite went on passing while probing none of them. Measured: 24 staff routes, 6 probed, 4 with an
id skipped entirely.

Rewritten to seed one row of every tenant-owned kind and substitute by parameter name. The important
half is the new guard next to it: **an unknown path parameter now fails the suite** rather than being
skipped, so a module adding `{menu_item_id}` gets a failing build telling it to seed a victim row.
Silence was the bug; the fix is that silence is no longer possible.

Proved rather than asserted. Sabotaging one repository's scoping produces exactly what it should:

    cross-tenant access succeeded on: ['PATCH /api/v1/staff/setup/dining-areas/{area_id} -> 200']

and removing a victim row fails the guard by name.

### Defect 3 · `{"name": "   "}` returned 201

`min_length=1` runs *before* an "after" field validator, so three spaces satisfied the constraint and
were then stripped to nothing — creating a dining area with an empty name, and a 201 saying it went
well. Stripping moved to a `mode="before"` validator, where the constraint sees what will actually
be stored. One fix, four fields.

### The lesson, for the third module running

Every one of these was a test or a guard that **read** as protection and provided none. B had two
tests whose names claimed the opposite of what they asserted; C had a guard that could not fail and
a security suite that skipped what it claimed to cover.

The only thing that found them was refusing to accept green: reverting the implementation under the
test, sabotaging the scoping, removing the victim row. A test that has never been observed to fail is
not evidence — and neither is a suite whose loop body never ran.

---

## What chunk D actually cost

Six components vendored through `npx shadcn@latest add` — Select, Dialog, Sheet, Table, Switch,
Label — adapted to our tokens. Four Radix packages plus `lucide-react` and `@testing-library/user-event`.
84 frontend tests, staff bundle 90.6 KB gzipped against a 250 KB budget.

**The backlog entry "Initialise shadcn/ui properly" was stale and is now closed.** It claimed M00
never ran `shadcn init` and asked for a decision before M07. `components.json` has existed since
`5271616`, correctly aliased, with a genuinely shadcn-derived Button. Chunk D settles it in practice:
the library is the design system. Worth noting that the entry was written when it was true and
quietly stopped being true — a backlog is as capable of lying as a docstring.

### What the generator gets wrong, every time

Three defects arrived with the generated source, none of which it reports:

1. **The import alias is wrong.** It wrote `@shared/shared/cn` in all six files — `tsc` catches it,
   but only because the alias does not resolve. A generator that had written a path which *did*
   resolve to something else would not have been caught.
2. **`lucide-react` is imported and not installed.** Three of the six need it; the generator added
   four Radix packages and not that one.
3. **Raw `z-50`, `shadow-*` and `bg-black/80`.** Every one of these is exactly what the token layer
   exists to prevent — a raw z-index is, in tokens.css's own words, "a bug waiting for a second raw
   z-index".

All three are now written down in `docs/ui/design-system.md`, because they will recur on the next
`shadcn add` and nothing detects them automatically.

### The scrim became a token

`bg-black/80` is a palette colour: no theme and no ADR can reach it. It is now `--scrim`, in the
**locked** layer alongside the alert colours and the z-index ladder — the scrim is the only thing
separating a modal from the live order behind it, and a festive theme that tinted or lightened it
would turn "deal with this first" into decoration. Verified it reaches the built CSS rather than
trusting the build, because this project has already lost an entire theme layer to an `@import`
in the wrong place.

### A docstring that had to be proved

`switch.tsx` claims the label is part of the hit area — the control is 24px, under `--target-min`
on every surface, so the words are what a waiter actually taps. That claim is not obviously true: a
`<label for>` does not natively activate a `<button>`, and Radix Switch renders a button.

It is true, and `src/shared/ui/ui.test.tsx` now holds it. Pointing `htmlFor` at a different control
fails that test and only that test, so it is testing the association rather than a click that
happened to land nearby.

That file exists for a narrower reason than "test the components": `shadcn add` **overwrites** these
files. An adaptation that is only described in a docstring returns to the generated default on the
next upgrade, silently. Anything a docstring here asserts that the code could stop doing belongs in
that test.
