# M07 · Orders / POS — Build Log

**Started 2026-09-13**, continuing the autonomous run from M06 on the owner's instruction
(*"you start with M07 as well once you are done with M06… refresh ur memory and then start M07"*).

Spec: `docs/modules/M07-orders-spec.md` (`a40ea95`). **Resume from the State table below.**

---

## State

| PR | Chunk | What | State | Commit |
|---|---|---|---|---|
| — | — | Research + spec | ☑ done | `a40ea95` |
| 1 | A | Log-context fix · UUID redaction fix | ☑ done | `6dfec22` |
| 1 | B | Migration 0019 + models + schema doc + enums | ☑ done | `142105f` |
| 1 | C | Permissions 0020 + `cash.manage` design amendment | ☑ done | `5281f5b` |
| 1 | D | Tax core: FY, line split, median rate date, apportionment | ☑ done | `5151e2a` |
| 1 | E1 | Orders, lines, modifiers, send/serve/bill/cancel · table status | ☑ done | `437a9e6` |
| 1 | E2 | Discounts, charges, split | ☑ done | `1851657` |
| 1 | — | **PR 1 gate: full `make check`** | ☑ green on the second run | fix `65e0418` |
| 2 | F | Idempotency mechanism + retrofit M06 receiving | ☑ done | `817dd27` |
| 2 | G | Settlement: invoice numbering, payments, consumption, cost freeze | ☑ done | `f567ee0` |
| 2 | H | Credit notes, invoice cancellation, refunds | ☑ done | `229fedf` |
| 2 | I | Cash sessions, counts, payouts, adjustments | ☑ done | `706e3e1` |
| 2 | — | **PR 2 gate: full `make check`** | ☑ green | `9762194` |
| 3 | J | Table map, order taking, bill, split, payment | ☑ done | `17992c4` |
| 3 | K | Void / credit note, cash-up screens, waiter patterns | ☑ done | `700efc6` |
| 3 | L | Seed, review, second reader, manual script, compliance-rules.md | ☑ done | this commit |
| 3 | — | **PR 3 gate: full `make check`** | ☐ next | — |
| — | — | **Your manual pass** — `docs/manual-tests/M07-orders.md` | ☐ | — |

**Resequenced from the spec:** chunk A was planned as "log-context fix · table status transitions".
The table-status guard refuses `free` while an order is open, which needs the `order` table — so it
moved after chunk B and ships with chunk E.

**Full `make check` runs at the end of each PR**, not after every chunk: running it while the next
chunk's files are being written lets pytest collect half-written modules and blame the wrong commit.
Every chunk still has its targeted tests, the generic suites, lint, types and both audits before it
is committed.

---

## Chunk A — two defects nothing could see (`6dfec22`)

**The tenant was never on a log line.** `docs/observability.md` said every line carried
`restaurant_id` and `actor_id` automatically. `app/core/logging.py` declared both context variables
and the formatter read them — but nothing ever *set* them. Fixed in `current_actor`, plus a middleware
step: the access line is written after the handler returns, in a context the handler's variables
don't reach, so the tenant is carried back via `request.state`.

**The phone redactor ate UUIDs.** Its boundaries excluded digits but not hex letters, so a UUID whose
last group held a bounded ten-digit run starting 6–9 logged as `…-[redacted]ab` — about one id in two
hundred, including locked-account ids in the security log. Fixed by carving whole UUIDs out of the
scan; the wider fix (loosening the phone boundaries) was rejected because it would stop redacting a
phone number glued to a word.

Red run before the fix: **5 failed, 1 passed** — the passing one was the leak test, trivially true
while nothing was set. Green after: 69 targeted, 21 generic suites.

**Also found, deliberately not fixed here:** no handler anywhere logs a business event at INFO — only
three auth warnings exist. The Definition of Done's *"business events logged at INFO with request_id
and restaurant_id"* was unmet by every module before M07, not merely unenforceable. M07 logs its own
events. The retrofit for M03–M06 belongs in `docs/backlog.md` at the end of this module, with the list
of events each should emit.

---

## Findings that shaped chunk B, before any of it was written

