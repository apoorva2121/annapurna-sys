# M09 · Waste — Module Spec

**Depends on** M05 (the stock ledger) and, for one optional link, M08.
**Status** — spec written 2026-09-16, before any code, per `docs/sdlc.md` step 1.
Build log: `docs/plan/m09-build-log.md`.

Tables: `wastage_reason`, `wastage_event`.
Endpoints: CRUD `/wastage/reasons`; `POST /wastage`; `GET /wastage`; `GET /wastage/summary`.
Screens: log waste in under ten seconds; the waste summary.

---

## Why this module is small and still matters

M05 built the hard part. `InventoryService.consume` already walks FEFO, charges each batch at its
own frozen cost, records a shortfall rather than refusing, and writes an append-only movement. This
module adds a reason, a person, and a screen fast enough to be used — and that last one is the whole
module, because **`docs/waste-model.md` is blunt about it: if logging waste is slow, it does not get
logged, and the module is fiction.**

So the acceptance criterion that matters is not a number reconciling. It is: *ten seconds, on a
phone, with one hand, in a kitchen.* Everything below serves that.

---

## Research — what binds this module, checked 2026-09-16

**Nothing in `docs/compliance-rules.md` binds waste.** It touches no menu text, no restaurant
identity, no tax, no price a guest pays and no customer data. Checked rather than assumed, as
CLAUDE.md requires from M07 onwards; the finding is "no rule applies" and that is a result.

**`docs/waste-model.md` is the spec behind the spec**, and three of its statements are load-bearing:

1. **Four stages, never lumped** — receiving, storage, prep, service. "Lumping them produces a
   number nobody can act on." `wastage_reason.stage` carries this, which is why reasons are a table
   rather than an enum: a row carries policy.
2. **`staff_meal` and `complimentary` are not waste.** Indian restaurants feed staff, always;
   untracked it looks like theft and poisons every variance number. Both already exist as movement
   types from M05 and stay out of this module's reports.
3. **Never ask the person logging for the cost, and show the rupee value only afterwards.** Showing
   it first suppresses honest reporting. This is a UI rule with a schema consequence:
   `cost_value` is computed and written by the server, and the API has no field to send it in.

**What M05 already provides, and this module must not rebuild:** FEFO, per-batch cost, negative
stock, the shortfall placeholder batch, and `stock_movement.ref_type`, which already lists
`wastage_event` in `docs/schema.md` §5 — so **no migration to `stock_movement` is needed**.

---

## The six decisions that matter

### 1 · The event and its movement are one transaction, or neither happens

`docs/schema.md` §8: "Every `wastage_event` writes a paired `stock_movement` of type `wastage` in
the same transaction. Never one without the other."

Both directions are bad and they are bad differently. An event with no movement is waste that
everybody can see in a report and that never left the stock book — the variance number silently
wrong, in the direction that hides theft. A movement with no event is stock gone with no reason, no
person and no stage, which is exactly the "mystery shrinkage" this product exists to eliminate.

So `WastageService.log` writes the event, calls `InventoryService.consume` with
`movement_type=wastage`, `ref_type="wastage_event"`, `ref_id=<the event>`, and writes the returned
cost back onto the event — all inside one transaction, with a test that kills it mid-way and asserts
neither row survives.

### 2 · The cost is the product's answer, and the API cannot be told otherwise

`cost_value` has no field in the request schema. Not "ignored if sent" — **absent**, so a client
that sends one gets a 422 from `extra="forbid"` rather than having it silently dropped. Same
reasoning as M07's prices (`docs/security.md` A04), and one more: a person logging waste in a
kitchen does not know what a kilo of paneer cost on the day it was received, and asking would either
get a guess or stop them logging.

The value comes from `ConsumptionResult.total_value` — the sum of each batch's own frozen cost, not
today's price and not an average. A kilo wasted from Monday's expensive delivery costs what Monday
cost.

### 3 · The rupee value is shown *after*, never before

`docs/waste-model.md`: "Showing the rupee value *after* logging is good — it teaches. Showing it
before suppresses honest reporting."

The logging screen therefore shows no cost at any point before submit, and the response shows it
plainly afterwards. The same rule as the blind cash count in M07 and the blind goods-receipt weight
in M06, and it is worth noticing that this is the third occurrence: **a "blind entry" pattern is now
earned** if a fourth appears, but three screens sharing a principle is not yet an abstraction.

