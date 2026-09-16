# M10 · Customers, Feedback & Guest App — Module Spec

**Depends on** M07 (orders, tables, the bill), M03 (the guest menu tree, built and never routed).
**Status** — spec written 2026-09-16, before any code, per `docs/sdlc.md` step 1.
Build log: `docs/plan/m10-build-log.md`.

Tables: `customer`, `customer_preference`, `customer_consent` (new — see decision 4), `feedback`,
`feedback_line`, `complaint`.
Endpoints: staff customer CRUD, history, preferences, consent, DPDP export and erasure, the
complaint workflow; **the first guest routes this product has ever served**.
Screens: customer profile with preferences and complaint tracking; **the guest PWA** — a second
bundle, QR → menu → three questions.

---

## Why this is the module that can hurt us

Every module until now served fifteen known people on restaurant-owned devices. This one serves
thousands of strangers on their own phones, over a hostile network, at a URL printed on a table.

ADR 0009 was written for exactly this day, and it is unambiguous: employee and customer are **two
applications**, separated structurally rather than by a conditional, because "a single codebase with
a shared middleware stack means every new endpoint is one forgotten permission check away from
exposing staff data to the public internet. The blast radius of that mistake is the whole business."

So the acceptance criterion that matters here is not a screen. It is: **no guest token reaches any
staff route, and no guest response can carry a staff field — and both are true because the code
makes them impossible, not because we remembered.**

The second half of the module is the reason it exists commercially. `docs/customer-experience.md`
opens by rejecting the vision doc's premise: ratings are "the *least* useful CX data a restaurant
has". **Most unhappy diners in India never complain; they just don't come back.** The product's job
is to catch dissatisfaction nobody said out loud — and the data that does it (KOT timestamps,
returns, gaps between rounds) is already in the database from M07 and M08. M10 adds the customer
those signals hang off, and the three-question form that is the one thing worth asking directly.

---

## Research — what binds this module, checked 2026-09-16

**`docs/compliance-rules.md` §B2 binds this module, and it is the one rule in the file that cannot
be added later.** Stated exactly as the file states it, because CLAUDE.md forbids filling an Indian
date from memory:

> DPDP Act 2023. Rules notified 13 Nov 2025, commencing in three phases: Phase 1 (13 Nov 2025 ✅)
> Board constituted; Phase 2 (13 Nov 2026) Consent Manager registration; **Phase 3 (13 May 2027)**
> notice, consent, security, breach, children's data, rights, penalties.
>
> "Consent architecture cannot be retrofitted — you cannot lawfully re-derive consent never
> captured. So build to the Phase 3 standard in M10, but **do not describe these obligations as
> currently in force**."

Three consequences this spec holds itself to:

1. **Build to the Phase 3 standard now** — one consent row per purpose, withdrawal as easy as
   granting, notice version and language retained, erasure on purpose completion.
2. **Say nothing, anywhere in the product, that calls these obligations current law.** Not in a
   screen, not in a tooltip, not in a commit message. They are notified and not yet commenced, and
   §B2 of `docs/compliance-rules.md` distinguishes those two states precisely because conflating
   them is how this project has been wrong before. M18 is the module that surfaces compliance risk
   to an owner; M10 builds the mechanism and stays quiet about it.
3. **No retention period is asserted in this module.** Erasure keeps the order because a financial
   record must be retained — *how long* is a number none of us may write from memory, and no code
   here needs it. When a retention clock is built, it is researched and cited first.

**`docs/security.md` §"The guest surface is hostile input"** gives five rules, all binding: tokens
short-lived (~2h) and scoped to one table at one restaurant; aggressive per-IP and per-token rate
limits; guest responses carrying no cost, margin, recipe, employee name or another guest's data,
enforced by *separate schemas*; feedback write-limited against rating manipulation; and **no
enumeration — a guest lookup by phone returns the same response whether or not the number exists.**

**`docs/backlog.md` carries a prerequisite with this module's name on it.** "Live competitor UX
research for the guest app — **Do before M10**": `docs/ui/brand.md` §7 was written from this
project's own material because the session that wrote it had no search budget left. The guest app is
the one surface a diner compares to something they use every week, so §7 is revised from live
research — with sources cited — as part of chunk G, before the guest screens are designed. If the
research cannot run, that is recorded as an unmet prerequisite rather than quietly skipped.

**What already exists and must not be rebuilt:**

- **The guest menu tree.** M03 built `GuestCategory` / `GuestItem` / `GuestVariant` and the
  persona filter, shipped no screen, and covered it in `tests/test_menu_tree_guest.py`. M10 routes
  it. The decision about what a diner may see was made when nothing depended on the answer, which
  was the entire point.
- **`order.customer_id`** — a bare column since M07, deliberately without a foreign key, "the same
  arrangement M05 used for `supplier_id`". M10 is the module that adds the table it points at.
  The FK is added here.