**Three parents lack the constraint a composite foreign key needs.** `recipe`, `stock_item` and
`tax_group` carry `UNIQUE (id, restaurant_id)`; `menu_item_variant`, `modifier` and `restaurant_table`
do not. Migration 0019 adds those three first. Safe on any existing data by construction — `id` is
already unique, so the pair is too.

**`order` is a reserved word.** SQLAlchemy quotes it in generated DDL and queries; every raw
`op.execute` in the migration — the immutability triggers — must write `"order"` by hand.

**Settled orders are immutable, open orders are not.** So the `order` trigger cannot be the blanket
append-only trigger `stock_movement` and `goods_receipt` use. It refuses UPDATE and DELETE only when
the *existing* row is in a terminal state.

**`customer` does not exist until M10**, so `order.customer_id` is a column without a foreign key — the
same arrangement M05 used for `stock_batch.supplier_id` until M06 created `supplier`.

---

## Chunk B — fourteen tables, and what the database now refuses

Migration `0019_m07_orders`, `app/models/orders.py`, fifteen enums mirrored to TypeScript, and
`tests/test_orders_schema.py` (56 tests, every one against real Postgres). `docs/schema.md` §7 is
rewritten to the built design with a *"What migration 0019 added"* section; header 64 → 72 tables.

**Refinements to the committed spec, decided while writing the schema:**

- **`cash_payout` became `cash_movement` (`payout` | `adjustment`).** Same shape; two tables would be
  two places to sum — the reason `refund` was eliminated.
- **`payment.status` is `success | failed`.** `pending` and `refunded` both describe a row changing
  later, which an append-only row cannot do.
- **`order_line.status` gained `sent`**, and already allows M08's `preparing` and `ready`.
- **`order_number` is unique per business day**, not per restaurant forever.
- **The invoice snapshots supplier name, address, GSTIN and FSSAI number.** A reprint is the
  document as issued.
- **CHECKs, not conventions:** a negative payment must reference a credit note; a tax invoice must
  carry a supplier GSTIN; a bill of supply carries no CGST/SGST; invoice and credit-note numbers ≤ 16
  characters; a GST line's halves are equal; a service charge is optional; a till cannot close
  without its count.

**Three holes found in my own first trigger design, before any test ran:**

1. **A line could be added to a settled order** — the triggers fired on UPDATE and DELETE only.
   Adding a line to a paid bill is the edit that matters most. Children now trigger on INSERT.
2. **Counter service pays before it cooks.** A trigger freezing every column would stop the kitchen
   marking a paid order's dishes ready. A settled order may change only `served_at`,
   `first_sent_at` and the void fields; a settled line only its kitchen status and `sent_at`.
   The comparison is `to_jsonb(NEW) - allowed` against `to_jsonb(OLD) - allowed`, so **a money
   column a later migration adds is frozen by default**, not by remembering to list it.
3. **Deleting a sent line** is how a served dish leaves a bill. A line may be deleted only while
   `pending`; afterwards it is cancelled with a reason.

**Constraints chunk G must respect:**

- **Flip the order to `settled` last.** Re-freezing line tax, writing `recipe_id` and
  `theoretical_unit_cost`, and adding charges must all happen while the order is still live — the
  triggers refuse them one statement later.
- **`Order.version` is SQLAlchemy's `version_id_col`.** Every ORM UPDATE is
  `… WHERE version = :loaded` and bumps it; a stale write raises `StaleDataError`, which the service
  must map to 409. A Core `update()` does not bump it.
- **The invoice number's uniqueness is the database's; its gaplessness is the service's** —
  the per-restaurant, per-FY advisory lock in chunk G.

**Deviations from habit, recorded so a reviewer does not "fix" them:** three trigger bodies carry
`# noqa: S608` — they interpolate only module constants, never input. `__mapper_args__` carries
`# noqa: RUF012`, because `DeclarativeBase` already types it and mypy rejects `ClassVar`.

Green before commit: 56 schema tests; 146 across migration round-trip, generic suites, enum mirror
and the M01/M06 schema suites; ruff, format, mypy over `app` and `tests`; `tsc`, eslint on the enum
mirror; both audits.

---

## Chunk C — who may make money disappear

Migration `0020_m07_order_permissions`; the catalogue, `PermissionCode` and the frontend mirror.

