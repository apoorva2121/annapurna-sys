# Manual Tests

One file per module: `MXX-<module>.md`. I write it when the module is code-complete and its
automated tests pass. You run it on staging. The module is not done until every step passes.

Why this exists and what your time is for: `docs/testing-strategy.md` Part 2.

## How to run one

1. Open the staging URL. Use the logins listed under **Preconditions** — they are seeded, and the
   passwords are in the file.
2. Work top to bottom. Do not skip, do not improvise on the first pass.
3. Tick Pass or Fail per step.
4. On a failure: note **step number**, **what you expected**, **what you saw**. Screenshot if you can.
   If an error shows a `Reference: 01J7X…` code, include it — it finds the exact request in the logs.
5. A failed step ends that section. Move to the next section rather than working around it.
6. Finish with the **exploratory charter** — ten real minutes.
7. Send me the failures. I fix, and you re-run **only the failed sections**, not the whole file.

## The format

Every file has these sections, in this order:

| Section | Purpose |
|---|---|
| **Preconditions** | Logins, URL, seed state. Everything needed, nothing assumed. |
| **A · Happy path** | The thing works when used correctly |
| **B · Validation** | It refuses bad input clearly |
| **C · Permissions** | Each role sees and does only what it should |
| **D · Security probes** | You personally verify the controls, in a real browser |
| **E · Usability** | It is actually usable by someone in a hurry |
| **F · Exploratory charter** | 10 unscripted minutes with a stated goal |

## Writing rules I hold myself to

- **One action per step.** "Tap Settle" — not "settle the order and check the total".
- **Concrete expected results.** "Total reads ₹1,240.00", never "the total is correct". If you have
  to judge correctness yourself, I wrote the step badly.
- **No jargon.** Not "assert the KOT transitions to ready" but "the ticket turns green and moves to
  the right-hand column".
- **Exact data.** "Order 2× Butter Chicken (Full)" — so the expected rupee figures are checkable.
- **If a step needs interpretation, that is my bug.** Tell me and I will rewrite it.

## Files

- `M00-template.md` — the blank template
- `M01-identity.md` — worked example (written before the module, so you can see the shape now)
- `security-checklist.md` — the pre-production pass, run once, before real money touches it