- **`order.bill_requested_at` and `settled_at`** — bill-to-settle, which
  `docs/customer-experience.md` calls "the single most complained-about moment in Indian dining", is
  already measurable. M10 does not compute it; M13 does. M10 makes sure the feedback that explains
  it is attached to the same order.
- **`app/api/v1/guest/__init__.py`** and **`frontend/src/guest/`** — both empty, both held open
  since M00 with a README stating the rule. This module fills them.

---

## The ten decisions that matter

### 1 · Two QR codes, not one, and they grant different things

The obvious design is one QR per table that does everything. It fails on a fact `docs/security.md`
states plainly: **a photographed QR code is effectively public.** A sticker on table 4 is
photographed once and is then a permanent credential, held by a stranger, for whatever is happening
at table 4 tonight.

So the module ships two, with different lifetimes and different powers:

| | **Table QR** (sticker on the table) | **Bill QR** (printed on the bill / bill folder) |
|---|---|---|
| Carries | `restaurant_table.guest_slug` — opaque, rotatable, public | a random per-order token, **stored hashed** |
| Mints | a guest token scoped to *one restaurant*, ~2h | a guest token scoped to *one order*, expiring 24h after settlement |
| Grants | the guest menu, and nothing else | that order's own lines and total; one feedback submission |
| If photographed | the menu, which is on the wall anyway | one order's dish list, until it expires |

This is the whole answer to "what does a stolen QR get you", and the answer is: the menu. The order
data lives behind a token that is minted per order and dies with it. `docs/customer-experience.md`
asks for the feedback QR "on the bill folder" for a reason unrelated to security — response rates —
and the two reasons happen to want the same design.

`guest_slug` is rotatable by a manager (`POST /staff/tables/{id}/rotate-qr`) precisely so a
restaurant that reprints its stickers can kill every photograph taken of the old ones.

**The bill token is stored as a hash, never in the clear.** `hash_refresh_token` already exists and
exists for this reason: "a stolen dump yields no live sessions". The raw token is generated when the
bill is requested, returned once to the staff client that draws the QR, and never readable again.

The consequence is a feature: **a reprinted bill carries a new QR, and the old one stops working.**
A bill folder left on a cleared table is a token in a stranger's hands, and reprinting is exactly the
moment a restaurant wants that to stop being true.

**Where it is minted, and why not in `request_bill`.** M07 already has
`POST /staff/orders/{id}/bill`, which answers with `OrderResponse` — and the raw token must be
returned exactly once, to exactly the client that is about to draw a QR with it. Folding it into
that response would put a live credential into the shape every order read returns, and the first
time somebody reuses `OrderResponse` somewhere else it travels with them. So it is its own route,
`POST /staff/orders/{id}/guest-qr`, behind the same `order.modify` that `request_bill` uses, and
calling it again is what a reprint does. A route whose entire purpose is "hand me a credential"
is easier to audit than a field on a response that usually does not carry one.

### 2 · The guest realm is a different token type, and it cannot be widened into a staff one

`issue_access_token` already takes a `token_type` and `decode_access_token` already refuses a token
whose `typ` is not `access` — that check exists because "a refresh token presented as an access
token would extend a session far past its intended life". The guest token reuses that machinery and
nothing else:

- `typ: "guest"`, and `decode_guest_token` refuses anything else, symmetrically.
- **No `prm` claim at all.** Not an empty list — absent. A guest token carries no permission
  vocabulary, so there is no string an attacker can add to it that any staff dependency would
  recognise.
- `sub` is not an employee id. It is the subject of the scope, and `scp` says which kind it is —
  a table or an order. No `org`: which organization a restaurant belongs to is how a chain
  recognises a diner across branches, and it is none of a table's business.
- A separate dependency chain in `app/api/guest_deps.py`, which imports nothing from
  `app/api/deps.py`. It constructs no `Actor` and knows no permission string, so a guest scope
  cannot be passed to `require_permission` — the isolation is a type error, not a convention.
- **Re-verified against the database on every request**, the way `current_actor` re-resolves
  permissions rather than trusting the claim. For an order scope the token carries the first
  sixteen characters of the stored hash, so a reprinted bill stops every session opened from the
  old QR at its next request instead of letting it live out its expiry.
- **A third repository base class.** `ScopedRepository` has two subclasses today because "the threat
  model has two attackers"; the guest realm is a third, and it cannot use either — a `TenantScope`
  needs an `organization_id`, and the guest token deliberately does not carry one. So
  `app/repositories/guest.py` holds a `GuestScopedRepository` that takes a `GuestScope` and filters
  on `restaurant_id` alone. The Definition of Done's "tenant scoping through the repository layer
  only" then holds on the guest side too, and no guest query can reach a staff repository, because
  the scope object the staff ones require does not exist in that realm.