| Permission | owner | manager | waiter | accountant | everyone else |
|---|---|---|---|---|---|
| `order.view` | ✓ | ✓ | ✓ | ✓ | — |
| `order.create` · `order.modify` · `order.settle` | ✓ | ✓ | ✓ | — | — |
| `order.void` · `order.discount` | ✓ | ✓ | — | — | — |
| `cash.manage` | ✓ | ✓ | — | — | — |

Six codes are verbatim from the P1 design. **`cash.manage` is an amendment, and it went into
`seed/organization.yaml` before the catalogue** — the design-subset test permits no other order.
`admin` holds none of the seven, as in 0018: configuration and people, not commerce.

New tests name the grants that matter rather than counting them: a waiter settles and cannot void,
discount or close the till; the accountant's whole order path is `order.view`; `admin`, chef, kitchen
staff, store manager and cleaner hold no order or cash permission.

**Two existing tests failed, and were meant to.** `test_auth_service.py` and `test_auth_switch.py`
assert a waiter's resolved permissions as a literal set, with a comment saying widening a waiter's
powers has to be a deliberate edit there — the failure they guard is a resolver that quietly
returns everything. Chunk C is that deliberate widening, so both literals now name the waiter's
five grants, and the comment records what M07 withheld.

**Nothing enforces these yet.** Chunk E's routes are the first to declare them; until then the
permission-matrix suite has nothing new to walk.

---

## Chunk D — the arithmetic, with no database

`app/core/tax.py`, and `calendar_date_of` / `financial_year_of` in `app/core/business_day.py` beside
the rule they differ from. 74 tests, most property-based; every one passed on its first run, which
is recorded rather than celebrated — the properties were written from 0019's CHECKs, so a failure
would have meant the schema and the arithmetic disagreed.

**Decisions made while writing it:**

- **CGST and SGST are each rounded on the line.** ₹101 at 5% carries ₹5.06, a paisa over the exact
  ₹5.05, and both halves agree. Halving a total leaves an odd paisa and fails 0019's CHECK.
- **Half-up to the paisa**, the invoice convention. **Rounding the payable to the rupee is off by
  default**: R12 says it is practice, not law, and the Jaipur bill did not round.
- **Apportionment works in whole paise**, integer arithmetic, so no share drifts through decimal
  precision; ties go to the earlier line, so a bill always divides the same way.
- **A flat discount larger than its base is refused, not clamped.**
- **Credit notes are `CN/2026-27/00001`**: sixteen characters exactly. The spec left the format
  open. The 100,000th in a year is refused rather than issued a number the law does not allow.
- **An unregistered restaurant's bill is a `bill_of_supply` row**, carrying no tax and needing no
  GSTIN, printed without the composition heading.
- The spec named `tax.split_line()`; it is `tax_line()`, returning every figure `order_line` stores.

**Not yet exercised:** `price_bill` has no caller until chunk E's reprice.

---

## Chunk E1 — an order from the first dish to the bill

Chunk E split in two, because discounts, charges and splitting are each a rule with its own
failure modes, and one commit carrying all of them would be reviewed as one blur. E1: repository,
service, schemas and routes for orders; the table-status transition endpoint; the floor plan screen
moved onto it. 29 endpoint tests; the generic suites now probe every order route with a victim
order and line.

**Decisions, and deviations from the spec's endpoint table:**

- **Taking a dish off is `POST .../lines/{line_id}/remove`, not DELETE.** What it does depends on
  the kitchen — an unsent line is deleted, a sent one is cancelled with a reason and an audit row —
  and it needs a body carrying the version. A required query parameter would also have 422'd the
  generic suites' probes before they reached the tenant check.
- **A price sent by the client is refused with a 422**, which is stronger than the spec's "ignored":
  `extra="forbid"` names the field, and a client that sends a price believes it.
- **`order_line.tax_inclusive` was added by amending 0019**, committed in `142105f` but never applied
  outside throwaway test databases. A reprice has to know whether a line's price already contains its
  tax, and the rate row may have changed since. CLAUDE.md forbids editing a migration applied on
  staging; this one has not been.
- **Every change reprices the whole order** through `app/core/tax.py`, flushing and re-reading
  first, and always moves the version — even when no figure changes — because a change the version
  does not record is one the next stale screen overwrites.
