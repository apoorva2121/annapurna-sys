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

---

## Amended 2026-09-19 · the thing this log should have said and did not

M16's backlog sweep found a row that said **"Decide before M17 starts"**, and M17 started and
shipped without deciding.

> *Staff without a login cannot see their own performance score.* ADR 0011 §3 promises every
> employee can always see their own figures and grants `performance.view.own` to every role to make
> it structural. ADR 0007 makes an employee without a `user_account` normal — in the seed, two
> kitchen staff and both cleaners. **So the guarantee failed silently for exactly the lowest-paid
> staff it was written to protect**, and this module's whole claim to raising morale rested on it.

The row had already decided the part that mattered: *"a score for someone with no way to see it
should not be published or used for incentives."* That is now built.

`publish` leaves those people out of the freeze, and `unscored()` names them on the period.
**An exclusion, not a refusal**, and the reasoning is in the service's docstring:

- refusing the publish would block the feature in any restaurant with one cleaner who has no
  phone, which is most of them;
- scoring them anyway would freeze a number about somebody who cannot read it, which is the
  definition of surveillance the ethics review was about.

`unscored()` is **derived rather than stored**, so it stops naming a person the moment they are
given a login — a column stamped at publish time would keep naming them after the problem was
fixed, which is how a warning becomes furniture.

Writing it changed the test fixture in a way worth recording: `_world` now gives every employee a
login by default. It had given none, so **every existing M17 test was scoring people who could not
see their scores** — the product problem reproduced inside the suite that was supposed to be
checking the product. One test failed immediately on the new rule (`assert None is not None`) and
was right to.

**Still the owner's:** *how* such a person sees their figures — a view-only login, a messaging
summary, or a manager who shows them and records it. Until that is chosen they appear on the
workload screen, which is about the roster rather than pay, and are left out of the money.