`tests/test_generic_suites.py` already mints a `typ: "guest"` token and asserts no staff route
accepts it. That suite has been passing vacuously against a realm that did not exist; from this
module it passes against a real one.

### 3 · Every guest response comes from `app/schemas/guest.py`, and three tests enforce it

ADR 0009's consequence — "Some serialisation logic is duplicated between staff and guest schemas.
**That duplication is the feature**" — only holds if the duplication is structural. Three rules,
each with a test that walks the routing table and fails the build:

1. **Every guest route's `response_model` is defined in `app/schemas/guest.py`.** A route answering
   with a staff schema fails.
2. **Every model reachable from one of those is defined there too.** The leak is never in the
   top-level schema; it is three levels down, in something reused because it looked harmless.
3. **No field in that graph is named like an internal one** — `cost`, `cost_value`, `margin`,
   `recipe`, `station`, `prep_minutes`, `code`, `is_active`, any `*_employee_id`, or the tenant
   columns.

modules.md asks for the third — "a guest response schema containing a cost field fails the build" —
and rule 2 is what makes it hold: rule 3 catches a bad field, rule 2 catches the reuse that put it
there. Together they are the only control that survives a tired afternoon.

The deliberate exceptions are named in the test, so that allowing them is a decision somebody made
rather than a gap somebody left: `price`, `price_delta`, and the bill's own totals. What the guest
pays is not what the dish cost.

**Writing the rule found two leaks that are already in `main`.** Neither ever reached a guest -
there has been no guest route until this module - but both have been in the schema since M03, and
routing the tree is what would have shipped them.

1. **`GuestItem.modifier_groups` is the *staff* `ModifierGroupResponse`.** It carries `code` and
   `is_active`, on the group and on every modifier inside it. So a menu that carefully withholds
   `BUTTER_CHICKEN` hands over `EXTRA_CHEESE` one level down.
2. **`GuestVariant` has a `code`.** M03's own test file says why it should not: "internal codes.
   `BUTTER_CHICKEN` is a join key, not a label."

`tests/test_menu_tree_guest.py` caught neither, because it asserts about the fields somebody thought
to look at. **That is the argument for rule 2 in one example**: a field blocklist needs a person to
think of `code` on a modifier three levels down. A rule that walks the graph does not have that
failure mode.

Fixed here, with the regression test written first (CLAUDE.md): `GuestModifierGroup` and
`GuestModifier` join the guest module carrying a name, a price delta and the selection rules, and
`GuestVariant` loses its `code`.

### 4 · Consent is a ledger of one row per purpose, never a column on the customer

`docs/schema.md` §9 lists five tables for this module. **This spec adds a sixth**, because §B2's
standard cannot be met by any of the five: *one consent row per purpose, never a single boolean*.

```
customer_consent                         -- append-only. Current state is the latest row per purpose.
  organization_id NN, customer_id NN FK→customer
  purpose      text NN check(order_contact|service_recognition|feedback_followup|marketing)
  granted      bool NN                   -- a withdrawal is a new row with granted=false
  notice_version  text NN                -- which words they were shown
  notice_language text NN                -- and in which language
  source       text NN check(qr|app|staff|call)
  captured_by  uuid FK→employee          -- null when the guest ticked it themselves
  occurred_at  timestamptz NN
  IX (customer_id, purpose, occurred_at DESC)
```

Four properties, each from §B2 or `docs/security.md`:

- **Per purpose.** "A phone number collected for a bill is not marketing consent." `order_contact`
  and `marketing` are different rows, and granting one grants nothing else.
- **Withdrawal as easy as granting.** Staff can do either on the profile; the guest surface can
  **only withdraw**, and that asymmetry is deliberate. A grant is a claim about a person, and the
  guest surface cannot verify who is holding the phone — so a bill token may take a consent away
  and may never hand one out. The only place a guest grants anything is the feedback form they
  typed their own number into.
- **The notice is versioned and its language recorded.** What somebody was shown is part of what
  they agreed to; a consent whose words are unrecoverable is not evidence of anything.
- **Append-only**, like `stock_movement` and `task_event`. A consent history that can be rewritten
  proves nothing, and DPDP's whole mechanism is proof.

**Never pre-ticked.** The frontend test walks the feedback screen's source for a `defaultChecked` or
a `checked={true}` on the consent control and fails the build on either — the same shape as
`wasteDiscipline.test.ts`, because a rule that lives only in prose is a rule the next screen written
in a hurry quietly skips.

**And the version recorded is the version displayed.** A `notice_version` column is worth nothing if
it names a notice nobody was shown. The canonical text of every version lives in
`docs/consent-notices.md`; `app/core/consent.py` names the current one; `src/guest/consentNotice.ts`
carries the same constant and the words the guest actually reads; and a test asserts the two
constants match — the same mechanism as `tests/test_enum_mirror.py`, for the same reason. A notice
edited on one side and recorded from the other is a consent record that proves nothing.

