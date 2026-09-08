# Waste Model — where the money actually leaks

Vision doc §14 treats waste as one thing with a reason code. It isn't. Waste happens at four
distinct points, each with a different owner, a different fix and a different size. Lumping them
produces a number nobody can act on.

| Stage | What it is | Typical share | Who fixes it | The lever |
|---|---|---|---|---|
| **Receiving** | Short weight, poor quality accepted, billed for more than delivered | 1–3% of spend | Store manager | Weigh at the gate |
| **Storage** | Expiry, spoilage, poor rotation, bad cold chain | 2–4% | Store manager | FEFO + expiry alerts |
| **Prep** | Over-production of bases; trim loss above standard | **4–8%** | Chef | **Daily prep sheet** |
| **Service** | Wrong orders, remakes, returns, comps, over-portioning | 1–3% | Manager | Accuracy + portion control |

Prep waste is the biggest and the least measured. It is also the only one with a same-day fix.

## 1. Receiving — the cheapest money in the product

Ordered 50 kg. Delivered 47 kg. Invoiced 50 kg. This happens constantly and nobody notices, because
nobody weighs.

Implement: receive **against** the purchase order, capture actual weight and accepted quantity
separately from invoiced quantity, and store the three-way variance (ordered / received / invoiced).
Roll it up per supplier over time.

> Supplier A short-delivered 4.2% across 31 deliveries this quarter — ₹18,400.

That single report has paid for the software. Also captures quality rejections and returns.

## 2. Storage — FEFO and honest expiry

Covered by the batch ledger and FEFO in `docs/domain-model.md`. Two additions worth making:

- **Shelf life is a property of storage conditions, not just the item.** Same tomato, different
  fridge, different life. Per-restaurant override on `ingredient.shelf_life_days`.
- **Near-expiry should generate an action, not just an alert.** "3.2 kg paneer expires in 2 days —
  these four dishes use it; feature Paneer Tikka today." An alert nobody can act on is noise (§25).

## 3. Prep — the daily prep sheet

**This is the highest-ROI feature in the entire product and it is not in the vision document.**

Every morning the chef decides how much of each base to make. Today that decision is made from
memory and habit, and it is wrong in the same direction every day — over-production, because
running out is visibly embarrassing and throwing away is invisible.

The chain, which only works because of ADR 0006:

```
forecast covers → dish-level demand → preparation demand → minus preparation stock on hand
   → PREP SHEET: "Makhani gravy: make 6 L (not your usual 10 L)"
```

At close, log leftover per preparation. That closes the loop:

> Makhani gravy: 10 L made, 6.2 L sold-through, 3.8 L discarded, ₹1,140. Fourth consecutive day.
> Suggested batch: 6.5 L.

Cold start (no history yet): seed from the first two weeks of actual sales, and until then let the
chef enter their own usual batch size — the system's first job is just to *measure* the leftover.
Measurement alone typically cuts prep waste before any forecast exists.

**Yield standards** belong here too. 1 kg raw chicken → ~700 g usable. Store `yield_factor` per
ingredient, alert when actual yield drifts below standard — that drift is either poor quality
supply or poor butchery, and both are worth knowing.

## 4. Service — separating waste from leakage

Every one of these must be its own movement type, never lumped into consumption:

- **`staff_meal`** — Indian restaurants feed staff, always. Untracked, it looks like theft and
  poisons every variance number. Track it, budget it, report it as a cost line, don't moralise it.
- **`complimentary`** — manager comps, NC bills, owner's table. A genuine leakage vector. Every comp
  needs an authoriser and a reason; the monthly comp report by authoriser is uncomfortable and
  necessary.
- **`remake`** — kitchen error. Links to station and shift.
- **`returned`** — customer sent it back. This is simultaneously a waste event **and** a customer
  experience signal. One record, two modules. See `docs/customer-experience.md`.
- **Over-portioning** — surfaces as theoretical-vs-actual variance on a single ingredient across a
  single dish. When Butter Chicken consistently uses 12% more gravy than the recipe, that is a
  portioning problem with a named owner, not a mystery.

## Waste capture must take under ten seconds

If logging waste is slow, it doesn't get logged, and the whole module is fiction. The interface is:
pick item → quantity (with big preset buttons: ¼, ½, 1, 2) → reason → optional photo → done. On the
kitchen tablet, three taps. Photo is optional but strongly nudged, because photos make reason codes
honest.

Never require the person logging waste to know the cost. The system knows. Showing the rupee value
*after* logging is good — it teaches. Showing it before suppresses honest reporting.

## The one report this all exists for

> This week you lost **₹31,200** to waste.
> ₹14,800 prep over-production (47%) — mostly makhani gravy, Tue/Wed
> ₹7,400 expiry (24%) — paneer and cream, both over-ordered on Monday
> ₹5,100 short delivery (16%) — Supplier A, three deliveries
> ₹3,900 service (13%) — remakes at the tandoor station, 8–10 PM
>
> Fix the makhani batch size and you recover ₹9,000/month for zero investment.