### 4 · A reason is a row, and it carries policy

`wastage_reason` is a table rather than an enum because its rows carry `stage`, `requires_photo` and
`requires_approval` — policy a restaurant sets, not a constant this product knows. A tandoor
station's "burnt" and a store's "expired" want different handling.

**`requires_approval` is enforced here. `requires_photo` is stored and deliberately not
enforced, and that is written down rather than quietly skipped.**

`seed/operations.yaml` already sets `requires_photo: true` on six of its twelve reasons — short
delivery, quality rejection, expired, spoilage, storage failure and customer return — and it is
right to: those are the six where a photograph is what makes the reason code honest
(`docs/waste-model.md`). But photographs live in `attachment` (`docs/schema.md` §10), which is
**M11's table**, and building half of it here to satisfy one column would be an abstraction two
modules ahead of its second occurrence.

Enforcing the flag without somewhere to put a photograph would make six reasons unusable, and the
failure mode is a cook standing in front of a bin of spoiled paneer with no way to record it. That
is worse than a flag that waits.

So: the column is stored, the API and the screen do not require a photograph, and this is tagged
`[planned: M11]` in `docs/security.md`'s sense — **G-7: a control that is designed but not
implemented is never presented as present.** A test pins the current behaviour, so the day
attachments land it fails and says what to turn on, rather than the flag being discovered years
later doing nothing.

### 5 · A remake is not automatically waste, and neither is a return

M08 deliberately does not book waste when a dish is sent back: it may be reheated rather than
binned, and a system that quietly books waste on the kitchen's behalf teaches people to stop
remaking food. `wastage_event.order_line_id` is the link, and it is **offered on the logging screen
and never filled in by the server**.

`docs/waste-model.md` also calls a returned dish "simultaneously a waste event **and** a customer
experience signal. One record, two modules." The record is this one; M10 reads it.

### 6 · The summary answers the question the report in `docs/waste-model.md` asks

Not "total waste this week" — a number nobody can act on. `GET /wastage/summary` groups by
**stage**, then by reason, with the rupee value and the share of the total, over a business-date
range. That is the shape of the one report this whole model exists for:

> ₹14,800 prep over-production (47%) — mostly makhani gravy, Tue/Wed

M09 delivers stage, reason and value. The "mostly makhani gravy, Tue/Wed" half is M13's, and saying
so here stops it being attempted twice.

---

## Not in scope

- **Photographs.** Decision 4 — and note this is not "not in scope" in the usual sense: the
  `requires_photo` column ships populated and unenforced, tagged for M11, with a test holding the
  gap visible.
- The daily prep sheet (`docs/waste-model.md` §3). It is called the highest-ROI feature in the
  product and it is **not this module** — it is a scheduling and production surface, and M05's
  external review already gave it a "prep-sheet thin slice (give it a module number)" row.
- Near-expiry actions. M05 has `expiring`; turning it into an action is M18's.
- Supplier short-delivery variance. M06 already captures it; the waste *report* joins it in M13.
- Approval workflow beyond a single approver field. A queue is M11's.

---

## Deliverables

### Migrations

- **0033 · `wastage_reason`, `wastage_event`** — `docs/schema.md` §8 as written, plus the composite
  `(id, restaurant_id)` foreign keys every tenant-owned table here uses, and a CHECK that
  `cost_value >= 0` and `quantity > 0`.
- **0034 · `wastage.log` / `wastage.approve`** — both already in `seed/organization.yaml`, so no
  design amendment, like M08.

### Backend

- `app/models/waste.py`, `app/repositories/waste.py`, `app/services/waste.py`,
  `app/api/v1/staff/wastage.py`, `app/schemas/waste.py`.

### Endpoints

| Method | Path | Permission |
|---|---|---|
| `GET` | `/staff/wastage/reasons` | `stock.view` |
| `POST` | `/staff/wastage/reasons` | `restaurant.configure` |
| `PATCH` | `/staff/wastage/reasons/{id}` | `restaurant.configure` |
| `POST` | `/staff/wastage` | `wastage.log` |
| `GET` | `/staff/wastage` | `stock.view` |
| `GET` | `/staff/wastage/summary` | `stock.view` |
| `POST` | `/staff/wastage/{id}/approve` | `wastage.approve` |