### 5 · Two ids: the organization owns the person, the branch owns the view

**Decided with the owner, 2026-09-16**, in answer to a direct question about whether one
restaurant's data can reach another. Their words: *"manager can generally look into one branch,
provision should be there that if required he is allowed to manage other branches as well. Owner
should be able to see analysis per branch and full organization as well, so I think we should have
an organization id and a branch id, so that later it can be easy to handle."*

That is exactly right, and it resolves a tension `docs/schema.md` §9 leaves open. The schema scopes
`customer` to the organization so "a chain recognises the same diner across branches" — which is
correct and is the whole reason a regular's allergy is known at the second branch. But scoping the
*row* to the organization was silently also scoping the *view* to it, which would let a manager at
one branch read the whole chain's customer book. Those are two different questions and they get two
different answers.

**The row is the organization's.** `customer.organization_id`, one row per person per business, with
`UNIQUE (organization_id, phone)`. Ravi eating at Koregaon Park on Tuesday and walking into Baner on
Friday is one Ravi, on his seventh visit, whose allergy nobody has to ask about again.

**The view is the branch's.** `customer.home_restaurant_id` records where a person was first written
down, and a customer list shows the customers of the branches **the person reading it is assigned
to** — anyone with an order at one of those branches, or whose home branch is one of them.

**And "provision to manage other branches" needs no new permission, because this product already
has the gesture.** `employee_role_assignment` ties an employee to a *restaurant*, and
`/me/restaurants` is the switcher M01 shipped. The filter is therefore the simplest possible one:
**the branch the actor is currently working in** — `TenantScope` already carries it, so it costs no
extra query. A manager assigned to Baner as well switches to Baner and sees Baner's customers; a
manager who is not, cannot. The answer to "can this manager see that branch?" is always "only if you
assigned them to it", which is the same sentence that already governs every other screen in this
product. That is worth far more than a permission invented here whose rules nobody would remember —
and it keeps the shipped catalogue a subset of the P1 design, which a fifth code would have broken.

Concretely, a customer is "this branch's" if **they have eaten here, or here is where they were first
written down**. The second half matters on the first day of a second branch: a customer created at
the counter has no orders yet, and without it they would be invisible to the person who just typed
them in.

**The owner's analysis needs nothing added.** Per branch and whole organization both come off
`order.restaurant_id`, which has existed since M07. M13 slices either way without a schema change,
and this module does not have to guess which one it will want.

**What is enforced, and where:**

| | Enforced by |
|---|---|
| Another organization's customers are unreachable | `OrgScopedRepository` + the generic tenant suite, as with every other table |
| A branch sees only its own customers | `CustomerRepository._at_this_branch()`, applied to every multi-row read, with its own test |
| A manager gains a branch | An assignment, not a permission — M01's mechanism |
| The same person is one record across branches | `UNIQUE (organization_id, phone)` |

The hard tenant boundary is unchanged and is still the organization: the branch filter is a *view*
rule inside one business, and nothing about it can widen into reading another business's rows,
because the scope object that would be needed cannot be built.

### 6 · Erasure anonymises and keeps the money

`docs/security.md`: "Erasure anonymises the customer row and keeps the order (financial records must
be retained); it does not cascade-delete revenue history."

`POST /staff/customers/{id}/erase` therefore:

- **Overwrites** `phone`, `name`, `email`, `birthday`, `anniversary` on `customer`; deletes every
  `customer_preference`; stamps `erased_at`.
- **Keeps** the `customer` row, every `order.customer_id` pointing at it, every `feedback` row, and
  every rupee. The acceptance test is modules.md's: **erasure leaves revenue totals unchanged**.
- **Keeps** the `customer_consent` ledger, with the personal data gone. What remains is "consent for
  marketing was granted on this date and withdrawn on that one" against an id that no longer names
  anybody — which is the record that proves the erasure was lawful.
- `phone` is the natural key and it is NOT NULL, so erasure writes a non-colliding placeholder
  (`erased:<id>`) rather than a null. **A consequence to say out loud: after erasure the same person
  returning is a new customer, with no history.** That is what erasure means, and it is the right
  answer, but it is the sort of thing an owner should hear before they press it — so the screen says
  it, in those words.

`GET /staff/customers/{id}/export` is the access right: every row about that customer, as JSON, in
one response. Built now and not later, because §B2 is right that it becomes a scramble otherwise.

### 7 · Three questions, and never a fourth

`docs/customer-experience.md`: "Three questions maximum. Food, service, would-you-return. Free text
optional. **Every extra question halves completion.**"

`docs/schema.md` §9 gives `feedback` four rating columns (overall, food, service, cleanliness). The
QR form asks **two of them plus a yes/no**, and this spec adds the yes/no:

