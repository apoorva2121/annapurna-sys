# M17 · Workload Fairness & Recognition — Module Spec

**Depends on** M07 (orders), M12 (shifts), M13 (the query layer), M15 (data with a shape).
**Status** — spec written 2026-09-19, before any code, per `docs/sdlc.md` step 1.
Build log: `docs/plan/m17-build-log.md`.

Tables: `incentive_scheme`, `performance_period`, `performance_score`, `performance_note`,
`recognition_award`. Design: `docs/workload-fairness.md`. Decisions: ADR 0011.

---

## What this module is for, and the sentence it has to keep

The owner's question is *"who is actually carrying the load, and how do I reward them fairly?"* —
and `docs/workload-fairness.md` opens by naming the risk in the same breath:

> **A measurement system aimed at morale can destroy morale if built carelessly.**

That is not a caveat, it is the specification. A restaurant is a place where the owner holds far
more power than a waiter, and a scoring system handed to that relationship without guardrails
becomes a tool for the stronger party. Every decision below exists to stop this module becoming
that, and **the module is worth building only if it stays the other thing**: feedback somebody can
see, argue with, and be paid for.

The primary screen is therefore **not** a leaderboard. It is the **workload distribution** — who
handled what share, with section context beside it — because the finding an owner needs is usually
*the roster is unfair*, not *this person is bad*.

---

## The eight open questions, answered

`docs/workload-fairness.md` §"Open design questions" says each must have a written answer here,
even when the answer is "no". These are the answers this module builds to.

### 1 · An employee can dispute a score, and a period cannot be published over an unanswered dispute

**Built.** `performance_note` gains an `author_role` distinction so an employee can raise one, and a
period refuses to publish while a dispute on it is unanswered. Answered means *accepted or declined
with a reason* — a note, by a named person, visible to the employee.

The alternative is the thing the proposal was worried about: visibility without recourse, which is
the shape of surveillance rather than feedback.

### 2 · Nothing in this product consumes a score to punish, and it says so

**Refused, deliberately, and stated in the product.** No deduction, no penalty, no warning, no
"improvement plan" feature reads `performance_score`. Software cannot stop an owner using a number
badly in a conversation; it can decline to build the mechanism and say why.

The purpose shown to staff on their own screen is one sentence: *"This is used for rewards and for
fairer rosters."* If that stops being true, the sentence is a lie the product is telling, which is a
thing somebody will notice.

### 3 · Below five scored people, the team sees only the team's own figure

**Five.** With three waiters, naming the top two names the third, which defeats "never publish a
bottom ranking" by arithmetic rather than by intent. Below the threshold the team view shows the
team's aggregate and each person's own row; the manager still sees individuals, because coaching is
their job.

Five rather than four because a four-person team with one obvious top and one obvious bottom is the
same problem with an extra step.

### 4 · The attendance denominator excludes approved absence, and the list is unit-tested

**Built as an explicit, tested exclusion list**, the same shape as the volume-weight rule: approved
leave, sickness, maternity or paternity leave, religious observance, and any day the person was not
rostered. A scored attendance metric that counted an approved absence as a miss would quietly
disadvantage exactly the people employment law protects, and it would do so while looking neutral.

### 5 · Every scored metric names how its actor is recorded, and what happens when that is wrong

**A table in this spec, and a column in the screen.** For each scored metric: where the actor comes
from, and its known weakness.

| Metric | Actor comes from | Known weakness |
|---|---|---|
| Covers, orders per hour | `order.waiter_employee_id`, set at open or by the roster (M12) | A captain entering orders for a section — visible as an implausible rate, and the manager's note is the fix |
| Order accuracy | `order_line` cancellations and M09 service-stage waste | A remake logged against whoever reported it, not whoever caused it |
| Rating | `feedback.waiter_employee_id`, copied from the order | Inherits the order's attribution |
| Attributable complaints | `complaint.order_id` → that order's waiter | A complaint about the kitchen recorded against the server |
| Attendance | `shift_assignment` clock times (M12) | A shared login; M12's clock-in takes no employee id precisely to reduce this |

**And the rule that follows from the table:** every scored figure on an employee's own screen is
shown with the count behind it, so a wrong attribution is visible as a wrong *number of things*
rather than as an unexplained score. A manager can annotate; nobody can silently edit.

### 6 · The employee's own view is sentences, in their language, and is the module's exit criterion

**English now, with the strings separated for translation, and a stated gap.** The screens are built
so the employee view is plain sentences — *"You served 214 covers in 38 hours. That is 5.6 an hour;
the section averaged 5.1."* — rather than a formula and a weight table.

Hindi and Marathi are **not** shipped, for the reason M10 gave about consent notices: a translation
is not a text to generate when somebody is held to what it says. The gap is recorded here and in
`docs/backlog.md` rather than papered over, and it is a real limit on where this feature should be
switched on.

### 7 · The legal basis: DPDP §7(i), and the two things that are *not* settled

**Researched 2026-09-19, cited rather than remembered** (CLAUDE.md standing rule 1).

**Section 7(i) of the Digital Personal Data Protection Act, 2023** lists as a legitimate use:

