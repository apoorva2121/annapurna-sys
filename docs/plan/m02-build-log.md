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
| E | Four screens | ✅ done | `336953b` |
| F | `POST /auth/switch` (S12) · theme settings · ~~`reserved` by hand (S14)~~ done in C | ✅ done | see below |
| G | Manual script, adversarial review, `make check` | ✅ done | see below |

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

---

## What chunk E actually cost

Four screens, an API layer of 15 hooks, 25 new frontend tests. 98 frontend tests in total; the staff
bundle is 129 KB gzipped against a 250 KB budget, up from 90.6 KB — Radix's Select and Dialog are
most of the difference, and that is the price of rule 4.

### The worked example is computed, not written

ADR 0004 calls `business_day_start` the setting owners misunderstand most, and the spec asks for a
worked example under the control rather than a tooltip. The obvious implementation is a sentence in
the strings file. That sentence would be a **second statement of the rule** — free to drift from the
first, with no way for the reader to tell which one the server obeys, and stale the moment anyone
changes the value on screen.

So `businessDayExample()` derives it by running `businessDateOf`, the same function the server
mirrors. It is wrong only if the rule itself is wrong. At 05:00 it produces exactly the spec's
sentence: *"An order at 01:30 am on Tuesday counts towards Monday's sales."* At midnight it returns
`null` and the screen says the business day is the calendar day, rather than inventing an example
for a case that has none.

### A test that would have proved nothing

The test for the above originally changed the control from 05:00 to **02:00** and asserted the
sentence still read "01:30 am". It passed — and would have passed against a hardcoded string, because
the example is anchored at 1:30am for *any* start later than 1:30am. The test's name claimed it
proved re-computation; its assertion proved nothing of the sort.

Rewritten to use 01:00, where the example has to move to 12:30 am. Verified by replacing the computed
sentence with a hardcoded one: that test fails and the other five still pass, which is precisely why
it is the one that matters.

This is the fourth time in M02 that a test has claimed more than it asserted. The pattern is now
familiar enough to name as a check: **pick the input where the right implementation and the wrong one
disagree — if you cannot name that input, the test is decoration.**

### A deliberate deviation from the approved spec

The spec says "dining areas and tables (drag to reorder)". This ships move-up/move-down buttons.
Recorded in `docs/backlog.md` with the reasoning rather than done quietly: drag needs a library and
needs a keyboard path built alongside it to be usable, buttons *are* that keyboard path, they work
with a glove and a steamed screen, and they write the same `seq`. Adding drag later is additive.

Also recorded there: reordering is two `PATCH`es and is not atomic. If the second fails two areas
share a `seq`; the list stays deterministic because the query orders by `(seq, id)`, so nothing
breaks visibly — but the order is not what was asked for and nothing says so. Both backlog rows want
the same fix, a `reorder` endpoint taking the whole ordering.

### jsdom needed two polyfills

`ResizeObserver` and `scrollIntoView` do not exist in jsdom, and Radix reaches for both. Every test
rendering a Switch, Select or Dialog died with `ReferenceError: ResizeObserver is not defined` —
a failure about the environment that reads like a failure about the component. Stubbed in
`test-setup.ts`, with a note that jsdom has no layout, so anything genuinely depending on measured
size cannot be tested there at all and belongs in a browser test.

---

## What chunk F actually cost

`POST /auth/switch`, the restaurant-wide theme, and the festive schedule. Migration 0006, 12 new
backend tests against a two-organization two-branch fixture, 8 new frontend tests. 387 backend and
110 frontend tests.

### The bug `auth/switch` would have shipped with

Switching mints an access token scoped to the new branch. Access tokens last fifteen minutes, and
`refresh()` resolved the restaurant through `_home_restaurant()` — which returns the person's
*first* one. So the switch would have worked and then silently undone itself, mid-task, with no
error and nothing on screen to explain it. It would have been reported as "the app keeps jumping
back to the other branch", which is not a sentence anyone can debug.

`user_session.restaurant_id` (migration 0006) is the fix. It is a **preference, never an
authorisation**: `refresh()` re-checks the assignment every time and falls back to the home branch
if the role is gone, so a stale value can cost a redirect and cannot grant access. There is a test
for exactly that — remove the role at the switched branch, refresh, land at home.

### Two things I got wrong on the way

**The endpoint first returned `MeResponse`, which has no access token.** The client would have kept
using its old token — still scoped to the old branch — so the endpoint would have reported success
and changed nothing. Caught by the tests, which read the restaurant out of the *token* rather than
out of the response body, deliberately: the body is what the server says, the token is what every
later request is actually scoped by.