- **The order row is locked for the length of a change** and the version checked after the lock.
  Status is checked before version: "this order is cancelled" helps a waiter more than "reload".
- **Order numbers restart each business day**, allocated under an advisory lock (namespace 70_001).
- **Opening a dine-in order marks its tables occupied; cancelling frees a table** only when no other
  live order sits there. Settlement's table handling is chunk G's.
- **`served_at` is overwritten on each serve** (Section 14's time of supply is when the supply
  completes); **`bill_requested_at` keeps the first request** (bill-to-settle is measured from when
  the customer first asked).
- **Audit rows:** a sent line cancelled, and an order cancelled — with how much had gone to the
  kitchen, which is the walk-out signal. Adding or removing an unsent line is not audited; the order
  is its own record. **INFO business events:** `order.opened`, `order.sent`, `order.cancelled`.
- **Table status:** `status` left `TableUpdateRequest`, so a PATCH carrying it is a 422, and
  `POST /setup/tables/{table_id}/status` refuses `free` or `out_of_service` under a live order,
  naming the order. M02's manual step A8 still reads correctly — the control on screen is the same.

---

## Chunk E2 — discounts, charges, and splitting a bill by items

18 more endpoint tests (47 in the file); the generic suites probe the new routes with a victim
discount and charge. Every test passed on its first run. That is recorded rather than celebrated: a
first-run green on money code deserves suspicion, which is why every expected figure in these tests
was worked by hand before the run rather than copied from its output.

**Decisions:**

- **The authoriser is the actor.** `OrderDiscountRequest` has no `authorised_by` field to fill in
  with somebody else's name. Adding and removing a discount both write an audit row: a comp added
  and quietly removed after the bill was shown is the other half of the story.
- **A percentage or comp is recomputed on every reprice while the order is live; a flat discount
  keeps its amount.** 10% of a bill that grows by a dessert is 10% of the new bill.
- **Refused, not clamped, in two places.** Adding a discount larger than what it comes off is a 422.
  A later change that would leave an existing discount larger than the bill — taking the dal off
  under a ₹400 discount on a ₹350 remainder — is a 409, and the whole change rolls back.
- **A discount on a dish taken off the bill takes nothing off** (amount ₹0), and stays as a record.
- **Service charge:** refused while the restaurant has no rate (409), once per order, computed from
  the bill after discounts at the restaurant's rate, untaxed unless a tax group is named, optional
  and removable. Typing an amount for one is a 422. A charge may not use a `non_gst` tax group.
- **Split returns the new order (201)**; the original's version moves, so the screen re-reads it.
  The new order's status follows its dishes (sent if any is in the kitchen, served if any was
  served), line-level discounts move with their dishes, order-level discounts and charges stay, and
  splitting off every dish is a 409. Audited as `order.split`.
- **Discounts and charges come off by `POST .../remove`**, for the reason lines do: the request
  carries the version. The spec's table had DELETE for charges.

---

## PR 1 gate — green on the second run, and the first run found a real defect

**First run: 918 passed, 1 failed.** `test_setup_endpoints.py::TestThemeSettings::
test_a_window_that_ends_before_it_starts_is_refused` got a 401 on the request immediately after a
successful login. The two log lines ran backwards in time — login at 02:39:48.515, the refused
request at 02:39:47.096 — so the machine's clock was stepped back about 1.4 s mid-run. Access tokens
carry `iat: now`, and PyJWT refuses a future `iat` with no leeway. Re-run alone, the test passed.

It was not a flaky test to retry. The same step happens in production whenever NTP adjusts a clock
or two instances disagree by a second, and it signs a person out immediately after signing in. Fixed
under the bug rule — regression test first, red output in the commit body — by turning off the `iat`
check only (`65e0418`). A leeway was rejected because PyJWT applies it to `exp` too, and expiry stays
exact to the second.

**Second run: `make check` exit 0.** Backend 920 passed, coverage 97.12%; vitest 213 passed;
`audit_docs` and `audit_guardrails` 0 issues; `pip-audit` no known vulnerabilities.

---

## Chunk F — a duplicate is money, so the database decides what counts as one