> *"for the purposes of employment or those related to safeguarding the employer from loss or
> liability, such as prevention of corporate espionage, maintenance of confidentiality of trade
> secrets, intellectual property, classified information or provision of any service or benefit
> sought by a Data Principal who is an employee."*

So processing employee performance data for employment purposes **does not require consent** under
the Act. Commentary treats performance evaluation as squarely within it.

**Two things this does not settle, and `docs/compliance-rules.md` forbids conflating them with the
first:**

- **It is not in force yet.** `docs/compliance-rules.md` §B2 records the DPDP's core obligations as
  commencing **13 May 2027** — *notified but not in force*. Only *in force* may block a user, and
  nothing here blocks one.
- **Purpose limitation still binds when it does commence.** §7(i) covers employment purposes; it
  does not cover using the same data for something else later. So: scores are not exported, not
  shared outside the restaurant, and not used for anything the employee's own screen does not say
  they are used for.

**Retention is decided here because it cannot be retrofitted:** a frozen score is kept for **three
financial years** after the period it belongs to, and is erased when an employee leaves **unless an
award was granted against it**, in which case it is kept with the award as the record of why money
was paid. That pairing is the whole of the rule, and it goes in `docs/compliance-rules.md`.

### 8 · The stop rule, written down before the feature is switched on

**Two consecutive published periods in which retention worsens, or in which assists fall, prompts
the owner to suspend points and keep only the workload-distribution view.**

It is a prompt rather than an automatic switch, for the same reason awards are granted by a human:
the data informs the decision and never makes it. But it is *built* — a product that can only be
turned on is a product nobody can honestly evaluate.

---

## The decisions that matter

### 1 · Live is a query; published is frozen; nothing recomputes

ADR 0011, unchanged. A `performance_period` is `draft → published → finalised`. Draft metrics are
computed live from orders, tickets, feedback and shifts. **Publish writes them into
`performance_score` and they are never recomputed** — the same reason `theoretical_food_cost` is
frozen at settlement: a later void must not rewrite the basis on which a bonus was paid.

The freeze test is the module's most important: publish a period, void an order inside it, and
assert the score does not move.

### 2 · Only controllable metrics carry weight; context metrics carry zero and are shown anyway

A waiter penalised for the tandoor running slow will correctly conclude the system is stupid and
ignore all of it. Kitchen delay, section footfall, table size and tips are `context`.

Showing them with zero weight is not decoration: it is what makes a low score *explainable* to the
person holding it, which is the difference between feedback and an accusation.

### 3 · Normalise per hour worked or per cover, and never rank a raw count

A four-hour shift and an eight-hour shift are not comparable and a raw total measures the roster.
Every metric is a rate, and comparison is within like-for-like shift types.

### 4 · Volume weight ≤ accuracy weight + rating weight, enforced when a scheme is saved

Without it the system pays people to rush, which is the opposite of the goal. Enforced on save with
its own test, and the suggested starting weights (accuracy 25, rating 20, volume 20, speed 15,
attendance 10, assists 10) satisfy it with room to spare.

### 5 · Assists are derived, never logged

An "assist" is an order served outside the waiter's own section — derived from
`order → table → dining_area` against `shift_assignment.dining_area_id`. Asking somebody to log
their own helpfulness produces a log of who remembers to log, which measures the wrong thing and
rewards the wrong person.

### 6 · No endpoint returns a bottom-ranked list, and a serialiser test enforces it

Top contributors are visible to the team; low performers are visible only to their manager. This is
a property of the *API*, not of the screens, because a screen can be reimplemented and an endpoint
that emits a bottom ranking will eventually be rendered.

---

## Not in scope

- **Automatic payouts.** ADR 0011. Points never trigger money.
- **Peer rating.** A popularity contest and a bullying vector.
- **Any punitive feature.** Answer 2 above.
- **Hindi and Marathi.** Answer 6 — recorded as a limit, not as a to-do.
- **Cross-restaurant comparison.** Out of month 1, and comparing two kitchens is comparing two
  roster patterns.

---

## Acceptance criteria

1. A published period does not move when an underlying order is voided afterwards.
2. A scheme whose volume weight exceeds accuracy + rating is refused on save.
3. Assists derive correctly when a waiter serves a table outside their section.
4. Normalisation makes a four-hour and an eight-hour shift comparable.
5. **No serialiser in the codebase can emit a bottom-ranked list**, asserted by a test over the
   response schemas rather than over one endpoint.
6. `performance.view.own` is held by every role and the catalogue test proves it.
7. A period refuses to publish while an employee's dispute is unanswered.
8. Approved leave, sickness and unrostered days are excluded from the attendance denominator.
9. Below five scored people the team view shows no individual but the viewer's own.
10. Every employee-facing figure is a sentence with its count beside it.
11. Generic suites 1–5 pass, with victim rows for the five new tables.

---

## Chunks — three PRs against `feat/m17-fairness`

**A · The schema and the scheme.** Five tables, the permissions, and the weight validator with its
test. No scoring yet.

**B · The metrics and the freeze.** Live computation, publication, the freeze test, the exclusion
list, and the dispute that blocks a publish.

**C · The screens.** Workload distribution first, then my performance, team performance, scheme
configuration and the award grant. Ends with `make check` clean.