- `food_rating`, `service_rating` — 1..5, tapped.
- `would_return` — bool, new column. It is the question that predicts revenue and no existing column
  holds it.
- `comment` — optional, never required.
- `overall_rating` and `cleanliness_rating` stay in the schema, stay nullable, and are **not asked by
  the QR form**. They exist for `source in (staff, call)` — a manager recording a conversation is
  not filling a three-tap form.

**Never ask twice in one visit** is a unique index, not a UI rule: one `feedback` row per order.
A second submission returns the first, unchanged, rather than an error — the guest tapped twice on a
slow network, and an error screen for that is a rudeness.

**Anonymous is the default and is fully supported.** No phone, no name, no tick: submit and leave.
The feedback is still order-linked, which is the only linkage that matters — `customer_experience.md`
calls unattached feedback "nearly worthless" because it cannot reach the dish, the waiter, the
station or the prep time, and the bill token supplies all four without the guest identifying
themselves at all.

### 8 · Recovery is measured, not typed

`complaint.customer_returned` is described in `docs/schema.md` as "the only honest measure of
recovery". It is also the field nobody will ever update: it becomes true weeks later, when whoever
logged the complaint has forgotten it exists.

So **it is derived, never written — and the column is not created.** A complaint's
`customer_returned` is computed at read time: does an `order` exist for that `customer_id` with
`placed_at > resolved_at`? One query, always current, impossible to flatter.

`docs/schema.md` §9 lists `customer_returned` as a column, and this spec deviates from it
deliberately: a column nothing writes, sitting beside a derivation that is always right, is an
invitation for somebody to write it — and the moment they do, the honest measure has a stale copy
that disagrees with it. It arrives in M13 if and when a monthly figure needs freezing, which is the
one case a column is the right answer. `docs/schema.md` is updated in the same PR to say so.

The rest of the workflow is the minimum that makes a complaint recoverable rather than logged:
severity, an assigned owner, a status, and what was done. A complaint with no owner is the thing
`docs/customer-experience.md` warns is "worse than no system".

### 9 · An allergy is not a preference, and it goes to the kitchen

`customer_preference.is_critical` exists for one case: an allergy. modules.md requires that allergy
preferences surface to the kitchen, and the kitchen is M08's KDS.

The mechanism is deliberately dumb and deliberately frozen:

- Attaching a customer to an order (`POST /staff/orders/{id}/customer`) **copies** their critical
  preferences onto the order as a note at that moment.
- The KOT carries the copy. It does not join to `customer_preference`.

Frozen, because the alternative is a live join, and a live join means deleting a preference
retroactively changes what the kitchen was told about a ticket it already cooked. The kitchen's
record of what it was warned about must be the warning it actually received. This is the same
reasoning as the frozen per-batch costs in M05 and the frozen published metrics in ADR 0011.

Non-critical preferences (spice level, seating, "usually orders Butter Chicken") are **not** copied
and **not** sent to the kitchen. They are for the waiter's screen, where
`docs/customer-experience.md` puts them: "7th visit · usually orders Butter Chicken · no onion/garlic
· last visit rated 5". A kitchen ticket carrying a regular's seating preference is noise, and noise
on a ticket is how a real allergy gets skimmed past.

### 10 · Rate limiting exists in this module or the guest surface ships undefended

There is no rate limiter in this codebase today — nothing in `app/core/`, nothing in the middleware
stack. Every route so far has been behind a password.

M10 adds the smallest honest one: a fixed-window counter in process memory, keyed by client IP and
route class, with two tiers — reads generous, writes tight, because `docs/security.md` calls out
rating manipulation specifically. It answers 429 with the standard error envelope and
`details.retry_after_seconds`, which is exactly the shape `auth.too_many_attempts` already uses.

**It is declared on the route, the way a permission is.** `require_permission` both declares and
enforces, "and the declaration matters as much as the enforcement: it is what lets a test walk the
application's own routing table and prove that no route was registered without a permission". The
guest limiter carries the same marker for the same reason, and suite 5 walks for it. A guest route
added in a hurry six months from now cannot be registered without one.

The limiter is a floor, not the defence. What actually holds is structural: a table slug is 128 bits
and is not guessed, a bill token is hashed at rest and dies with its order, and one-feedback-per-
order is a unique index rather than a counter.

**What it is not, said plainly so nobody discovers it in an incident:** it is per-process. Two API
containers behind a load balancer give an attacker twice the budget, and a restart resets every
counter. That is acceptable at pilot scale and it is not acceptable at two instances, so it goes to
`docs/backlog.md` the day it is written, with the shape of the fix (a shared store) and the trigger
(the second instance).

---

## Not in scope