**The claim is one statement in the effect's own transaction:** `INSERT … ON CONFLICT DO NOTHING` on
`(restaurant_id, key)`. A second request with the same key waits on the unique index until the first
transaction ends, then finds a finished request and replays its stored response. A first attempt that
fails rolls its claim back with everything else, so the honest retry runs again — **an error is never
stored.** The same key with a different request is a 409. A request is identified by method, path and
exact body bytes; a replayed response carries `Idempotent-Replayed: true`.

**The key check runs inside the handler, after authorisation, never as a dependency.** A dependency
would resolve beside `require_permission` rather than after it, and a missing key could then answer
before a missing permission.

**On the client the key is made once per submission and renewed on success** — not per tap (two taps
on a stalled connection are one delivery) and not per request (a retry would carry a new key). The
wrapper refuses to send a listed endpoint without one. `newKey` falls back to `getRandomValues`
because `crypto.randomUUID` does not exist in an insecure context, which a tablet reaching a
development server by LAN address is.

**Retrofitted onto M06 receiving**, closing the backlog row M06's own review opened. The existing
suites adapted rather than being weakened: 19 delivery posts in the procurement tests and the
query-count test now send a key, and the generic suites send a fresh key with every probe so an
idempotent route still reaches the check under test. The race is tested on real transactions
(`fresh_database`): two taps with one key book one delivery and replay once.

**Recorded, not built:** ADR 0010 says expired keys are swept nightly. Expiry is honoured — an expired
key can be claimed again — but no job deletes old rows; a backlog row carries the trigger. ADR 0010
gains a refinement note: the wrapper refuses a keyless request rather than inventing a key.

Green before commit: backend 65 passed (idempotency, procurement endpoints, query counts, generic
suites); frontend 23 passed (wrapper, key hook, goods receipt); ruff, format and mypy over 142 files;
`tsc` and eslint; both audits.

---

## Chunk G — settling is one transaction, and its order is the design

`POST /orders/{id}/settle` (`order.settle`, idempotent) and `GET /invoices/{id}`. The service's
docstring is the specification; the sequence is:

1. **Lock and check first.** Version, status, and the restaurant's ability to issue the document its
   scheme requires. A regular restaurant with no GSTIN cannot issue a tax invoice, so it is refused
   before anything is written; a composition restaurant issues a bill of supply with no tax.
2. **Re-freeze tax from Section 14's date**, the median of served, invoiced and the earliest payment,
   and reprice every line and charge while the order is still live, because migration 0019 refuses
   the write one statement after settlement.
3. **Freeze the plate cost** from today's recipe and unit costs, with the costing snapshot loaded
   once for the whole bill.
4. **Post theoretical consumption**: a dish recipe's direct components plus each modifier recipe's,
   times quantity, summed per stock item. A preparation is consumed as itself, not as the onions it
   was made from. Settlement is never refused for want of stock (M05 decision 2).
5. **The payments must cover the re-frozen total exactly.** A payment's `paid_at` may not precede
   the order or run more than two minutes ahead of the server.
6. **Number the invoice under an advisory lock** (namespace 80_001, series per financial year),
   snapshot the restaurant's identity onto it, and write the payments.
7. **Settle the order last**, send its tables to cleaning, and audit.

**Proven on real transactions:** five bills settling at once take five consecutive numbers, and two
devices settling one order charge it once. A failure injected after consumption leaves no movement,
invoice or payment behind. The Jaipur bill from the owner's research settles to the rupee as printed.

Green before commit: backend 148 passed (settlement, orders endpoints and schema, idempotency,
generic suites); ruff, format and mypy over 144 files; `tsc`, eslint and the wrapper's tests; both
audits.

---

## Chunk H — nothing settled is edited; everything after is a new document

`POST /invoices/{id}/cancel` and `POST /invoices/{id}/credit-notes` (both `order.void`; the credit
note is idempotent), and `GET /credit-notes/{id}`.

**Cancelling an invoice is for one issued in error**: on its business day of issue, and only while
nothing has been credited against it. It keeps its number, is reported as cancelled, and voids its
order. **Cancellation moves no money and no stock.** It withdraws a document raised against the
wrong table, and the bill is raised again where it belonged. Money going back is always a credit
note with a refund, the only path that has to carry a reason and a name.