**The boundary tests passed before the endpoint existed.** A route that is not registered answers
404, and three tests asserted only `status_code == 404`. They now assert the error *code* as well,
so an unimplemented endpoint cannot masquerade as a refusal. Fifth time this module that a test
claimed more than it asserted.

### The theme had to travel in the session

`/staff/restaurant` is owner-and-admin-only, and a theme has to render for the waiter too. So
`RestaurantSummary` carries it, the same decision `business_day_start` got in chunk B and for the
same reason. `RestaurantSummary.of()` lifts it out of the `settings` JSONB in one place, because
four endpoints build that summary and a theme appearing on three of them is a bug nobody notices
until one screen looks wrong on one day of the year.

Overlapping festive windows are **refused rather than resolved by precedence**. There is no right
answer for a date claimed twice, and silently picking the first would make the second window
disappear on a day nobody is watching.

**A person's own device choice outranks the festival.** Otherwise the manager who set dark mode for
a dim back office loses it for a week in November because of a setting somebody else changed.

### Deploy skew is a real failure mode, found by the test suite

Adding two required fields to the session type crashed every screen in the suite: fixtures without
them made `session.restaurants.length` throw, and the whole React tree went with it. That is not a
test artefact — during a deploy the app and the API are briefly different versions, and a field the
server has not started sending yet must degrade, not white-screen every signed-in user.

The wire types now mark both fields optional and the session mapper fills them in, so the internal
type stays honest while the boundary stays tolerant. The distinction is worth keeping: *optional on
the wire, guaranteed after mapping.*

---

## What chunk G actually cost

Manual script (`docs/manual-tests/M02-restaurant-setup.md`), adversarial review, `make check`.

### The review found the module was not demonstrable

Two findings, both of which would have made the manual pass start with an apology:

**1 · `make seed` produced an empty floor.** M02's master data — two dining areas, fourteen tables,
three stations, two tax rates — has been in `seed/operations.yaml` since M00 and validated by
`seed/validate.py` ever since. Nothing loaded it, because there was no table to load it into until
this module built one. Every M02 screen opened blank on seeded data, and the manual pass would have
begun by hand-building a floor plan before it could test anything. `app/seed/setup.py` now loads it.

**2 · `POST /auth/switch` was unreachable in the demo world.** The seed has two restaurants, but in
two *different organizations* — nobody worked at two branches of one company, so the switcher
rendered nothing and chunk F's headline feature could not be exercised by hand at all. The seed now
has a second Spice Garden branch and one dual posting: Vikram is a **manager at Koregaon and a
waiter at Baner**, junior on purpose so switching visibly changes what he can do.

Both are the same class of defect and it is worth naming: **the feature was finished and the world
it lives in was not.** Tests passed because tests build their own fixtures. A demo that cannot show
a feature is a feature nobody will check.

### The finding I did not fix

**A superseded tax rate has nothing pointing at its successor.** `menu_item_variant.tax_group_id`
references one `tax_group` row directly (schema §3), and M02's rule is that a rate change is a new
row. So on a changeover every menu item points at the closed row with no link to the replacement.

History is safe — `order_line.tax_rate` is copied at order time — so this is not corruption. The gap
is the forward step: somebody must re-point every menu item, and neither a mechanism nor a screen
exists. `seed/operations.yaml` already gives each rate a `code` (`GST5`) that is exactly the stable
family key required, and the schema has no column for it.

Left unfixed **deliberately**: it changes an approved schema, M06 is the first module that depends
on it, and an external review is about to look at the same code. In `docs/backlog.md` with M06 as
the un-defer trigger, and called out in the manual script so the decision is visible rather than
buried.

### Scoreboard

Six defects across M02, and the shape of them is consistent: **five were things that read as
working and were not.**

| | Found by |
|---|---|
| The tzdata dependency was a host feature | running the tests on a second machine |
| `NewEmployeeScreen` defaulted to yesterday's date | asking what the browser's clock actually returns |
| The permission-seed guard could not fail | changing the catalogue and watching nothing break |
| Tenant isolation skipped every new route | counting what the loop actually probed |
| `make seed` built an empty floor | asking what the manual script would open on |
| `auth/switch` was unreachable in the demo | asking who, in the seed, works at two branches |

Not one came from reading the code approvingly. Every one came from asking what would have to be
true for it to be broken, and then checking that specific thing.