- **Guest ordering.** The guest reads the menu and their own bill; they do not place an order. QR
  ordering is a product decision with a service-model consequence, and nothing in `docs/modules.md`
  asks for it here.
- **Phone OTP.** ADR 0009 names it as the second guest auth realm, for order history across visits.
  The bill token covers this visit, which is what the CX doc says drives response rates. OTP needs an
  SMS provider — an external dependency with a cost and an account we do not have — and it is a
  module of its own. Flagged in the backlog with that reason.
- **The silent-dissatisfaction signals.** `docs/customer-experience.md` lists five (no repeat order,
  long gap before the second round, a 3/5 with no comment, a regular who stops). Every one is a
  *query over data this module creates*, and every one belongs to M13, the analytics module. Writing
  them here would put analytics in a CRUD module and freeze the definitions before there is data to
  check them against.
- **Attachments on a complaint.** `attachment` is M11's table and needs object storage. A complaint
  photo is exactly what it is for; it lands when the bucket does.
- **Occasion reminders.** `birthday` and `anniversary` are captured here. The reminder the week
  before is a notification, and notifications are M14.
- **Marketing sends.** The consent purpose exists; nothing reads it. Deliberate — the consent must
  predate the send, which is the entire lesson of §B2.

---

## Deliverables

### Migrations

- `0036_m10_customers.py` — `customer`, `customer_preference`, `customer_consent`, `feedback`,
  `feedback_line`, `complaint`; `feedback.would_return`; `customer.erased_at`;
  `restaurant_table.guest_slug`; `order.guest_token_hash` + `guest_token_expires_at`; and the
  **`order.customer_id` → `customer.id` foreign key** M07 left for this module.