**A credit note reduces an invoice by whole dishes** (CGST Act s.34; Rule 53), in its own series
(`CN/2026-27/00001`, advisory lock 90_001). Each line carries its share of the original line's
taxable value and tax, with CGST and SGST kept equal. A dish cannot be credited more times than it
was billed across every note, and **the note that credits a dish's last unit takes the exact
remainder**, so crediting three portions one at a time cannot drift a paisa from the bill.

**A refund is a negative payment naming its credit note.** Migration 0019 refuses one without a note,
and the service refuses one larger than the note or on account. A refund posts to the till open at
the time. **Neither path reverses stock:** a dish sent back was cooked, and binning it is wastage.

Green before commit: backend 97 passed (reversals, settlement, orders endpoints, generic suites); ruff, format and mypy over 146 files; `tsc` and eslint; both audits.

---

## Chunk I — the till knows what it should hold, and keeps the shortfall

`GET`/`POST /cash/sessions`, `GET /cash/sessions/{id}`, `POST …/close`, and `POST …/payouts` and
`…/adjustments`, both idempotent. All sit behind `cash.manage`. Opening and closing need no key: a
second open meets the one-open-till index, and a second close finds the till already closed.

**Expected cash is derived, never stored.** It is the opening float, plus every cash payment posted
to the till, minus the payouts from it. A refund is a negative cash payment and posts to the till
open when it is given. Every one of those rows is append-only, so a closed till's figure cannot move
afterwards. The acceptance-criterion-16 test gives a refund in the next shift and asserts the
counted till is untouched.

**The variance is frozen at close and never corrected away.** Cash found next morning is an
adjustment: a new row with a reason, recorded by somebody other than the person who closed the till.
That is M05's count-approval rule, held the same way. The adjusted variance is reported beside the
original, never instead of it.

**A payout is a row** with an amount, a reason and a name. It cannot exceed what the till should
hold. A waiter takes cash at the table and never touches the till. A denomination counted twice is
refused. Only one till is open at a time, held by migration 0019's partial unique index.

Green before commit: backend 70 passed (cash, reversals, settlement, generic suites, query counts);
ruff, format and mypy over 150 files; `tsc` and eslint; both audits.

---

## PR 2 gate — the money chunks, F to I

Full `make check` over the tree at `706e3e1`. Exit code 0. Backend: 972 passed in 20 min, coverage 97.10% against the 95% floor. Frontend: 219 tests in 26 files passed. `tsc`, eslint (zero warnings), ruff and mypy were clean, and `audit_docs` and `audit_guardrails` reported 0 issues. The only yellow output is the market-rate validator flagging stale prices in `library/`; it predates M07 and is not a gate failure.

---

## Chunk J — the waiter's three screens

`GET /floor` (`order.view`) returns areas, tables, and each table's live orders in one call, and its
query count does not grow with the number of tables. The three screens render on the waiter surface.
`WaiterSurface` sets 48 px targets while one is mounted and restores the previous surface when it
leaves.

- **Table map.** Every status is a word, not only a colour. A free table opens a dine-in order in one
  tap and goes straight to order taking; an occupied one links to its order.
- **Order taking.**
  - A dish with nothing to choose is one tap. A dish with choices opens a bottom sheet, and its Add
    button stays disabled until every required question is answered.
  - An unsent line changes count with the quantity stepper, or comes off in one tap. A sent line asks
    why first.
  - Send is bottom-right, and no request carries a price.
- **Bill.**
  - It is provisional until settled, and says so.
  - One payment sends the bill's own total. A split payment sends the amounts as typed and never adds
    them up: the server's exact-cover check answers.
  - Split by dishes moves the ticked lines to a new order before settlement.
  - Settle carries one idempotency key per bill.

Every write puts the server's returned order straight into the cache, and a stale version re-reads
the order rather than overwriting it. That falls short of the fully optimistic screen the
conventions ask for; the backlog row is in chunk L.

Green before commit: backend 76 passed (floor, orders endpoints, generic suites, query counts); frontend 29 tests in 7 files, including AppShell and HomeScreen; ruff, format and mypy over 151 files; `tsc`, eslint over the whole app with zero warnings, and prettier; both audits.

---

## Chunk K — after the bill, and the till

**The order detail now names its invoice** (`invoice_id`), so the manager's screens can get from a
bill to its legal document. It is looked up only for a settled or voided order, so reading a live
order during service costs no extra statement.

