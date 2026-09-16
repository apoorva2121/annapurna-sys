# M05 · Inventory Ledger — Manual Test

**Module:** M05 · **Built:** 2026-09-12 · **Gate:** `make check` clean.

Run `make seed` first, then `make dev`.

**This is the module the rest of the product stands on.** M03 said what the restaurant sells, M04
said what a dish should cost. M05 is the ledger that makes theoretical and actual comparable — and
the variance between them is the thing this product is for. M07's settlement, M09's waste and
M13's headline report all write to or read from the table this module creates.

---

## What I already ran, and what still wants you

| Section | State |
|---|---|
| **A · the ledger adds up** | Verified — 1,000 randomised operations, and the property test was re-run with the shortfall path deliberately broken to confirm it goes red. **A3 wants your calculator** |
| **B · negatives** | Verified against the API and the screen. **B2 is the one to judge yourself**: is the banner's wording something a manager would act on? |
| **C · FEFO** | Verified, including the `NULLS LAST` case that is silently wrong without it |
| **D · counts** | Verified, including the refusals. **D4 is yours** — it is the control an insider would attack |
| **E · who may do what** | Verified. **E2 is the one to do by hand**: sign in as the chef |
| **F · exploratory** | Not run. Yours |

Short of time? Do **A3, B2, D4** and the F charter. Ten minutes.

---

## A · The ledger adds up

| # | Step | Expect |
|---|---|---|
| A1 | Sign in as **owner**, open **Stock on hand** (`/stock/on-hand`) | A table of items with quantities and values |
| A2 | Pick any item and press **History** | Every movement behind that figure: its date, what kind it was, and the signed change |
| A3 | Add up the **Change** column by hand for one item | It equals the **On hand** figure exactly. Not approximately — this is a sum, and there is no stored balance anywhere for it to disagree with |

**A3 is the point of the whole module.** On-hand is never stored; it is
`SUM(stock_movement.quantity_delta)` computed at read time. A test asserts it over a thousand random
operations; doing it once by hand on real rows is what makes you believe the test.

---

## B · Negatives — the behaviour to judge, not just check

The seed plants one deliberately, so this section has something to find without you creating it.

| # | Step | Expect |
|---|---|---|
| B1 | On **Stock on hand**, look at the top of the page | A banner: *"1 item has been used without a recorded delivery"* |
| B2 | **Read the banner properly** | It explains what happened and offers two ways out: record the missing delivery, or count the shelf and let the count correct it |
| B3 | Find the negative row in the table | It carries the words **"No delivery recorded"** beside the figure, not only a colour |

**B2 is yours, and it is a judgement rather than a check.** A negative position is not a bug — it
means stock is being consumed that nobody recorded receiving, which for a restaurant that has never
kept records is week one, not an edge case. The system deliberately **never refuses a consumption
for insufficient stock**: doing so would stop a restaurant taking money because the storeroom
paperwork was behind. So the question is whether this banner reads as *information a manager can
act on*, or as an error they will learn to scroll past. If it reads as an error, it is wrong, and
say so.

---

## C · FEFO — first expired, first out

| # | Step | Expect |
|---|---|---|
| C1 | **Record a delivery** (`/stock/receive`) twice for one item: 1 kg expiring in 30 days, then 1 kg expiring in 2 days | Both appear; on-hand shows 2 kg |
| C2 | Consume 500 g | The **2-day batch** is drawn down, not the 30-day one |
| C3 | Look at **Expiring soon** | The near-dated batch appears with 500 g left |

Two ways this is silently wrong if unguarded, both tested: a batch with **no** expiry date must be
used *after* every dated one (Postgres sorts NULLs first by default, which is the exact opposite of
FEFO and leaves the perishable batch to rot), and an already-empty batch must not be offered just
because it expires soonest.

---

## D · Stock counts

| # | Step | Expect |
|---|---|---|
| D1 | Open **Stock count** (`/stock/count`), press **Start a count**, type quantities slightly below what the book says, save, and submit | The count is **submitted**, and **on-hand has not moved** |
| D2 | Look at the variance figures | Each line shows the gap **in rupees**, negative where the shelf holds less than the book |
| D3 | Approve the count **as the person who counted it** | **Refused**, with a sentence saying the approver must be somebody else |
| D4 | Approve as a different person with `stock.count` | On-hand now matches what was counted, and the correction appears in **History** as a **Correction** with the count's date in its note |

**D3 is the control an insider would attack, and D4 is why it matters.** A count is the one document
that can make a shortfall official. If the person who walks the shelves can also accept the result,
the control is decorative. It is refused in the service *and* by a constraint in the database, so it
holds even for a path that forgets to ask — and it is not waived for the owner.

**D4's second half matters too:** the correction stays visible as its own movement type forever. A
variance report that hid its adjustments would let somebody declare a shortfall away.

---

## E · Who may do what

| # | Step | Expect |
|---|---|---|
| E1 | Sign in as **kitchen staff** | **Stock on hand** is in the list. Nothing that changes stock is |
| E2 | Sign in as the **chef** and try to record a delivery | Refused. The chef may **produce** a batch but may not **receive** one |
| E3 | Sign in as a **waiter** | The storeroom is not there at all |

**E2 is the grant worth understanding.** A kitchen turns ingredients into gravy; it does not sign
for the sack at the door. Separating `stock.produce` from `stock.receive` means a cook cannot
quietly book in stock that never arrived and then cook it away. The split comes from
`seed/organization.yaml`'s P1 design, not from convenience — an earlier draft of this module
invented a coarser permission and the catalogue test refused it.

---

## F · Exploratory charter

**Thirty minutes. Try to make the ledger lie.**

Specific things worth attacking, because they are the ones that would matter:

- Consume more than exists, repeatedly, then record a delivery. Does on-hand come back to the right
  number, or has the shortfall been double-counted?
- Open two counts over the same item at once and approve both. Does the correction post twice?
- Produce a preparation with none of its ingredients in stock. It should succeed and drive every
  input negative — a kitchen does not stop cooking because the storeroom is behind.
- Record a delivery, then look for any way at all to edit or delete a movement. There should be
  none, anywhere: the database itself refuses `UPDATE` and `DELETE` on that table.
- Check a figure after midnight but before 05:00. It should book to the **previous** business day.

---

## Not built yet, deliberately

These are named so their absence reads as a decision rather than an oversight:

- **Purchase orders and supplier invoices** — M06 owns those. A receipt here is an ad-hoc
  "we bought this", which is how a real market purchase arrives anyway.
- **Order-driven consumption** — M07 posts it. The service method exists and is tested; no order
  exists yet to call it.

---

## Result

*(fill in)*

| | |
|---|---|
| Run on | |
| Sections passed | |
| Failures | |
| Notes | |
