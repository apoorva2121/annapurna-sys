# Manual pass findings — 2026-09-19 onward

Issues the owner found by using the product, raised one at a time and triaged here **before**
anything is changed. Separate from `docs/backlog.md`, which is scope not yet promoted, and from
`docs/owner-actions.md`, which is decisions waiting on the owner.

Each row is triaged into one of three buckets:

- **A — defect.** No judgement needed. Regression test first, then the fix.
- **B — decision.** I would be guessing at intent. Goes to `docs/owner-actions.md` as a question.
- **C — working as designed.** The behaviour is recorded somewhere; I show where, and the owner
  says whether the design is wrong. That is a different conversation from a bug.

**Fixes are batched deliberately.** `make check` takes roughly 90 minutes, so fixing one row at a
time costs a full gate run each. Related rows are fixed and gated together.

---

## Read this before triaging anything else found on staging

**Staging is 61 commits behind this laptop.** It runs `eb8bd6e`, built 2026-09-17T23:36:55Z
(`GET /api/v1/version`); `HEAD` is 61 commits ahead and carries M11–M18. So:

- a screen the owner is looking at on staging **may already be different locally**, and
- a defect found there may already be fixed, or — as with F1 — may already be **worse**.

Every row below records which build it was seen on. Check against local `HEAD` before writing a
test, or the test may be written against a screen that no longer exists.

---

## The list

| # | Seen on | What | Bucket | State |
|---|---|---|---|---|
| F1 | staging `eb8bd6e`, phone | The staff header reads as a paragraph of text, not a set of links | **A** | ✅ **fixed** 2026-09-19 |
| F2 | local, from F1 | Links are `text-info` on the home screen and unstyled in the header, while `tokens.css` documents `--brand` as the link colour | **A** (small) | ✅ **fixed** 2026-09-19 |
| F3 | local `HEAD` | 8 screens are linked in both the header and the home page — the same option twice on one screen | **A** | ✅ **fixed** 2026-09-19 |
| F5 | local `HEAD` | A **manager** must no longer be assignable as a table's waiter | **A** | ✅ **fixed** 2026-09-19 |
| F6 | local `HEAD` | The whole "Preparation preference" group comes off **non-veg** dishes | **A** | ✅ **fixed** 2026-09-19 |
| F7 | local `HEAD` | "Ask for bill" is shown to the owner, where it is not an owner's action | **A** | ✅ **fixed** 2026-09-19 |
| F8 | local `HEAD` | A **manager** cannot reset anyone's password — only the owner can | **A** | ✅ **fixed** 2026-09-19 |
| F9 | local `HEAD` | No "forgot password" anywhere; owner recovery to go by SMS/WhatsApp code | **B** | channel chosen, blocked on research |
| F10 | local `HEAD` | A bill cannot be printed; only the credit note that corrects it can | **A** | answered, needs a research step |
| F11 | local `HEAD` | Dishes, categories, variants **and modifier groups** show their internal code beside the name | **A** | ✅ **fixed** 2026-09-19 |
| F12 | new, owner's idea | A reference page listing every name and its code, since codes become invisible | **A** | ✅ **built** 2026-09-19 |
| F24 | local `HEAD`, found by a test | A dish's cost breakdown names each ingredient by code, because the API sends no name | **A** | not started |
| F13 | local `HEAD` | Nobody can look at a populated report: generated data is excluded from reports by design | **B** | question open |
| F14 | local `HEAD` | Workload compares 120 days of orders against 2 days of attendance | **A** | ✅ **fixed** 2026-09-20 |
| F15 | local `HEAD` | Alert cards are unreadable in the Dark theme — contrast 1.04 against a minimum of 4.5 | **A** | ✅ **fixed** 2026-09-19 |
| F16 | local `HEAD` | "My performance" tells the owner to ask their manager; should it exist for them at all? | **B** | question open |
| F17 | local `HEAD` | M17's incentive scheme is specified in the seed and **never loaded** — performance is empty for everyone | **A** | ✅ **fixed** 2026-09-20 |
| F18 | local `HEAD` | **Every attachment link 401s.** A browser cannot send the Bearer token an `<a href>` needs | **A** | ✅ **fixed** 2026-09-19 |
| F19 | local `HEAD` | Upload never confirms success, so a working upload looks like a failed one | **A** | ✅ **fixed** 2026-09-19 |
| F20 | local `HEAD` | M11 has no seeder — no sample conversations or messages | **A** | ✅ **fixed** 2026-09-20 |
| F21 | local `HEAD` | **No screen can create a shift.** The endpoint and the hook exist; nothing calls them | **A** | ✅ **fixed** 2026-09-19 |
| F22 | local `HEAD` | With no shifts, the roster's button is permanently disabled and says nothing | **A** | ✅ **fixed** 2026-09-19 |
| F23 | local `HEAD`, verified in a browser | `Button` is the one `shared/ui` component without `forwardRef`, so Radix focus management fails | **A** | ✅ **fixed** 2026-09-19 |

---

## F1 · The staff header reads as prose

**Seen on** staging `eb8bd6e` on a phone (`images/first_page.jpeg`). **Owner's words:** *"all the
options look like its a paragraph and not the different options."*

### What is actually wrong — three things, not one

1. **The nav links have no styling at all.** In `frontend/src/staff/components/AppShell.tsx` every
   link is a bare `<Link to="/alerts">{strings.nav.notifications}</Link>` — no class, no colour, no
   underline. They inherit body text, so a row of them wraps into a paragraph. The links on the
   home screen look correct only because `HomeScreen.tsx:88` gives them `className="text-info
   underline"`.
2. **No touch target, and the rule was known.** The Sign out button in the same header carries
   `min-h-target` (44px, `--target-min`). Not one nav link does. On a phone they are ~20px tall and
   16px apart, under the design system's own minimum for a thumb.
3. **There are 25 of them and the count grows every module.** The screenshot shows 15 because
   staging predates M11–M18. On `HEAD` an owner holding every permission gets 25 links in the same
   flat wrapping row. **This is the structural problem; 1 and 2 are the visible symptoms.**

### Why it happened, which matters for the fix

The nav is already split into `ServiceLinks`, `InsightLinks` and `EveryonesLinks` — but the
comments say each split happened because **eslint's complexity limit forced it**: *"the third time
the budget has forced this grouping."* The grouping exists in the code and was never expressed on
the screen. It does not need inventing, only showing.

The same comments carry an argument the fix must not trample: *"a chef standing at the pass is
already inside the app, and going back to a landing page to reach the next screen is not how
anybody works a shift."* That is an argument against burying everything behind a hamburger.

### Decided with the owner, 2026-09-19

**Shift screens stay visible; everything else moves into a drawer, below the `md` breakpoint only.**

Two calls made rather than asked, and recorded here so they can be overruled:

- **What stays visible is permission-driven, not a fixed list.** `ServiceLinks` is already
  documented in the code as "the screens of the shift" and each of Tables / Bills / Cash is
  permission-gated. A waiter sees Tables and Bills, a cashier sees Cash, a cleaner sees neither and
  gets only the drawer button. Hard-coding a list would break ADR 0007 — navigation comes from
  permissions, never from a role name.
- **Drawer below `md` only.** At laptop width there is room for a real horizontal nav, and hiding
  Reports behind a hamburger on a 1400px screen is worse than the problem being solved. The owner
  surface is a laptop (`docs/ui/conventions.md`).

### How to build it

- **Make the nav data, not JSX.** A `navigation.ts` carrying groups — Service · Menu & stock ·
  Purchasing · Insight · People · Set up · Yours — each with a heading string and items of
  `{ to, label, permission? }`. One source of truth, rendered twice: a grouped horizontal bar at
  `md`+ and the drawer below it. This also dissolves the eslint-complexity problem that produced
  the accidental groupings in the first place.
- **Use the existing `shared/ui/sheet.tsx`** (shadcn/Radix, already in the bundle — the design
  gallery uses it). Do not hand-roll a drawer.