Three manager screens:

- **Bills.** Today's settled and cancelled bills, by the restaurant's business day rather than the
  browser's. A test sets the clock to 01:30 IST and still gets the previous evening. A full page
  offers the next one rather than stopping silently.
- **Invoice.** The tax split and the payments, and the two documents that may follow.
  - **A credit note:** dishes are chosen with the quantity stepper, from none up to what was billed.
    It takes a reason and an optional refund, typed by whoever hands the money over.
  - **Cancelling:** behind a second tap, and it asks what the error was.
  - Nothing on this screen sends a price. The note's figures are the server's.
- **Cash.**
  - Open with a float. Payouts and adjustments each carry an idempotency key.
  - Close with a count per denomination. **The count is blind:** while a till is open the screen shows
    the float and the payouts, never what the till should hold. Expected cash and the variance
    appear only after the count.
  - "Short" or "over" is read from the sign of the server's figure.
  - An adjusted till keeps its original variance beside the adjusted one.

The waiter patterns M07 owed `docs/ui/design-system.md` are now written into §4: table map cell,
order line row, money display and quantity stepper.

Green before commit: backend 90 passed (settlement, orders endpoints, generic suites, query counts); frontend 35 passed in 6 files, re-run after splitting the invoice test's fetch mock into a route table for eslint's complexity limit; ruff, format and mypy over 151 files; `tsc`; eslint over the whole app with zero warnings; prettier; both audits.

---

## Chunk L — the seed, the rules, and the script

- **Seed.** `app/seed/orders.py` builds its demo state through the real services, so the seeded bill
  is priced, taxed, numbered and consumed exactly as a real one would be. It creates:
  - an open order and a sent order;
  - a settled bill paid in cash with the paise by UPI;
  - a naan credited back with a UPI refund;
  - a till closed **₹50 short**.

  `tests/test_seed_orders.py` asserts each of these, and that seeding twice creates nothing new.
- **Compliance.** `docs/compliance-rules.md` §A7 adds nine rules, each with its instrument, its
  status and the test that enforces it. §D gains two gaps: no rendered invoice, and no report of
  documents issued.
- **Manual script.** `docs/manual-tests/M07-orders.md`. The rupee figures are for checking by hand.
- **Backlog.** Six rows. Among them: no screen for discounts or comps, the blind count as a decision
  for the owner, and INFO business events missing from M03–M06.
- **`docs/modules.md`.** The M07 endpoint list now matches what was built: there is no `/void` and
  no `/payments`, because payments travel inside settle.

**Review.** An independent second reader went through the whole M07 diff, and the uncommitted seeder, and reported six findings. It found nothing in tenant isolation, immutability, idempotency, permissions or the frontend. The six findings: cash posting into a till that closed mid-settle; cash taken with no till open; a cancelled invoice's cash double-counted in the till; a comp growing past what was authorised; credit-note rounding drift on many one-portion notes; and a refund larger than money received. Each fix gets its regression test written first, in the commit after this one, and cash with no till open goes to the owner as a backlog row. My own review before it found and fixed the closed-till list stopping silently at one page, and a screen test asserting an ambiguous word.

Green before commit: seed tests 33 passed (4 new for the orders seeder, plus seed, seed CLI and procurement seed), re-run 4 passed after reading model money through `Decimal(str(...))` for mypy; ruff, format and mypy over 153 files; both audits.

---

## Notes for whoever picks this up

- **Use `backend/.venv/Scripts/python -m pytest`, never bare `python`.** Bare `python` on this
  machine is Anaconda, whose `argon2` is too old for `app.core.security`; conftest fails to import
  and nothing runs.
- **Very long inline shell commands fail here** (`ENAMETOOLONG`, or bash losing a heredoc). Write a
  script to the scratchpad and run it.

- **Run pytest from `backend/`, not the repo root** — Alembic resolves `script_location` relatively.
- **Two bill images sit untracked at the repository root** (`restaurant_bill.png`,
  `restuarant_bill_latest.png`), supplied by the owner as research. They carry a real restaurant's
  phone number and tax registration. **Never stage them** — commit by explicit path. G-16's check only
  covers tracked files, so it will not stop a careless `git add -A`.