`POST /staff/wastage` is **idempotent** (ADR 0010): it writes the stock ledger, so it joins
`IDEMPOTENT_ENDPOINTS` on both sides. A double-tapped Log on a phone in a kitchen is the exact
situation the key exists for.

### Frontend

- `staff/screens/WasteScreen.tsx` — the ten-second flow: item → preset quantity (¼, ½, 1, 2) →
  reason → done. Waiter surface, 48px targets, one hand.
- `staff/screens/WasteSummaryScreen.tsx` — by stage, then reason, with shares.
- A **mechanical test on the logging screen** in the shape of `kdsReadability.test.ts`: no money
  rendered before submit, preset buttons present, and no free-text quantity as the primary control.

---

## Threat question — *what would an insider do with this?*

**Log theft as waste.** This is the module's central risk and it cannot be prevented, only made
visible and expensive. The controls are: every event names a person and a time; `requires_approval`
on the expensive reasons; and — the real one — the waste report is *by reason and stage*, so a
person quietly logging two kilos of paneer a week shows up as a pattern in a report a manager reads
anyway, rather than as an anomaly somebody has to go looking for.

**Log waste against the wrong batch to move cost.** Not possible: the batch is chosen by FEFO in
M05, not by the client. The request names an item and a quantity.

**Delete an inconvenient event.** There is no delete. `stock_movement` is append-only by trigger and
a correction is a new `adjustment` movement, which M05 built precisely so corrections stay visible.

**Suppress reporting by making it slow.** The ten-second rule is a security control as much as a
usability one: a form nobody uses produces a variance number nobody can trust, and an untrustworthy
variance number is cover for everything above.

---

## Acceptance criteria

1. An event and its movement are written together; killing the transaction leaves neither.
2. `cost_value` matches the batch costs FEFO actually consumed at that moment, to the paisa.
3. The API refuses a request carrying a cost.
4. Logging waste for an item with no stock records the shortfall rather than refusing (M05's rule).
5. A reason with `requires_approval` produces an event that is not approved, and approving it needs
   `wastage.approve`.
6. `staff_meal` and `complimentary` movements never appear in the waste summary.
7. The summary groups by stage and reason over a business-date range, with shares.
8. Tenant isolation over every route, and the design's own grants honoured:
   **a waiter cannot log waste at all** — `seed/organization.yaml` gives `wastage.log` to the chef,
   the kitchen staff, the manager and the store manager, and to nobody on the floor. Checked against
   the file rather than assumed, because assuming it is what broke two tests in M08. The chef and
   the kitchen staff log and cannot approve; the manager and the store manager do both.
9. **Under ten seconds on a phone, hand-timed by the owner.** The only criterion here that no test
   can assert, and the one the module lives or dies by.

---

## Chunks — two PRs

| PR | Chunk | What |
|---|---|---|
| 1 | A | Migration 0033 + models + schema doc check |
| 1 | B | Migration 0034 + permissions |
| 1 | C | Reasons CRUD, seeded reasons per stage |
| 1 | D | `POST /wastage`: the paired write, the cost, idempotency |
| 2 | E | `GET /wastage` and the summary by stage and reason |
| 2 | F | The ten-second screen and the summary screen |
| 2 | G | Seed, review, manual script |

### What the seed plants, and what it deliberately does not

`docs/seed-data.md` plants fourteen signals, and four of them are this module's: makhani gravy
over-produced ~35% every Tue/Wed (1), paneer expiring twice a month (2), staff meals ~₹18k/month
(10) and comps ~₹9k/month (11). **The volume that makes those readable is M15's**, the same line the
orders seeder draws — 120 days of history is a generator, not a seeder.

So M09 plants a handful of events across all four stages, enough that the summary screen opens on
something rather than on a zero, and shaped like the signals so M15 has a pattern to scale rather
than invent. Signals 10 and 11 are `staff_meal` and `complimentary` movements and must **not** appear
in this module's reports at all — which is itself worth a test, because the whole point of separating
them is that they stop poisoning the variance number.

`docs/seed-data.md` rule 3 also asks for "a day the waste log was skipped". That is planted here:
perfectly clean data hides the bugs real data finds, and a summary that assumes every day has a row
is one of them.
