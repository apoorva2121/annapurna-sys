# M17 · Workload Fairness & Recognition — Build Log

Spec: `docs/modules/M17-fairness-spec.md`. Manual script: `docs/manual-tests/M17-fairness.md`.
Design: `docs/workload-fairness.md`. Decisions: ADR 0011.

---

## State

| Chunk | What | State |
|---|---|---|
| A | Five tables, five permissions, migrations 0051-0052, the weight validator | ✅ committed |
| B | Live metrics, the freeze, the dispute that blocks a publish, 26 tests | ✅ committed |
| C | Seven endpoints, three screens, the discipline test | ✅ committed |
| — | Manual pass | **Owner's** |

Built on 2026-09-19, on `feat/m11-communication` after M15.

---

## What this module is, and the line it had to stay on

`docs/workload-fairness.md` opens by naming the risk in the same breath as the goal: **a measurement
system aimed at morale can destroy morale if built carelessly.** A restaurant is a place where the
owner holds far more power than a waiter, and a scoring system handed to that relationship without
guardrails becomes a tool for the stronger party.

So the interesting half of this module is what it refuses to do, and the refusals are in code rather
than in prose:

- a scheme that would pay people to rush is refused **on save**;
- a context metric cannot be given weight **at all**;
- a period with an unanswered dispute **cannot be published**;
- no response schema in the product **has a field that could carry a ranking**;
- `performance.view.own` is granted to every role by a migration that asks the database for the
  roles rather than listing them, because a list is a place to forget somebody.

---

## The eight ethics questions, and where each answer actually lives

The spec answered them in prose. This is where each one ended up in the product, which is the only
place an answer counts.

| # | Question | Where the answer is |
|---|---|---|
| 1 | An employee cannot dispute a score | `PerformanceService.publish` refuses while `unanswered_disputes` is above zero; the employee's own screen is where the dispute is raised |
| 2 | Punitive use is not ruled out | Nothing reads `performance_score` but the three read endpoints, and `PURPOSE` is shown on the person's own screen — a sentence that stops being true is a lie somebody will notice |
| 3 | "Top contributors" leaks the bottom in a small team | `MIN_TEAM_SIZE = 5`, and below it `team()` returns the viewer alone |
| 4 | Attendance can score protected reasons | `_attendance()` divides by rostered days **minus** approved leave, and somebody whose every rostered day was leave scores 1.0 rather than 0 |
| 5 | Attribution is the weakest link | Every metric carries its `count`, and every sentence on the employee's screen names it: a wrong attribution is a wrong *number of things* somebody can point at |
| 6 | Visible is not understandable | The sentences are built on the server; Hindi and Marathi are **not shipped** and are recorded as a limit |
| 7 | The legal basis is unverified | Researched: DPDP §7(i) makes employment purposes a legitimate use. Recorded in `docs/compliance-rules.md` with both caveats |
| 8 | There is no stop rule | Stated in the spec; **not built**, and that is a gap named below rather than a tick |

---

## The finding that shaped the tests

**The freeze test could not use a void, because the database refuses one.**

ADR 0011's example of a later correction is *"a voided order"*, and the obvious test is: publish a
period, void an order inside it, assert the score does not move. A settled order is immutable
(invariant 6, enforced by a trigger), so the test could not perform the correction it wanted to
describe.

That refusal is the same principle one layer down, and the test is better for it. It uses **M12's
attendance correction** instead — a manager fixing a clock-out somebody forgot, which is a real,
supported, audited operation. It halves `hours_worked`, the normalisation denominator, so it would
double every per-hour figure on the screen if the figures were not frozen.

---

## Two decisions taken while building that are not in the spec

**`performance.view.own` is granted by a query, not a list.** The migration inserts it for every
system role by selecting them, rather than naming nine roles in a tuple. A list is a place to forget
somebody, and forgetting somebody here is this feature quietly becoming surveillance for that
person. `tests/test_m17_endpoints.py` asserts the catalogue has no role without it.

**Nobody rating you is not a zero.** The rating metric of somebody with no ratings is zero *value*
with a count of zero, and the screen says "0 people rated their visit" rather than showing a bad
mark. A quiet week is not a bad review, and scoring it as one is how a measurement system loses the
person it is measuring in the first month.

---

## What is not built, named rather than ticked

- **The stop rule.** The spec states the condition — retention or assists worsening over two
  consecutive published periods prompts the owner to suspend points and keep the distribution view.
  It is **not implemented**: it needs two published periods of real data to be meaningful, and a
  prompt built against no data is a prompt nobody has seen fire. On `docs/backlog.md`.
- **Hindi and Marathi.** Answer 6. A translation is not a text to generate when somebody is held to
  what it says, which is the same refusal M10 made about consent notices.
- **The recognition board.** The award is granted and stored with its citation; the public board by
  the kitchen door is a screen and is on the backlog.
- **Scheme editing.** A scheme is created and activated; changing one is a new scheme with a later
  `effective_from`, because editing the weights a published period was computed against would
  rewrite the basis of a payment — which is the thing this module exists to prevent.

---

## Tests

| File | Count |
|---|---|
| `tests/test_m17_scoring.py` | 26 |
| `tests/test_m17_endpoints.py` | 11 |
| `frontend/src/staff/fairnessDiscipline.test.ts` | 6 |