- **Tokens only.** `--brand` is documented in `tokens.css:68` as the link colour ("fills: active
  nav, links, selected state"). No hex, no inline style.
- **`min-h-target` on every link**, in both the bar and the drawer.
- **The drawer trigger is not icon-only.** The design system permits an icon-only button only for
  an action done fifty times a shift; this is not one. Icon plus a visible word.
- **The active link must not re-flow the layout** (design-system rule 10): mark it with colour and
  `aria-current="page"`, never a bolder weight or a thicker border.
- **Strings go in `staff/strings.ts`** under `nav` — group headings and the trigger label. Note
  `strings.nav.menu` is already the *food* menu, so the trigger needs its own word.

### The trap in testing this

`AppShell.test.tsx` collects links with `getAllByRole('link')`. **jsdom loads no stylesheet**, so a
`hidden md:flex` desktop nav is still fully visible to the test — the existing permission tests
will keep passing even if the mobile drawer is completely broken. Any test for the drawer has to
**open it first** and assert against its contents, or it proves nothing.

---

## F2 · Two different colours for a link

**Found while diagnosing F1**, not reported by the owner.

`tokens.css:68` documents `--brand` as the colour for links. `HomeScreen.tsx:88` uses
`text-info underline`. The header uses nothing at all. So the product has up to three link
appearances depending on the screen.

Small, but it belongs with F1 rather than after it: fixing the header to `brand` while the home
screen stays `info` would make the inconsistency more visible, not less. **Decide one and apply it
in the same change.**

---

## F3 · The same screen linked twice on one page

**Measured on local `HEAD`** by reading `AppShell.tsx` and `HomeScreen.tsx` — *not* from the
staging screenshot, so it is not an artefact of the stale build. Noticed by the owner on
staging (`images/first_page.jpeg`), where Staff / Restaurant settings / Menu / Options and
add-ons / Ingredients and recipes appear in the header and again below it.

**Owner's words:** *"the options that are present at the top they should not be repeated below …
any option should not be duplicate on a screen, that is redundant … put some important ones on top
and others below, that will save space as well."*

### The measurement

Counted from `AppShell.tsx` and `HomeScreen.tsx` on `HEAD`:

**8 screens are linked in both places** — `/staff`, `/settings`, `/menu`, `/menu/options`,
`/stock`, `/costs`, `/reports`, `/profile`. Five of those eight are the ones visible in the
owner's screenshot.

That is the whole of this finding. The *coverage* gaps it turned up — screens reachable from only
one of the two lists — are **F4**, kept separate because the owner did not report them and because
conflating them would make one fix answerable to two problems.

### Why it survived

`reachability.test.ts` (backlog-issues B10) fails the build when a fixed route has **no** link
anywhere in the app. It is satisfied by a link in either place, so it has never had an opinion
about a screen linked in *both* — and no test anywhere asserts that a screen is linked once. The
duplication is invisible to the suite.

### The fix, as the owner described it

**One union of 35 screens, partitioned — never overlapping.** Important ones in the header, the
rest on the home page, and **no screen in both**.

This folds into F1 rather than following it: F1 already turns the nav into data
(`navigation.ts`, groups of `{ to, label, permission? }`). Once the nav is data, the home page
renders **the complement of what the header shows**, computed from the same source rather than
maintained as a second hand-written list. Two lists that must not overlap will overlap again
within two modules if they are kept by hand — the M03/M04/M08/M09 comments in both files are four
separate instances of exactly that drift.

### What must be decided before building

**Which screens are "important" enough for the header** is a product judgement and belongs to the
owner, not to me. The honest default, from the code's own reasoning, is *the screens somebody opens
during a shift*: Tables, Bills, Cash, **Kitchen display**, Alerts. Everything else on the home page,
grouped. To be confirmed before the split is written.

### Tests this needs

- **A test that no route is linked twice** across the shell and the home page — the gap that let
  this happen. It has to read both sources, the way `reachability.test.ts` does.
- **A test that the two lists are complementary**: every fixed route appears in exactly one of
  them. That is strictly stronger than today's "at least one link anywhere", and it replaces the
  hand-maintenance that keeps failing.

---

## F5 · Who may be a table's waiter

**Owner's words:** *"tables should be assigned to only waiters and not manager or owner, or admin."*

**CORRECTED 2026-09-19 while implementing it.** An earlier version of this finding said *"owner
and admin already cannot be assigned"*, because `seed/organization.yaml` lists `order.create`
under `manager` and `waiter` and not under `owner`. **That was wrong.** The `owner` role is
`permissions: ["*"]`, and the identity seeder **expands the wildcard into every permission in the
catalogue**. Checked against the running database:

| role | holds `order.create` | permissions held |
|---|---|---|
| owner | **yes** | 55 |
| manager | yes | 47 |
| waiter | yes | 13 |
| admin | no | 22 |

So the **owner was being offered as a waiter on every table** — the exact thing reported — and only
`admin` was already excluded. Reading a role's grants out of the YAML without accounting for `["*"]`
is how this was missed; the database is the source of truth for what a role actually holds.

**So the live question is the manager only**, and the current behaviour is deliberate:
`order_takers`' docstring says it "includes a manager covering the floor and excludes the
accountant who only reads orders."

**And a new permission could not have fixed it.** That was the obvious implementation and it is
structurally impossible: an owner holds `["*"]`, so they would hold any new permission
automatically, the moment it was added to the catalogue. **Nothing can be hidden from an owner by
adding a permission.** ADR 0007 rules out checking the role name instead.

So the two ideas the product treats as one are separated by a **column on the employee**:

- **may take an order** — `order.create`, which a manager keeps;
- **serves tables** — `employee.takes_tables`, a fact about the person's job rather than a grant of
  authority, and set per person by the owner.

That is also the truer model. A manager who genuinely covers Friday service gets the switch; one
who never waits a table does not — without granting it to every manager everywhere.

**Why it probably matters.** ADR 0011 scores a waiter on the orders they served. A manager who
covers the floor for an hour enters the waiter statistics, which distorts everyone else's figures
and, under the fairness guardrails, could reach a payment.

---

## F6 · "Jain" is offered on non-vegetarian dishes

**Owner's words:** *"non veg dishes should not have a option of no garlic or jain food, this option
is just of veg food."*

**Confirmed in the seed.** `seed/operations.yaml:130-131` attaches the `JAIN_PREF` group
("Preparation preference") to `MAIN_NONVEG` and `STARTER_NONVEG` as well as the veg categories. So
a chicken curry currently offers **"Jain (no onion/garlic)"**.

**The Jain half is a clear defect.** Jain dietary practice is vegetarian by definition — the option
cannot be satisfied on a non-veg dish under any preparation. It is worse than useless: a Jain
customer shown that option on chicken learns the restaurant does not know what the word means.
This is exactly the class of thing `docs/compliance-rules.md` §A1 treats seriously about the
veg/non-veg mark, though the mark itself is a separate rule.

**The no-onion / no-garlic half is not.** Those are legitimate requests on a non-veg dish — allergy,
taste, or digestion. Removing them from non-veg would take away something customers really ask for.
**Recommendation: split the group** — `JAIN_PREF` (Jain only, veg categories only) and a new
onion/garlic preference group attached to everything.

**A deeper problem, flagged and not scoped.** A Jain diet excludes *root vegetables* — potato,
onion, garlic, ginger, carrot, radish. So "Jain" is also wrong on any veg dish built on them: Aloo
Gobi cannot be made Jain by omitting anything. Attaching the option by *category* will always be
approximate; doing it properly means knowing, per dish, whether a Jain version exists. Worth a
decision before the menu is sold to a real restaurant, not before this fix.

---

## F7 · "Ask for bill" is shown to the owner

**Owner's words:** *"in owners table page ask for bill option should not be there, its for customers
odering page rather here."*

**Where it actually is.** Not on the tables grid — on the order detail screen reached from it
(`OrderScreen.tsx:720`), so it appears for anyone who can open a table's order, the owner included.

**The owner is right that it is not an owner's action**, and wrong that it belongs to the guest app
today — which is the catch:

- the guest surface is **read-only** (M10, a recorded decision; guest ordering is Q2 on
  `docs/owner-actions.md` and unanswered), and its only order route is `GET /order`;
- so `OrderService.request_bill` is reachable **only** from the staff surface, and this button is
  the only thing in the product that ever sets `bill_requested_at`;
- that timestamp is what bill-to-settle time is measured from — its docstring: *"measured from when
  the customer first asked, not from the third time they had to."*

**Remove the button and the measurement dies silently.** Nothing would fail; the figure would
simply always be empty.

**It is also a genuine waiter action.** In a real restaurant the table asks the *waiter*, not an
app. The waiter tapping it is the normal path and would remain so even after guest self-service
exists.

**Recommendation: hide it from owner and admin, keep it for waiter and manager.** Revisit if Q2 is
answered in favour of guests asking from their phone.

---

## Answers given by the owner, 2026-09-19

Recorded here because each turns a **B** into an **A** and fixes the shape of the work.

**F5 — waiters only.** A manager may still take an order and must no longer be recordable as the
table's waiter. This is the option that costs a real change, and the owner chose it knowing that:
`order.create` stays with the manager, and a second idea is separated out — *may be credited as the
table's waiter*. ADR 0007 still holds, so it is a permission or an employee attribute, never a
check on the role name. `AccessRepository.order_takers` is the one place that decides, which is
what makes this tractable.

**F6 — remove all three from non-veg.** The owner's original instruction, restated after I
queried it. `JAIN_PREF` detaches from `MAIN_NONVEG` and `STARTER_NONVEG` entirely; Jain, No onion
and No garlic remain on veg dishes only.

I recommended splitting the group so "No garlic" survived on meat dishes — allergy or taste — and
**the owner overruled it**, which is their call: they know what customers in this market actually
ask for. Recorded because a later reader will otherwise see the split idea in F6's body and think
it was missed rather than declined.

It is also the cheaper fix: one line in `seed/operations.yaml` plus a migration, with no new group,
no new modifiers and no new strings. The deeper root-vegetable problem (Aloo Gobi can never be
Jain) was offered and not taken — it stays flagged in F6 and unscoped.

**F7 — hide, do not remove.** The owner's instruction was that it should not be on their screen,
and the catch was explained: the guest app is read-only, so this button is the only thing that sets
`bill_requested_at`, and removing it would silently kill bill-to-settle timing. Hiding it from
owner and admin satisfies the instruction and keeps the measurement. Revisit if Q2 (guest ordering)
is answered.

### What these three share, and why they are one change

F5 and F7 are both **"this person should not be offered this"**, and the product already has one
honest way to express that: a permission, checked in one place, never a role name (ADR 0007). F6 is
a seed-data change with a migration for existing restaurants. So the sensible batching is:

1. **F5 + F7 together** — both touch who sees and who may be recorded, both need a permission
   added to `app/core/enums.py`, the seed, a migration, and the frontend `can()` checks.
2. **F6 on its own** — `seed/operations.yaml:130-131` drops `MAIN_NONVEG` and `STARTER_NONVEG`
   from the `JAIN_PREF` attachment, plus a migration detaching it for restaurants already seeded.
   No new group.
3. **F1–F3 together** — all three are the navigation, and all three rewrite the same two files.

Three batches, three gate runs, rather than seven.

---

## F8 · Only the owner can reset a password

**Owner's words:** *"all the others can ask it from manager or owner."*

**Half of that is already true, and the manager half is not.** Reading `seed/organization.yaml`:
`owner` holds `permissions: ["*"]` and therefore `employee.password.reset`. **No other role holds
it** — not `admin` (which has `employee.view` and `employee.manage` but not the reset),
not `manager`, nobody. So today a waiter who forgets their password must find the owner.

**This is the cheap half of the request and probably the valuable half.** Staff forget passwords
constantly; owners rarely. Granting `employee.password.reset` to the manager role is a seed change
plus a migration for restaurants already created.

**What must not be lost when it is granted.** `POST /employees/{id}/password` sets
`password_reset_required` (P1-6): the reset is legitimate, but it ends the standing ability of
whoever performed it to sign in as that person afterwards. A manager who resets a waiter's password
must not be able to use it — the existing flag already handles this and the grant does not weaken
it. Worth an explicit test rather than an assumption.

**CORRECTED 2026-09-19 while implementing it.** An earlier version of this finding warned that
*"the reset endpoint has no rank check today"* and that granting the permission would open a path
from manager to owner. **That was wrong, and it was written without reading the service.**

`EmployeeService.reset_password` already calls `may_reset_password`, which is documented as
deliberately stricter than every other guard: *"Appointing a peer is not escalation — a manager may
appoint another manager. **Acting as** a peer is, because a password is the ability to be that
person."* It requires **strictly** more senior, with one exception for two owners so co-owners can
help each other and an owner is not locked out with no recovery path.

So a manager still cannot reset an owner's or an admin's password, and this finding is a one-line
grant after all. `password_reset_required` (P1-6) already ends the standing ability of whoever
performed a reset to sign in as that person.

---

## F9 · There is no "forgot password", and the owner's reset has no channel

**Owner's words:** *"in signin page owner, manager should be able to change there passowrd … but if
owners want to change, they should have email sent to their email and there they can change
password."*

**CORRECTED 2026-09-19 after looking at the actual page.** An earlier version of this finding
said *"the sign-in page offers no recovery at all."* **That was wrong**, and it was written from
the code without opening the screen.

The login page **does** carry a *"Forgot password?"* control. It is a disclosure that expands to:
*"Ask your manager or the owner. They set a new one from Staff, and you choose your own the next
time you sign in."* So there is a deliberate, documented **manual** recovery path — not an absence.

What is genuinely missing is **self-service** recovery: `POST /auth/password` changes your own
password but requires you to be signed in and to supply the current one.

**And the message on that page is currently false** — see F8. It tells the user to ask *"your
manager or the owner"*, but only the `owner` role holds `employee.password.reset`. A manager asked
for a reset cannot perform one. **F8 and this sentence must be fixed together**: either the manager
gets the permission and the sentence becomes true, or the sentence must stop naming the manager.

**There is no email capability in this product.** No SMTP, no provider SDK, no templates, no
outbound mail of any kind — checked across `backend/app`. This is a new capability, not a screen.

### What building it actually requires

- an email (or other channel) provider and credentials in the secret store;
- a reset-token table: single-use, short expiry, hashed at rest like any other credential;
- a public endpoint that **must not reveal whether an address is registered** — the same
  no-enumeration rule the guest QR refusal follows (`docs/security.md`);
- rate limiting, or the endpoint is a way to send somebody hundreds of emails;
- a verified sending domain.

### Two blockers that are not code

1. **No custom domain.** The product is on `restaurant-os-api-…run.app` with no SPF, DKIM or DMARC.
   Password-reset mail from it will be spam-filtered or rejected. Same root cause as the QR codes
   not being printable (see `docs/owner-actions.md` A11). **A reset link the owner never receives
   is a lockout, not a recovery.**
2. **Email may be the wrong channel for this market.** A restaurant owner in Pune reads WhatsApp
   hourly and email rarely. The seed already stores a phone number for every person
   (`organization.yaml:261-269`). An SMS or WhatsApp OTP would very likely reach them; an emailed
   link might not. `docs/product/vision.md` and the market research both assume a phone-first owner.
   **This is the decision to make before any of it is built** — the channel changes the provider,
   the cost, the token format and the compliance surface (DPDP consent for a phone number is not
   the same as for an email).

### Scoping recommendation

**Split it.** F8 (let managers reset) is small, is most of the day-to-day value, and unblocks every
member of staff. F9 (owner self-service recovery) is a module of its own and should not be started
until the channel is chosen and a domain exists. Until then, the honest answer to "the owner forgot
their password" is that a second owner account, or direct database access, is the recovery path —
and that should be written down rather than discovered at 11pm on a Saturday.

---

## F9 — channel chosen, 2026-09-19: **SMS or WhatsApp code**

The owner chose a code to the phone over the emailed link they first described, once the two
blockers were laid out. It is the better answer for this market: the seed already carries a phone
number for every person, and it needs no sending domain, so it is not blocked behind the same
missing-domain problem as the QR codes.

**This does not unblock the work. It moves the blocker.**

### What must be researched before a line is written — NOT filled in from memory

`CLAUDE.md`'s first compliance rule is *never fill an Indian rate, threshold or commencement date
from memory*, and the sub-rule is *never conflate in force with notified-but-not-in-force with
unsettled with unverified*. Sending transactional SMS to Indian numbers is squarely inside that
rule. What I believe and have **not** verified, flagged as **unverified** rather than asserted:

- that transactional SMS to Indian subscribers requires **DLT registration** (sender ID and message
  templates pre-registered through a TRAI-mandated platform) before a single message will be
  delivered;
- that WhatsApp Business messaging requires **template approval** and a verified business, and that
  an authentication template is its own category with its own pricing;
- that both carry lead times measured in **days to weeks**, not hours.

**If any of those is true, it is the real schedule risk in this feature** — the code is a token
table and a screen; the registration is the long pole. **Every one of these must be checked against
the actual instrument and cited in `docs/compliance-rules.md` before this is planned**, exactly as
that file's first rule demands. Research that returned stale-but-confident law three times in one
session is the reason the rule exists.

### What follows regardless of the research

- **An SMS provider is an owner action** — an account, a payment method, a sender ID. It belongs in
  `docs/owner-actions.md` once the research says which kind of account is needed.
- **A code, not a link.** A six-digit code typed into the app avoids the link-in-a-message problem
  entirely and is what every Indian consumer app already trains people to expect.
- **The security rules do not change with the channel**: no enumeration (the endpoint must answer
  identically whether or not the number is registered), single-use, short expiry, hashed at rest,
  and rate-limited per number *and* per IP — an unthrottled OTP endpoint is a way to spend the
  owner's money sending messages to a stranger.
- **DPDP consent for a phone number is not the same as for an email**, and
  `docs/compliance-rules.md` governs that too. Also to be checked, not recalled.

**Recommendation unchanged: do F8 first.** It is a seed change plus a rank check, it needs no
provider, no registration and no research, and it solves the case that actually happens weekly —
a waiter locked out mid-shift.

---

## Closed

**F4 — ten screens reachable only from the home page.** Raised by me on 2026-09-19 and **closed by
the owner the same day**: they could reach those screens and did not want the header changed to
carry them. Recorded rather than deleted so it is not re-raised as new in a month.

The measurement was correct and is worth keeping for whoever reads this next: on `HEAD` the
kitchen display, the waste screens, the stock operations and the customer screens are on the home
page and not in the header. **A deliberate split between "header screens" and "home page screens"
is a legitimate design** — it was only ever a question of whether a *shift* screen belongs on a
landing page. The owner has answered that it does not matter to them today.

It becomes live again only if someone working a shift complains they cannot find the kitchen
display from where they are standing.

---

## F10 · The bill cannot be printed, but the credit note against it can

**Owner's words:** *"bills from bills page should be printable."*

**Where it is.** `/bills` lists settled bills; a row opens `/bills/{orderId}` → `InvoiceScreen`.
That screen renders the invoice on screen and **prints only its credit notes** — `window.print()`
with a `print:hidden` stylesheet so the chosen note is alone on the page (decision D27,
`InvoiceScreen.tsx:446-464`). The invoice itself has no print path.

So the product can print **the document that corrects a bill and not the bill itself.**

### This is a recorded gap whose stated reason does not hold

`docs/compliance-rules.md:233` already carries it:

> *No rendered invoice document — M07 follow-up. Rule 46's particulars and the restaurant's
> identity are stored on `invoice` at settlement, but nothing lays them out for a customer: no
> print, no PDF, and no Rule 5(1)(f) heading on a composition bill of supply. Printing is out of
> scope for month 1 (CLAUDE.md).*

**CLAUDE.md's exclusion is "printer/hardware drivers", which browser printing is not** — and the
product already browser-prints credit notes. An over-broad reading of one exclusion turned a
rendering job into a deferred gap. Worth correcting in `compliance-rules.md` in the same change,
so the next reader is not deferred by it again.

### The data already exists

`invoice` stores `supplier_name`, `supplier_address`, `supplier_gstin`, `fssai_licence`,
`recipient_name`, `recipient_gstin`, `invoice_number`, `invoice_date`, the totals and the tax
split, frozen at settlement. **No new column, no migration, no API change** — it is a layout and a
print stylesheet.

### Decided with the owner, 2026-09-19: an 80mm thermal till roll

What a restaurant actually hands a customer. It prints from the browser to any thermal printer
with no driver, so it stays inside CLAUDE.md's exclusion. It needs its own narrow layout — an A4
stylesheet on a 80mm roll produces a bill nobody can read — and it must be tested on a real roll,
not only in a print preview.

### The research step this must not skip

**A composition restaurant issues a *bill of supply*, not a tax invoice**, and the document carries
a declaration whose wording is set by the instrument. `document_type` on `invoice` already records
which it is, and migration 0019 enforces that a composition restaurant puts no tax on the bill —
so the data is right and only the *rendered wording* is missing.

**That wording must be taken from the instrument and cited, never recalled.** `CLAUDE.md`'s first
compliance rule, and this is precisely the case it is about: a bill of supply carrying an invented
declaration, or a tax invoice missing a required particular, is a licence risk for a real
restaurant. The particulars list for Rule 46 and the declaration for a bill of supply both need
looking up before the layout is written, and adding to `docs/compliance-rules.md` with their
instrument and status.

Until that is done this finding is **not ready to build**, even though the owner has answered the
only product question in it.

---

## F11 · Everything on the menu is named twice — once for people, once for the database

**Owner's words:** *"in menu, i see that its written like Veg Starters the starter_veg … every dish
is mentioned twice, name is okay, but the other thing should not be in ui."*

**Extended by the owner on the same day:** *"Same with options and add-on page — i see
JAIN_PREF, ADDONS_GRAVY, BREAD_OPTS should go too."*

**Confirmed in five places**, all the same shape — the code in small monospace beside the name:

| Screen | Line | Reads as |
|---|---|---|
| Category list | `MenuScreen.tsx:156` | "Veg Starters `STARTER_VEG`" |
| Dish list | `MenuScreen.tsx:293` | "Garlic Naan `GARLIC_NAAN`" |
| Variant list | `MenuItemScreen.tsx:279` | "Full `FULL`" |
| Dish detail | `MenuItemScreen.tsx:66` | the join key, deliberately |
| **Modifier groups** | `ModifierGroupsScreen.tsx:110` | "Preparation preference `JAIN_PREF`" |

**What stays.** `ModifierGroupsScreen.tsx:124` is also monospace, and it is the price delta, not a
code — `font-mono tabular-nums` on a number is design-system rule 8 working correctly. Removing it
would misalign every price in the column.

### Decided with the owner, 2026-09-19: remove it everywhere, detail screen included

I recommended keeping it on the **detail** screen and was **overruled**, which is recorded here so
a later reader sees a decision rather than an oversight.

**The consequence, stated so it is not a surprise.** `MenuItemScreen.tsx:38` documents why it was
there: *"`code` is shown and never editable. It is how `library/dishes.yaml` and every recipe M04
[joins]."* It is the key tying a dish to its recipe in the 223-dish library. Removing it from the
UI means **the app can no longer show which library recipe a dish is attached to** — that
correlation moves to files and exports. It bears on `docs/owner-actions.md` A15, the chef's review
of `library/`, which matches dishes by code. If that review turns out to need the code on screen,
this is the finding to reopen.

### The sub-question the removal creates — open

**A category, a dish and a modifier group all still *require* a code when created.**
`MenuScreen.tsx:218-223` and `ModifierGroupsScreen.tsx:168-205` each carry a required code field
that uppercases what is typed. If codes are invisible
everywhere else, the product would be asking a manager to invent a value they will never see
again, for a reason nobody can explain to them. That is worse than showing it.

Three ways out, and this needs the owner before the change is written:

1. **Generate it from the name** — "Veg Starters" → `VEG_STARTERS`, with a uniqueness suffix when
   it collides. The manager never sees or types a code. Most consistent with the decision.
2. **Keep the field, on the create form only** — visible where it is set, invisible everywhere
   after. Contradicts "everywhere in the UI" slightly, but only at the one moment it has meaning.
3. **Generate it, and show it on an admin-only screen** — for whoever maintains the library link.

**Answered by the owner, 2026-09-19: (1), generate it.** The code becomes invisible everywhere,
including the create form. `VEG_STARTERS` is derived from "Veg Starters"; a collision takes a
suffix. A manager never sees or types one.

**What generation has to get right**, because a join key that changes is worse than one nobody
sees:

- **Derive once, at creation, and never again.** Renaming a dish must **not** regenerate its code —
  `library/dishes.yaml` and every M04 recipe join on it, and a code that follows the name would
  silently detach a dish from its recipe the first time somebody fixes a spelling.
- **Uniqueness is per restaurant**, matching the existing constraint, and the suffix must be
  deterministic rather than random so a re-seed is reproducible.
- **Rule 46(b)'s sixteen-character limit is about invoice numbers, not dish codes** — do not
  confuse the two. The dish code's only constraint is the column's and uniqueness.
- **Transliterate rather than drop.** A dish entered in Devanagari must still yield a usable ASCII
  code rather than an empty string; `docs/ui/conventions.md` puts Hindi and Marathi in scope later,
  and a generator that returns `""` for a Hindi name would collide on every such dish.
- **The existing uppercase-and-underscore nudge becomes the generator**, not a second
  implementation — it already does the transformation the owner sees today.
- **One generator, used by all four creators** — category, dish, variant and modifier group. Four
  copies of a slug function is how two of them end up disagreeing about apostrophes.

**Modifier group codes are join keys too.** `seed/operations.yaml`'s `modifier_attachments` block
wires groups to categories by code (`{categories: [MAIN_VEG], groups: [SPICE_LEVEL, JAIN_PREF]}`),
which is the same block F6 changes. So the never-regenerate-on-rename rule applies to them exactly
as it does to dishes — and F6 and F11 both touch that file, which is a reason to sequence F6
first and rebase F11's work on it rather than run them in parallel.

---

## F12 · One page where the codes still live

**Owner's words:** *"u can give another page where the list of items and there respective codes are
there, so in case they are required later, people should be able to access it, because i see in
addons, to create new addon group we need group code."*

**This is the owner arriving at a better answer than the one I recommended**, and it resolves a
concern I had raised and then let go. F11 hides codes everywhere; my worry was that the app would
then have no way to show which `library/dishes.yaml` recipe a dish is tied to, which bears on
`docs/owner-actions.md` A15, the chef's review of the 223-dish library. A single reference page
answers that without putting a database key back in front of somebody choosing a starter.

It also answers the create-form problem the owner spotted independently: a manager is currently
asked to invent a group code. With F11's generator that field disappears, and this page is where
the generated value can be read afterwards.

### What the page is

**A read-only table. Name → code, for everything that has one:** categories, dishes, variants and
modifier groups. Searchable, because a 223-dish library is not a page anybody scrolls.

- **It creates nothing and edits nothing.** A code is a join key; a screen that let somebody change
  one would detach a dish from its recipe, which is the same failure the never-regenerate-on-rename
  rule in F11 exists to prevent. Read-only is not a simplification here, it is the safety property.
- **With a CSV export.** `components/ExportButton.tsx` already exists and is the pattern. This is
  what makes the page actually useful for A15 — a chef reviewing the library wants a file to work
  through, not a screen to squint at.

### Two calls made rather than asked, both overrulable

1. **Behind `menu.manage`, not `menu.view`.** Every waiter holds `menu.view` — they need to read
   the menu to take an order — and a waiter has no use for a table of database keys. `menu.manage`
   is the manager and the owner, which is who would ever need one. It is the narrower grant and
   the easy one to widen later.
2. **It lives under the menu, not under settings.** Everything on it is a menu object, and
   `docs/ui/conventions.md` groups screens by what they are about rather than by who maintains
   them.

### It interacts with three other findings

- **F3** (no screen linked twice) — this page gets exactly one link, in one place.
- **F1** (the navigation) — it needs a nav entry and a string, and `reachability.test.ts` will fail
  the build if it has a route and no link. That test is why this cannot be quietly half-built.
- **F11** — this page is the *only* place a code appears after F11 lands, which makes it the one
  screen whose tests must assert codes are present rather than absent.

---

## F13 · There is no way to look at a report with figures in it

**Owner's request:** *"can u please create dummy data for reports tab, so i will be able to
understand what it is, then suggest any changes."*

**The dummy data already exists and reports are guaranteed to show none of it.** Two deliberate
locks, and they close on each other:

1. `app/seed/generate.py:281` — the generator writes history **only** into an organization marked
   `is_demo`. Its docstring: *"refuses to write history into a restaurant whose organization is not
   marked `is_demo` — a second lock on top of M13's reporting exclusion. That one keeps generated
   data out of reports; this one keeps it out of the database."*
2. `ReportingRepository._real_restaurants()` — every M13 report excludes `is_demo` organizations.

So M15's 120 days of trading with its 14 planted signals can never reach a report, **and a test
pins it that way**: `tests/test_planted_signals.py:160` asserts `report.revenue.value ==
Decimal("0.00")` and `report.days == []` for generated data.

**This is good design and a real gap at the same time.** The exclusion is the one filter standing
between demo figures and a real restaurant's books, and it should not be weakened. But the
consequence is that **nobody — owner, reviewer or developer — has ever seen a populated report in
this product**, and the owner cannot give feedback on screens that only ever render zeros.

**Staging does not help.** M13's report screens shipped after `eb8bd6e`, so the deployed build has
no reports tab at all. This has to be local.

### Two ways out

1. **A local-only flip.** Seed as normal, then set `is_demo = false` on the Spice Garden
   organization on the local database. Reports populate immediately with 120 days including the
   planted signals. Five minutes, reversible by re-seeding, never leaves the laptop. **It is a
   hack** — it has to be redone after every re-seed, and it puts a row in a state the seeder does
   not produce.
2. **A third seed path — a "pilot" tenant.** A non-demo organization, generated into, created only
   when `ENV=local` and an explicit flag is set. Both existing locks stay intact for the demo
   orgs; this is a separate, deliberate door. Half a day, and it is the thing that makes report
   review repeatable rather than a one-off.

**Recommendation: (1) tonight so the owner can actually look at the screens and give feedback,
(2) logged as the real fix.** The feedback is the point; the mechanism to produce it is not worth
blocking on.

**Nothing has been done.** The local stack is up (db, api, web) with the base seed only — 2
organizations, 5 orders, both `is_demo`. No generation has run and no flag has been changed.

---

## F14 · Workload will show figures, and they will be wrong

**Owner's request:** *"do the same for workload tab as well, i need some data to understand what it
is and how it works."*

**Workload is not blocked the way reports are, and that is the good news.**
`repositories/performance.py` does **not** filter on `is_demo` — only M13's reporting repository
does. So M17's screens will populate from seeded data with no flag to flip. F13's workaround is not
needed here.

**The bad news is that the numbers will not mean anything**, because two parts of the seed cover
completely different windows:

| What | Source | Window |
|---|---|---|
| Orders served, ratings, complaints | `seed/generate.py`, `DEFAULT_DAYS = 120` | **120 days** |
| Roster and hours worked | `seed/shifts.py`, `_DAYS_BACK = 3`, `_DAYS_FORWARD = 7` | **3 days back, 7 forward** |
| Hours actually *clocked* | `seed/shifts.py` — *"Only yesterday and today are clocked in"* | **2 days** |

`PerformanceRepository.worked()` reads hours from `shift_assignment`. So a workload period of a
month compares **120 days of orders against 2 days of attendance**. Every per-hour figure is
inflated by roughly sixty times, and attendance reads as though the entire team missed almost every
shift.

**This is worse than an empty screen.** Zeros are obviously nothing; these are plausible-looking
numbers that are wrong, on the one module whose output can reach somebody's pay
(`docs/workload-fairness.md`, ADR 0011). An owner shown this screen would draw conclusions about
real people from an artefact of the seed.

### What would make it honest

1. **Generate the roster alongside the trading.** The generator already knows which waiter served
   which order on which business date — the same loop can write `shift` and `shift_assignment` rows
   across the same 120 days, clocked. This is the real fix, it is the same shape as the work M15
   already does, and it is what M17's own review would have wanted.
2. **Or pin the workload period to the clocked window** — yesterday and today only. Honest, and
   nearly useless: two days of one restaurant is not enough to show what the module is for.

**Recommendation: (1).** It is the only version where the owner can look at a month of workload and
have the figures mean what they appear to mean. It also unblocks M17's planted-signal review —
signal 6 in `generate.py:515` is *"one waiter's accuracy errors, on dinner shifts only"*, and
**that signal cannot currently be seen at all**, because there are no dinner shifts to concentrate
it on beyond yesterday.

### Related

Same root as F13 — the demo world was built to exercise the code, not to be looked at by a person.
F13 is "the data is hidden from the screen"; this is "the data is there and half of it is missing".
Both surfaced the moment the owner tried to *read* a screen rather than test it.

---

## F15 · Alert cards are invisible in the Dark theme

**Owner's words:** *"Alerts tab is not coming properly, alert boxes are of a similar colour as text
and hence text colour cant be seen."*

**Reproduced by computation, not by eye.** Contrast of the alert card's text against its own
background, WCAG AA minimum 4.5:1:

| Theme | Pair | Ratio | |
|---|---|---|---|
| Light / Warm | `foreground` on `critical-soft` | 15.38 | pass |
| Light / Warm | `muted-foreground` on `critical-soft` | 5.89 | pass |
| **Dark** | `foreground` on `critical-soft` | **1.04** | **fail** |
| **Dark** | `foreground` on `caution-soft` | **1.02** | **fail** |
| **Dark** | `foreground` on `warning-soft` | **1.02** | **fail** |

Identical colours score 1.0. At 1.04 the text and the box are the same colour to within rounding —
not hard to read, *invisible*.

### Two correct decisions colliding

- **The six alert colours and their `-soft` fills are locked on purpose.** `tokens.css:108`
  declares them under `:root, [data-theme]` so no theme can repaint them —
  *"a festive theme that makes red decorative breaks the only promise the kitchen display makes."*
  `--critical-soft: 0 80% 96%` is therefore a near-white pink in **every** theme.
- **The Dark theme legitimately sets `foreground: 210 20% 96%`** (`themes.ts:95`) — near-white text
  on a near-black ground.

Near-white ink on a near-white fill. Neither decision is wrong on its own; **nothing checks the
pair.**

### The screen makes it certain

`NotificationsScreen.tsx:60-62` applies the tint with **no text colour**:

```
critical: 'border-critical/40 bg-critical-soft',
warning:  'border-caution/40 bg-caution-soft',
caution:  'border-caution/40 bg-caution-soft',
```

So the text inherits the page `foreground`. Design-system rule 11 is explicit that this is the
mistake: *"A status badge is soft fill, **strong ink**, and a word … its contrast is text-on-soft,
not text-on-page — check that pair, because the page pair passing proves nothing about it."*

### Why no test caught it, admitted in the design system itself

`theme.test.ts` computes contrast across every shipped theme and refuses any pair below 4.5:1 — but
it checks **foreground on background**. The design system's own "what is not built yet" list says:
*"a `Badge` component and a contrast test for text on each `-soft` fill — rule 11 is followed by
hand until then."* Followed by hand, and this is the hand slipping.

### The fix has two halves, and the second is the one that matters

1. **Set the ink.** Every `-soft` fill gets its `text-<alert>` partner, per rule 11 — on this
   screen and anywhere else a `-soft` background is used without one. **Audit every use**, because
   this screen is unlikely to be the only one.
2. **Extend `theme.test.ts` to the `-soft` pairs**, across every shipped theme. This is the gap the
   design system already documented and deferred; it has now cost a broken screen, which is the
   trigger for building it. Without it the same defect returns with the next theme or the next
   `-soft` fill.

**Do not "fix" this by unlocking the alert tokens per theme.** The lock is load-bearing — it is
what keeps red meaning *act now* on the kitchen display in every theme. The answer is ink that
suits the fill, not a fill that drifts with the theme.

### Worth checking in the same pass

`--neutral-soft`, `--info-soft` and `--success-soft` are locked the same way and will fail
identically wherever they carry inherited text. `MenuScreen.tsx:157` and `:295` use
`bg-neutral-soft` with `text-neutral` — correct, and a useful example of the pattern this screen
should follow.

---

## F16 · The owner is told to ask their manager

**Owner's words:** *"My performance page should not be there for owner, it says ask ur manager,
which should not be happening, he should be giving reviews to people there rather than getting
reviewed."*

**The message is `strings.ts:1549`** — `noPeriods: 'No periods have been set up yet. Ask your
manager.'` An owner has no manager, and is the person who would set a period up. The sentence is
wrong for them in both halves.

**But the message is not why the page is empty** — see F17. Nobody has any figures, because no
incentive scheme is ever loaded. Fix F17 and the owner still sees a page about themselves; fix this
one and the owner sees a correct sentence about an empty page. They are different defects and both
are real.

### The harder half: should the page exist for the owner at all?

**There is a documented promise in the way.** `AppShell.tsx:41-43` carries no permission check on
this link, with the comment: *"M17. Every role, always — ADR 0011 makes it a structural guarantee,
so this link has no permission check on it and is not supposed to."* The seed says the same:
*"performance.view.own is on EVERY role by design (ADR 0011): a score an employee cannot see is
surveillance; the same score, visible, is feedback."*

**That promise is about people who are measured.** An owner who is not scored has nothing to see,
so hiding it from them does not breach the guarantee — but the guarantee is load-bearing and the
change must be made in a way that cannot quietly strip the page from somebody who *is* scored.

**And it cannot be done by role name** (ADR 0007), nor by permission: `performance.view.own` is
deliberately held by everyone, so it cannot distinguish.

Three mechanisms, none free:

1. **Hide it from anyone who holds `performance.view.team`.** Permission-based, so ADR 0007 holds.
   Reads as *"you review others, so you get the team screen instead."* **Risk:** a manager who is
   themselves scored would lose sight of their own figures — which is the exact harm ADR 0011
   exists to prevent. Only safe if managers are never scored, which must be confirmed rather than
   assumed.
2. **Hide it when the person is not in the active scheme's scope** — data-driven and exactly
   correct by definition. Costs a query before the navigation renders, and the nav is on every
   screen.
3. **Keep the link, fix the sentence.** An owner opening it sees *"You are not scored under the
   current scheme"* and a link to the team workload screen. Cheapest, honest, and leaves a page
   nobody needs in the navigation — which is also F3's complaint about clutter.

**Recommendation: (2), with (3)'s wording as the fallback for anyone genuinely unscored.** It is
the only one that cannot misfire, and `unscored()` already exists from M17 to answer the question.

---

## F17 · The incentive scheme is designed, written down, and never loaded

**Owner's words:** *"some data should be there, for performance and shifts page, wherever they
are."*

**M17 has no seeder.** `backend/app/seed/` contains modules for identity, setup, menu, stock,
inventory, procurement, customers, orders, counts, waste, shifts and the history generator —
**and nothing for performance.** `__main__.py` imports and runs each of those; there is no
performance import to run.

**Yet the scheme is fully specified in `seed/operations.yaml`**: the weights, the `context_only`
metrics carried beside a score at weight zero (`kitchen_delay_minutes`, `section_footfall`,
`average_table_size`, `tips_received`), and the award types
(`cash, leave, shift_preference, meal, recognition_only`). Somebody designed the whole thing in
data and no code reads it.

**Confirmed against the running database:** `incentive_scheme` 0 rows, `performance_period` 0 rows.

So the chain breaks at the first link — **no scheme → no period → no score → every user sees "No
periods have been set up yet."** This is not an owner problem; M17's screens are unreachable for
everybody in every seeded environment, which is why the module has never been looked at by a person.

### What a performance seeder has to create

- the incentive scheme from the YAML that already describes it, so the file stops being decorative;
- **at least two closed periods and one open one** — a single period cannot show a trend, and
  "still open" versus published is a distinction the screen draws (`strings.performance.stillOpen`);
- scores for the people the generated trading already credits as waiters.

### It depends on F14 and must not be built before it

A score needs hours worked. **The roster covers 3 days back and 7 forward, clocked for 2, while the
trading covers 120 days** (F14). A performance seeder built on top of that would produce
scores computed from 120 days of orders over 2 days of attendance — **plausible-looking figures
that are wrong, published, on the module that can reach somebody's pay.** F14 first, then this.

### Shifts

The second half of the owner's request. The shifts screen has the same cause as F14: the roster
exists but spans ten days around today, and only two are clocked. There is no separate defect here
beyond what F14 already records — fixing F14 fixes the shifts screen and unblocks this one.

---

## F18 · Every attachment link returns "Please sign in"

**Owner's words:** *"in conversation i see that it got attached but while opening i see —
`{"code":"auth.required","message":"Please sign in.","issue":1006}`."*

**Root cause, and it is total rather than intermittent.**

- This product authenticates with a **Bearer token in an `Authorization` header**, held in
  JavaScript memory (`shared/api.ts:186`).
- `attachmentHref()` (`api/communication.ts:410`) returns a bare path,
  `/api/v1/staff/attachments/{id}`, and `AttachmentControl.tsx:85` puts it straight into an
  `<a href>`.
- **A browser following a link sends cookies. It cannot send an `Authorization` header.**
- `GET /attachments/{id}` requires an authenticated actor holding `message.send`
  (`attachments.py:157`), so it refuses — `auth.required`, issue 1006.

**No attachment in this product has ever been openable.** Not a race, not a size limit, not this
file: every attachment link, for every user, every time. The upload itself works — which is why it
appears in the conversation and then fails to open.

**The refresh cookie does not rescue it.** It exists, but this endpoint resolves an actor from the
access token, not from that cookie.

### Why it slipped through

The upload path has a careful note about exactly this class of problem — `shared/api.ts:397`:
*"This deliberately sends no `Authorization` header. The URL already carries its own signature, and
attaching this session's token would hand a live credential for our API to another host."* Somebody
reasoned precisely about credentials on the **upload** leg and the **download** leg was left as a
plain link.

### The fix, and the one that is wrong

**Wrong:** put the token in the query string. It lands in browser history, in server logs, and in
`Referer` headers — a live API credential in three places that outlive the request.

**Options:**

1. **Fetch with the header, then open a blob URL.** The screen requests the bytes through the
   normal client (which attaches the token), makes an object URL and opens or downloads that.
   No new endpoint, no new credential, and it works for the inline-bytes response the server
   already returns. Costs holding the file in memory briefly.
2. **A short-lived signed download URL**, like the upload leg already uses — a separate token
   scoped to one attachment, minutes long, single purpose. Cleaner for large files and for the
   S3 redirect path, and it matches the pattern already in the codebase.

**Recommendation: (1) for the fix, (2) if attachments ever get large.** (1) is small and closes a
completely broken feature today.

**The regression test writes itself:** assert that no attachment is reachable by a request carrying
no `Authorization` header **and** that the screen can open one — the second half is what was never
tested, because every existing test calls the API as a client that sets the header.

---

## F19 · A successful upload looks like a failed one

**Owner's words:** *"i am not able to upload any image, it can be upto 10 mb, mine is in kbs but
still they dont show it s loaded, it should show it got attached."*

**The upload was working.** The file reached the conversation — the owner says so in the same
sentence. What is missing is the product telling them so.

`AttachmentControl.tsx` documents **three** states: *"choosing, uploading with the button disabled
and its label saying so, and the failure in place with the server's own words."* Pending and error
are both handled (`:105`, `:114-115`). **There is no success state.**

`docs/engineering-standards.md` §5 and design-system rule 6 both require **pending, error *and*
success** explicitly. The component's own docstring enumerates three states and success is not one
of them, so this is a rule that was read and then applied incompletely.

**The consequence is not cosmetic.** Silence after an upload reads as failure, so the natural
response is to upload again — and a restaurant on a slow connection now sends the photo three
times. M09's photo nudge and M11's attachments are both aimed at people documenting waste and
breakages in a hurry.

**Fix:** a success state that names what was attached, and keeps the file visible in the control
until the message is sent.

---

## F20 · Messages have no sample data either

**Owner's words:** *"Same in message, i dont see any sample data."*

**Confirmed: M11 has no seeder.** `backend/app/seed/` has modules for identity, setup, menu, stock,
inventory, procurement, customers, orders, counts, waste and shifts, plus the history generator.
There is none for communication, and `__main__.py` imports none.

**The same family as F17.** M11 and M17 both shipped complete, tested and with no way for a person
to open the screen and see it working. The pattern worth naming: **a module is not finished when
its tests pass; it is finished when somebody can look at it.** Three of the owner's last five
findings are this same gap wearing different clothes (F13 reports, F17 performance, F20 messages).

**What a communication seeder needs:** a few conversations of the kinds the module was built for —
a shift handover, a broken-equipment thread with a photo, a manager's announcement — with messages
spread across recent days so the list has an order to it, and **at least one attachment**, which
would have made F18 visible on the first manual pass rather than the sixth.

---

## F21 · A restaurant cannot create a shift

**Owner's words:** *"i am also not able to put anyone on shift, and no error shows up."*

**There is no shift-creation screen anywhere in the product.**

- `POST /shifts` exists — `api/v1/staff/shifts.py:116`.
- `useCreateShift()` exists — `frontend/src/staff/api/shifts.ts:115`.
- **No `.tsx` file calls it.** Checked across the whole staff tree.

The backend and the data layer were both built; the screen never was. This is the same shape as the
M03/M04 defect already recorded in this codebase — *"screens behind routes that nothing linked
to"* — one layer deeper: an endpoint and a client hook with no screen at all. `reachability.test.ts`
cannot see it, because that test checks routes against links and this has neither.

### Why it is worse than one missing screen

Shifts are the root of a chain:

**no shift → no roster → no hours worked → no workload score.**

`PerformanceRepository.worked()` reads hours from `shift_assignment`. So M12 is unusable and M17 is
uncomputable, for a reason that is neither module's fault.

**And it is precisely a cold-start defect**, which is this product's central risk
(`docs/onboarding-cold-start.md`). A **seeded demo** gets `MORNING` and `EVENING` from
`seed/operations.yaml`, so every test and every demo has shifts. A **real restaurant** signing up
gets none, and has no way to make one. The seed hid the defect from everybody who has looked at
this module — the owner found it only because their local database had not been fully seeded, which
put them accidentally in a new restaurant's shoes.

### What is needed

A shift editor, wherever restaurant configuration lives — the same place as dining areas, kitchen
stations and tax rates, all of which already have screens. It is a small screen: a code, a name, a
start and an end, and `ADR 0004` already handles a shift that crosses midnight (`EVENING` is
17:30–00:30).

**It should also be part of onboarding.** A restaurant with no shifts cannot roster anybody, so
"create your shifts" belongs beside "create your dining areas" in the cold-start flow rather than
being something an owner discovers is missing.

---

## F22 · The roster screen refuses silently

**The second half of the owner's report**, and a defect in its own right — it is what turned F21
from a missing feature into a mystery.

`RosterScreen.tsx:274` disables the button with
`disabled={!ready(employeeId, shiftId, day) || assign.isPending}`. `shiftId` can only be chosen
from `shifts.data?.items ?? []`. With no shifts, that list is empty, `shiftId` stays `null`, and
**the button can never be enabled**. Clicking does nothing, no request is made, and therefore no
error is shown — `assign.error` is null because nothing was ever attempted.

**The disabling itself is correct** and follows the design system: *"Disable a control at its limit
instead of hiding it, so nothing shifts."* What is missing is the other half of the same rule —
*"an empty state that says what will appear and how to make it appear."* The screen has that
message for the roster (*"Nobody is on the roster yet"*) and none for the thing actually blocking
the user.

**Fix:** when the shift list is empty, say so where the shift is chosen, and link to where a shift
is created once F21 exists. The same check applies to the staff list and the dining areas — a
restaurant with no employees cannot be rostered either, and would fail just as silently.

**The general lesson worth carrying past this finding:** a disabled control is only honest if
something on screen explains it. Three `Choices` lists feed one button here, and any of the three
being empty produces the same dead button with no way to tell which.

---

## F23 · The design gallery works; the warning it prints does not

**Owner's words:** *"Check design page it surely doesnt work properly, no button does anything,
just review it properly."*

**Reviewed in a real browser, signed in as the owner, not by reading the code.**

### First, the reassuring half

**The page is working, and most of those buttons are inert on purpose.** `/design` is a component
gallery, shown only in a development build (`AppShell.tsx`, `DesignGalleryLink`). The row of
Primary / Secondary / Brand / Ghost / Destructive / Disabled buttons exists to show what each
*looks* like; none has an `onClick` and none should. The same is true of the table, the fields
(all `readOnly`) and the notices.

The genuinely interactive specimens **do** work. Clicking *"Open a dialog"* opens it — verified,
with the dialog rendering its title, body, "Yes, close it" and "Close".

So "no button does anything" is mostly the page behaving as designed, and it is fair that this was
not obvious: **nothing on the page says it is a gallery of appearances rather than a working
screen.** A one-line explanation at the top would have saved the confusion, and is worth adding.

### Second, the real defect

Opening that dialog prints a React error, twice:

```
Warning: Function components cannot be given refs. Attempts to access this ref will fail.
Did you mean to use React.forwardRef()?
Check the render method of `Primitive.button.Slot`.
    at Button (src/shared/ui/button.tsx:52)
    at DialogTrigger (@radix-ui/react-dialog)
```

**`shared/ui/button.tsx` does not wrap its component in `forwardRef`.** It is the **only** component
in `shared/ui/` that does not — `dialog.tsx`, `label.tsx`, `select.tsx`, `sheet.tsx`, `switch.tsx`
and `table.tsx` all do.

**What breaks.** Radix uses the trigger's ref for focus management. The click still works, because
that rides on event delegation — which is why the dialog opens and the defect looks like nothing.
But **focus is not returned to the trigger when the dialog closes**, and that is the behaviour
somebody navigating by keyboard depends on. A kitchen or a busy till is exactly where people stop
using a mouse.

**This is design-system rule 4 biting a second time.** The rule — *"Do not hand-roll what shadcn/ui
provides … Radix has solved focus management, ARIA and keyboard behaviour and a solo project will
not"* — carries its own note that *"this rule exists because it was already broken once: M01
hand-rolled three components."* shadcn's own Button ships wrapped in `forwardRef`; this one was
written by hand and the wrapper was left off.

### The fix

Wrap `Button` in `React.forwardRef` and pass the ref through, matching every sibling in
`shared/ui/`. Small, and it silences a warning that is currently printed on every page carrying a
Dialog or Sheet trigger — nine `asChild` usages across the staff app today.

**Add a test that fails on a React console error.** The warning has been printing all along and
nobody saw it, because no test asserts a clean console. That is the reason this survived, and it
will be the reason the next one does.

---

## Batch 1 — shipped 2026-09-19

**F18, F19, F23, F15, F22.** Frontend correctness: a completely broken feature, a warning nobody
saw, and three screens that failed silently. `vitest` 439 passed (was 434); eslint and `tsc` clean.

**What the work turned up that was not reported:**

- **Two locked colour tokens were below the accessibility floor, and always had been.** The new
  soft-fill test found `--warning` at 4.06:1 on its own fill and **4.33:1 as plain text on the
  page**; `--caution` was worse, at 3.63:1. Both are now 37% and 29% lightness, hue and saturation
  untouched — the lock is on what a colour *means*, and a deeper orange means the same thing.
- **Three more screens had the same soft-fill defect as the alerts page** — two on
  `StockOnHandScreen` and one on `WasteScreen`, each a tinted panel with no ink. The first version
  of the test passed while finding nothing, because a mangled escape made its pattern match a
  control character instead of a word boundary. **A green test that has never failed is not
  evidence**; this one was made to fail first, and then found three more.
- **The focus defect in F23 was real, not theoretical.** Reverting the fix made the new
  focus-return test fail outright: with no `forwardRef`, focus never returned to the trigger after
  a dialog closed.

**F15's fix is not the obvious one.** Painting the alert card in alert ink would satisfy the
contrast rule and produce a paragraph of red text. Severity moved to a left stripe plus a badge —
soft fill, strong ink, and a word — and the card keeps a normal surface where `foreground` is
readable in every theme. Rule 11's pairing is right for a badge and wrong for a card.

---

## Batch 2 — shipped 2026-09-19

**F5, F6, F7, F8.** Permissions, the seed and three migrations (0056–0058).

**Two of my own findings were wrong, and implementing them is what found the errors:**

- **F5 said the owner already could not be assigned as a waiter.** They could. The `owner` role is
  `["*"]` and the seeder expands it into all 55 permissions, so the owner held `order.create` and
  appeared on every table's waiter list — the exact thing reported. Reading grants out of the YAML
  without accounting for the wildcard is how it was missed.
- **F8 warned that granting a manager the password reset would open an escalation path.** It
  would not: `may_reset_password` already requires strictly more senior and says so at length. The
  finding was written without reading the service.

**The consequence of the first is the shape of the whole fix.** A new permission could never have
worked — an owner holds every permission that exists, including any added tomorrow — and ADR 0007
forbids checking the role name. So "serves tables" became `employee.takes_tables`, a column: a fact
about the person's job rather than a grant of authority, set per person. A manager who genuinely
covers Friday service gets the switch; one who never waits a table does not.

That column then answered F7 as well. "The table has asked for the bill" is a floor action, not an
authority, and it could not be hidden from an owner by permission for the same reason. It is
**hidden and not removed**: it is the only thing in the product that sets `bill_requested_at`,
because the guest app is read-only, and that timestamp is what bill-to-settle time is measured
from.

**F6 needed a finer granularity than the owner asked for.** Removing the group from the two non-veg
categories would have left it on `CHINESE`, which holds veg and non-veg dishes side by side. The
attachment now filters on the dish's own `food_type` — the field with a statutory basis, and
therefore the one that is never empty.

    pytest (5 affected suites) 103 passed · vitest 440 passed · ruff, mypy, eslint, tsc clean

---

## F24 · The cost breakdown names ingredients by code

**Found by the discipline test written for F11**, not by the owner.

`DishCostScreen.tsx:239` renders `line.code` for each ingredient in a dish's cost breakdown. Its
own comment says why the screen exists:

> *"The breakdown is the product. '₹126.70' is not actionable; '₹63 of it is the chicken tikka' is
> what an owner uses when the price of chicken moves."*

**That is exactly the sentence a code cannot say.** The screen prints `PREP_CHICKEN_TIKKA` where
its author intended a name.

**It is not part of F11 and was deliberately not folded into it.** F11 removes codes that sit
*beside a name*, where the name is already there. Here there is no name to fall back on:
`CostedLine` carries `component_id`, `code`, `quantity`, `unit_cost` and `cost` — the API sends no
name at all. So removing the code would leave the row with nothing identifying it, which is worse.

**The fix is a schema change:** add `name` to the costed line, show it, and keep the code out. A
backend change rather than a screen change, which is why it is its own row.

Until then `menuDiscipline.test.ts` exempts the screen **explicitly, with this reason written into
the exemption**, so it reads as a decision rather than as a gap in the rule.

---

## Batch 3 — shipped 2026-09-19

**F11, F12 first, then F1, F2, F3.** All frontend, all the navigation and the menu.

**Checked in a browser at 400px, not only by test.** The header now shows Tables · Bills · Cash and
a Menu button; the drawer opens with real group headings and scrolls. The home page shows the ten
screens the header does not carry, grouped, with nothing repeated.

**What the work turned up:**

- **`reachability.test.ts` reported twenty-one unreachable screens** the moment the navigation
  moved into `navigation.ts`, because it globbed only `.tsx`. It was right to complain — the links
  really had left the files it was reading. Widened to `.{ts,tsx}`.
- **A first version of the duplicate test asserted "every route is in the navigation" and was
  wrong.** `/reports/sales`, `/reports/waste`, `/reports/dishes` and `/reports/variance` are
  reached *from* the Reports screen on purpose — M13: *"one link, because Today is the way into the
  other four"*. That assertion is gone, with the reason written where it used to be.
- **`HomeScreen.test.tsx` threw rather than failing** on the new empty case: a person whose screens
  are all in the header now lands on an empty home page, which is correct, and `getAllByRole`
  throws on zero matches.

**Three of the owner's four navigation defects had the same root**, and it is worth naming: the
header and the home page were two hand-written lists that had to agree and had no way to. Four
separate comments across the two files record somebody noticing a gap and patching one side. They
are one list now, partitioned, and `navigationDiscipline.test.ts` refuses a screen offered twice.

    vitest 459 passed (was 455) · eslint 0 · tsc 0
    migrations 0056, 0057, 0058 applied to the local database and verified

---

## F21 — shipped 2026-09-19

`/settings/shifts`, beside the other things a restaurant sets up once. Behind `shift.manage` rather
than `restaurant.configure`: rostering and configuring are different jobs, and the person who runs
the rota is not always the person who sets up the restaurant.

**Verified against a database with no shifts** — the state the owner was actually in:

    GET  /staff/shifts            -> {"items":[]}
    POST /staff/shifts  Evening   -> 201, crosses_midnight: true   (17:30-00:30)
    POST /staff/shifts  Morning   -> 201
    GET  /staff/shifts            -> both, newest first

`crosses_midnight` comes back true for the evening shift, which is ADR 0004 working: an evening
shift in a place that closes at two ends before it starts, and that is not an error.

**The chain this unblocks:** shift → roster → hours worked → workload score. The roster's "Staff"
button can now be enabled at all, and `PerformanceRepository.worked()` has something to read.

---

## F14 and F17 — shipped 2026-09-20

**F14: the roster now reaches exactly as far back as the generated trading**, because a workload
score divides one by the other. It is not a larger constant — a constant drifts again — but the same
`SEED_DAYS` the generator reads, so `make seed-small` shortens both and neither can be changed
alone. `tests/test_seed_roster_window.py` is what holds that.

**F17: `app/seed/performance.py` exists.** It reads the scheme `seed/operations.yaml` had described
for months and nothing had ever loaded.

**Periods are seeded as drafts and none is published**, deliberately. Publishing is the freeze
(ADR 0011) — it writes figures into `performance_score` and they are never recomputed. A seeder that
published would have to invent who published it and freeze numbers nobody reviewed, and it would
take from the owner the one action on that screen worth doing. A draft computes live, so what is on
screen is real.

**It calls the service rather than inserting rows**, so `validate_weights` still refuses a scheme
where volume stands alone, and a seeded scheme cannot be one the application would reject.

### Measured after seeding a 30-day window

    roster       456 assignments, 358 clocked, 2026-08-21 -> 2026-09-27
                 (was: 3 days back, 2 clocked)
    trading      1189 orders, all with a waiter, 2026-08-22 -> 2026-09-20
    performance  1 scheme, 2 periods
    workload     6 people with hours, covers, orders, assists and share-of-work

Hours cross-checked against SQL rather than trusted: 244.47 over 38 shifts, and 231.60 over 36 for
the person deliberately left un-clocked one day. The API and the database agree to the minute.

### Two things worth recording

- **The seeder needed a real employee.** `create_scheme` is `@audited` and `audit_log` has a foreign
  key to `employee`; a scope-shaped actor got a `ForeignKeyViolationError`. That is the audit trail
  refusing to name somebody who does not exist, and it is right to. The scheme is attributed to the
  restaurant's most senior employee — found by `min(Role.rank)`, not by role name (ADR 0007).
- **My first verification measured nothing.** I called a URL that does not exist, parsed the 404
  body as a result object and reported "people scored: 0" — which looked exactly like a real
  finding. A check that cannot distinguish "empty" from "wrong address" is not a check.

**The team screen shows two of six people, and that is correct**: `team()` returns the top third
plus your own row and never a bottom ranking, because naming the top two of three names the third.
The distribution screen shows all six.

---

## F20 — shipped 2026-09-20

`app/seed/communication.py`: three threads of the kinds M11 was built for — an evening handover, a
walk-in freezer that is icing up, and a manager telling the floor Sunday is full. Nine messages,
more than one voice in each, backdated so the list has a believable order.

It calls `ConversationService` rather than inserting rows, so the dedupe, the refusals and the
revision counter the stream depends on all still apply, and a seeded thread cannot be one the
application would reject.

**Running it against the local database proved nothing**, and it is worth recording why. Threads
were already there from hand testing, the get-or-create guard correctly skipped, and the log said
*"Seed data already present; nothing to do."* That is the seeder working — and it is not evidence
that it produces anything. `tests/test_seed_communication.py` answers the question on a clean
database, which is the only place it can be answered: **5 passed**, 3 conversations, 9 messages.

**No attachment is seeded, and that is named rather than hidden.** Every attachment in the product
returned `auth.required` from M11 until F18 was fixed, and nobody saw it because no seeded thread
had a file on one — the defect was reachable only by uploading by hand. A seeded attachment would
have caught it on the first manual pass rather than the sixth. It is absent because an attachment
needs bytes in object storage, which a seeder that must run identically on a laptop and in CI
should not invent. Worth doing when the storage seam is next touched.