- `0037_m10_permissions.py` — **the four codes `seed/organization.yaml` already designs, and not
  one more**: `customer.view`, `customer.manage`, `feedback.view`, `complaint.manage`. The shipped
  catalogue must be a subset of the P1 design (`test_the_shipped_catalogue_is_a_subset_of_the_p1_
  design`), so inventing a fifth would be changing the design in a migration. Grants follow the file
  exactly: **owner and manager** get all four; **a waiter gets `customer.view` and `feedback.view`**
  and nothing else; the kitchen roles and the store manager get none.

  The waiter's grant is the design being right rather than generous — `docs/customer-experience.md`
  puts the regular's card on the waiter's screen ("7th visit · usually orders Butter Chicken · no
  onion/garlic"), and a waiter who cannot see a customer cannot greet one.

  **What this leaves open, recorded rather than decided here:** erasure is irreversible and sits
  under `customer.manage` beside editing a name, because the design has no finer code and a
  migration is the wrong place to invent one. Whether an administrator or a manager should be able
  to destroy a customer's details is a question for the owner, and it goes to `docs/backlog.md`
  alongside the `admin` stock-permissions row, which is the same kind of question.
- `0038_m10_issues.py` — an issue number for every code this module raises.

### Backend

`app/models/customers.py` · `app/repositories/customers.py`, `feedback.py`, `complaints.py` ·
`app/services/customers.py`, `feedback.py`, `complaints.py`, `guest_session.py` ·
`app/schemas/customers.py` (staff) and **`app/schemas/guest.py`** (guest, and the only module guest
routes may answer from) · `app/api/v1/staff/customers.py`, `complaints.py` ·
`app/api/v1/guest/{session,menu,order,feedback,consent}.py` · `app/core/rate_limit.py` ·
`app/core/guest_token.py` · `app/api/guest_deps.py` — the second dependency chain, importing
nothing from `app/api/deps.py` · `app/core/consent.py` (the current notice version) ·
`app/core/phone.py` (one place that decides whether two numbers are the same person).

**Docs in the same PR** (CLAUDE.md): `docs/schema.md` §9 — the new `customer_consent` table, the
`would_return` and `erased_at` columns, and the removal of `customer_returned` with the reason ·
`docs/consent-notices.md` — new, the exact words of every notice version · `docs/ui/brand.md` §7 —
revised from the competitor research the backlog asked for · `docs/backlog.md` ·
`docs/plan/m10-build-log.md` · `docs/manual-tests/M10-customers.md` · **`docs/ui/conventions.md`** —
which has a "Rules per surface" section with three surfaces in it, and this module ships the fourth.
A guest surface's rules are not a waiter's: the device is not ours, the network is not ours, the
person has never seen the product before and will use it once. It gets its own paragraph, in the
same place as the others, rather than being left to be inferred.

### Endpoints

**Staff**

```
GET    /staff/customers                        list, search by phone or name
POST   /staff/customers                        create
GET    /staff/customers/{id}                   profile
PATCH  /staff/customers/{id}
GET    /staff/customers/{id}/history           visits, orders, feedback, complaints
POST   /staff/customers/{id}/preferences       + DELETE /{preference_id}
POST   /staff/customers/{id}/consent           grant or withdraw, one purpose per call
GET    /staff/customers/{id}/export            DPDP access right
POST   /staff/customers/{id}/erase             DPDP erasure — irreversible, `customer.manage`
POST   /staff/orders/{id}/customer             attach; copies critical preferences to the ticket
GET    /staff/feedback                         by business day, waiter, rating
GET    /staff/complaints                       + POST, PATCH status, POST resolve
POST   /staff/orders/{id}/guest-qr             `order.modify` - mints the bill's QR; a reprint mints a new one
POST   /staff/tables/{id}/rotate-qr            `restaurant.configure` - kills every photograph of the old sticker
```

**Guest** — all rate-limited, all answering from `app/schemas/guest.py`

```
POST   /guest/session                          { table_slug } or { order_token } → a guest token
GET    /guest/menu                             the M03 tree, with M03's ETag (see below)
GET    /guest/order                            the bill for the order the token names
POST   /guest/feedback                         three questions; idempotent per order
POST   /guest/consent                          the guest's own consent, and their own withdrawal
```

**What the guest menu shares with the staff one, and what it does not.** ADR 0009's duplication
rule is about *serialisation* — its own words are "some serialisation logic is duplicated between
staff and guest schemas" — and that is where the line sits. The **loader** is shared: one query
plan that reads categories, items, variants and modifier groups, returning model objects. The
**filter and the schemas** are not: `guest_tree` and `app/schemas/guest.py` decide what a diner may
see, and nothing a guest route touches can produce a staff schema. Duplicating the loader as well
would buy nothing and cost a second N+1 to get wrong.

`MenuService.load_tree` takes an `Actor` today, which a guest realm cannot construct, so it gains a
sibling `load_guest_tree(restaurant_id)`. The staff method keeps its actor and its
`include_inactive`; the guest path has neither, because a diner never sees a deactivated dish and
there is no flag for somebody to get wrong.

The sibling resolves the restaurant's organization itself, in one query, to build the scope the
shared loader needs. **That is not the guest token growing an `org` claim** — the token still
carries none, and nothing a guest sends influences the lookup. It is the server knowing something
about its own restaurant, which it always has.

**`GET /guest/menu` carries an `ETag` and honours `If-None-Match`**, which M03 already built for
the staff tree: `MenuTreeResponse.version` is "the `ETag` a conditional GET compares against".
`docs/security.md` asks for guest menu responses to be "cached and cheap", and this is what makes
them so — the menu is the most-requested thing on the guest surface and it changes a few times a
week. A 304 also costs the rate limiter nothing a diner would notice, which matters on the one
endpoint a whole restaurant hits at once.

### Frontend

**Staff** — customer list and profile (preferences, consent state, history, complaints), the
feedback day view, the complaint board.

**Guest** — a second Rollup entry point. The `guest:` line in `frontend/vite.config.ts` has been
commented out since M00 waiting for this module; uncommenting it is the whole build change.
`src/guest/` imports from `src/shared/` only, enforced by an eslint rule
(`no-restricted-imports` on `@staff/*` within `src/guest/`) so that the rule in the README stops
being a promise.

Three screens: the menu, the bill, and the three questions. Nothing else. It loads on a hostile
network on somebody's phone, and every kilobyte is a guest who did not wait.

The menu carries **one** control - a veg-only filter - and no others (§7.1 of `docs/ui/brand.md`,
from the competitor research): a vegetarian scrolling a long menu is not reading labels, they are
looking for what they can eat, and a second filter is where a three-tap surface becomes an app.

---

## Threat question — *what would an insider do with this?*

The answer this module is most exposed to is **rating manipulation by the people rated**. M17 pays
attention to feedback; a waiter who can submit feedback on their own tables can write their own
review. Three things stand against it, and they are the reason the bill token is per-order:

- Feedback requires an order token, which is minted when the bill is requested and dies after
  settlement. There is no staff endpoint that mints one.
- One feedback per order, enforced by an index. A waiter cannot submit fifty.
- `source` is recorded, and a `staff`-sourced rating is visibly different from a `qr` one in every
  view. A manager filling the form for a customer is a legitimate act; hiding that it happened is
  not.

The third thing worth saying out loud is what this module **cannot** promise: **the phone number a
guest types is unverified.** An anonymous surface has no way to know whose number it was given, so a
`qr`-sourced `order_contact` consent is a record that somebody at that table typed that number and
was shown that notice - no more. It is stored with its source, so nothing downstream can mistake it
for a verified one, and the notice says so in the words the guest reads. Verification is phone OTP,
which ADR 0009 names as the second guest realm and which needs an SMS provider this project does not
have. Until then, the guest surface may **withdraw** a consent and may never grant one on somebody
else's behalf, which is decision 4's asymmetry.

The second exposure is **an employee walking out with the customer list** — it is a competitor's
most valuable asset, and the P1 design deliberately puts `customer.view` in a waiter's hands so they
can greet a regular. So the control is not the permission; it is the shape of the surface:

- the DPDP export is **per customer**, never bulk. There is no endpoint that returns everybody's
  details, in any role, including the owner's.
- the list screen is thinner than the profile — phone, name, visit count, last visit. Not
  birthdays, not preferences, not lifetime value. A screen showing every customer's birthday is a
  screen somebody photographs.
- every export and every erasure writes an `audit_log` row naming who did it.

None of that stops a determined person with a phone camera and an evening. It makes the fast version
— one request, the whole book — not exist.

---

## Acceptance criteria

1. No guest token satisfies any staff route (the existing suite, now against a real realm).
2. No staff token reaches a guest route expecting a guest scope — the symmetry matters, because a
   staff session must not be able to browse another table's bill either.
3. Every guest route answers from `app/schemas/guest.py`; every model reachable from one of those
   is defined there too; and no field in that graph is named like an internal one. All three
   enforced by tests over the routing table, not by review.
4. `src/guest/` imports no staff code, enforced by eslint.
5. Erasure leaves revenue totals unchanged, and leaves the consent history intact.
6. A consent is one row per purpose; withdrawing marketing does not withdraw order contact.
7. The consent control is not pre-ticked, enforced by a frontend source test.
8. Feedback is anonymous unless the guest gives a phone, and submitting twice returns the first row.
9. A guest lookup by phone answers identically whether or not the number exists.
10. A critical preference reaches the kitchen ticket; a non-critical one does not.
11. `customer_returned` is derived from the order ledger and no endpoint writes it.
12. Every guest route declares a rate limit, and returns 429 under a burst with a retry hint.
13. **A branch sees only its own customers**, and a manager assigned to a second branch sees that
    one after switching — never before. Asserted with two restaurants in **one** organization,
    which no existing suite covers: the generic suites use two organizations, and this rule lives
    inside one.
14. **Every tenant-owned table carries `UNIQUE (id, restaurant_id)` and every foreign key between
    two tenant-owned tables is composite.** A new structural test enumerates the mapped metadata
    and fails on either. Today the pattern is followed by convention and checked only where somebody
    remembered; the owner asked for a strict check, and this is what makes a missing one a red
    build rather than a review comment. **It closes the `menu_item_variant.menu_item_id` hole
    `docs/backlog.md` has been carrying since M08** — a variant that could, as far as the database
    is concerned, point at another restaurant's dish.
15. **No phone number reaches a log line.** The Definition of Done says "no PII in logs" and this is
    the first module with real PII in it. A test asserts that the log records this module emits
    carry ids, purposes and counts, and never a number, a name or an email.
16. Nothing in the product describes the DPDP obligations as currently in force.

**One Definition-of-Done line needs reading carefully here.** "Permission declared on every route;
default-deny verified" is written for the staff surface, and a guest route correctly declares none:
suite 5 asserts that a guest route declaring a permission is a *failure*, because it would mean the
staff dependency chain had been wired into the guest one. The guest analogue of the declared
permission is the declared rate limit, and it is checked the same way, over the same routing table.
Both halves of that sentence are true at once, and the tests say so rather than a reader having to
hold it in their head.

---

## Chunks

| | What |
|---|---|
| **A** | Spec, migrations, models, repositories |
| **B** | Customer service + staff CRUD, history, preferences, the order attach and the frozen allergy note |
| **C** | Consent, export, erasure — and their tests, which are the compliance evidence |
| **D** | The guest realm: token type, dependency chain, `schemas/guest.py`, rate limiter, the five guest routes, and suite 5 |
| **E** | Feedback and complaints |
| **F** | Staff screens |
| **G** | The guest bundle — vite entry, eslint boundary, three screens |
| **H** | Seed, adversarial review, manual script, build log |

**What the seed plants, and what it deliberately does not.** `docs/seed-data.md` has fourteen
planted signals and three are this module's — ratings dropping to ~3.3 in the 20:30-22:00 Fri/Sat
window (5), six regulars with five or more visits who stop after week 14 (12), and eight Biryani
complaints in one week, all at dinner peak (14). **The volume that makes those readable is M15's**,
the same line M09's seeder drew: a hundred and twenty days of history is a generator, not a seeder.
So M10 plants a handful shaped like those signals — a few regulars with visit counts and
preferences, a spread of ratings, one open complaint and one resolved — enough that every screen
opens on something real, and shaped so M15 scales a pattern rather than inventing one.

And three deliberate imperfections, per `docs/seed-data.md` rule 3: **one order with no feedback at
all** (most orders have none, which is the honest response rate), **one customer with a withdrawn
marketing consent**, and **one complaint that was resolved and whose customer never came back** —
so the derived `customer_returned` has something to be false about.
