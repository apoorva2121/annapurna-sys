# M14 · Audit & Notifications — Module Spec

**Depends on** M01, which created `audit_log` early and said why. Touches every service that writes
one, which is ten of them.
**Status** — spec written 2026-09-18, before any code, per `docs/sdlc.md` step 1.
Build log: `docs/plan/m14-build-log.md`.

Tables: `notification` (new). `audit_log` and `issue` already exist.
Endpoints: `GET /audit`, `GET /notifications`, `PATCH /notifications/{id}/read`.
Screens: the audit trail, and the notification centre.

**One owner decision taken before this spec was written** (2026-09-18): **the decorator lands and
all ten existing `_audit` helpers are migrated onto it.** The rule only works if there is one path;
leaving ten in place keeps precisely the failure mode the decorator exists to remove, and the next
module makes it eleven.

---

## Why a decorator, and what it is really for

`docs/modules.md` states the rule and its reason in one line: *"audit written by a service-layer
decorator, not by hand at each call site — hand-written audit calls get forgotten exactly where
they matter."*

That is not a style preference, it is a threat model. An insider's most valuable act is the one
nobody recorded, and the call sites most likely to be missed are the rare ones — the manual price
override, the adjustment at the end of a bad month, the role granted at eleven at night. Each is a
path somebody wrote once, in a hurry.

So the real deliverable is not the decorator. **It is the test that fails the build when a mutating
service method does not declare an audit**, exactly as M00's suite fails the build when a route
declares no permission. The decorator is what makes that test possible to satisfy.

There are ten private `_audit` helpers today — in `procurement`, `employee`, `orders` (twice),
`cash`, `inventory`, `menu`, `setup`, `stock`, `reversals` and `shifts` — each a near-copy. Ten
copies of one idea is nine chances for the tenth to differ.

---

## Research — what binds this module, checked 2026-09-18

**`docs/compliance-rules.md`: no rule in §A or §B binds an audit trail.** Checked rather than
assumed. Recorded anyway because the *reason* an owner wants this record is often a dispute or an
inspection: an audit trail is **not** a statutory register and must never be described as one.

**DPDP §B2 (not in force; Phase 3 commences 13 May 2027)** touches it in one place, and it is M11's
gap again: an audit row's `old_value`/`new_value` can hold a customer's name or phone — a corrected
order, an edited customer record — and M10's erasure does not reach it. This module does not solve
that; what it does is refuse to widen it. **No audit row is written for a read**, and no
notification body quotes customer data.

**`docs/observability.md`** fixes the log shape and the redaction filter. An audit row is not a log
line: it has a subject, and it survives log rotation.

**ADR 0008** puts `audit_log` in the append-only tier. Nothing here updates or deletes one.

**The P1 design gives `audit.view` to the owner, the admin and the accountant — not the manager.**
That is the line the viewer is built to: the person who runs the floor is frequently the subject of
the record, and a record its subject curates is not a record.

---

## The decisions that matter

### 1 · The decorator declares; the service does not remember

```python
@audited("order.void", entity="order", key="order_id")
async def void(self, actor: Actor, order_id: uuid.UUID, *, reason: str) -> None: ...
```

It loads the entity through the service's own repository **before** the call and again after, diffs
the mapped columns, and writes one row with both values and the actor. A service opts in by being
an `AuditedService`, which is what gives the decorator something to load with.

**What it must not become:** magic that writes a row nobody can predict. The action string is
explicit, the entity is explicit, and the diff is over mapped columns rather than anything clever.
A reviewer reading the signature can say what will be recorded.

### 2 · A mutating method without a declaration fails the build

The module's actual deliverable. An AST walk over `app/services/` finds every public async method
that writes — adds to the session, or mutates a mapped attribute — and asserts it carries
`@audited` or appears in an explicit, commented exemption list.

**The exemption list is the interesting part**, and it is short by design: sending a message, moving
a KOT ticket, clocking in. Each carries a sentence saying why the act is not worth a row, so a new
exemption is a decision somebody writes down rather than a line somebody forgot.

This is M00's "a route with no declared permission fails the build", pointed at the second thing
that gets forgotten in exactly the same way.

### 3 · Ten helpers become none, and two keep something the decorator lacks

All ten private `_audit` methods are deleted and their call sites become declarations. Their tests
are the safety net: every one of those paths is already covered, so a lost audit row surfaces as a
failing test rather than as silence.

Two do something the decorator cannot: `OrderService._waiter_audit` records a *reason* (`roster`,
a handover note) and `ShiftService`'s correction records one too. So `@audited` takes an optional
reason resolved from the call, and those two keep their meaning rather than being flattened to fit.

### 4 · A notification is a condition the product noticed, not a row a job wrote

**There is no background job in this product.** ADR 0005 puts scheduled work in a container
invocation and none is deployed. A `notification` table filled by a job that is not running is a
notification centre that is silently empty — the worst failure available, because it looks exactly
like *nothing is wrong*.

So the centre is **derived** from conditions the product can already answer — stock below reorder,
batches expiring, an open complaint, an overdue task, a till variance, a count awaiting approval —
each a query that already exists and is already indexed. The `notification` table stores what a
*person* did about one: read it, dismissed it. Keyed by a stable identity of the condition, so
dismissing "paneer expiring on the 21st" does not also dismiss the next batch.

**What this buys:** a centre that cannot go stale, cannot double-send, and needs no job.
**What it costs:** a notification for a condition that has since resolved simply disappears — which
for a restaurant is the right behaviour, and is written down here so it is a decision rather than
an accident.

`channels` and `dispatched_at` stay in the schema unused: push, email and WhatsApp are Phase 2, and
the columns being there is what stops the table being redesigned when they arrive.

### 5 · Escalation is who sees it, not how loudly

Vision §25's four tiers, applied to the conditions above rather than to invented ones:

| Tier | Example | Reaches |
|---|---|---|
| Minor | one overdue task | its assignee |
| Repeated | a section's tasks overdue three days running | the manager |
| Pattern | food-cost variance above threshold for a week | manager + owner |
| Critical | a critical complaint, a negative-stock item | immediately, owner included |

**The rule under all four:** a person sees a condition they can act on. A waiter is not shown a
food-cost variance they cannot change, and an owner is not shown one overdue task. *"This will
prevent notification overload"* is the vision's own sentence, and this is the only way it survives
contact with a real week.

### 6 · Severity is the locked colour scale, and never two reds in one region

`severity` maps to the six locked alert tokens (`docs/ui/conventions.md`), not themeable, not
changeable without an ADR. `critical` means *somebody must act now*, and the centre collapses
multiple criticals into a count — the rule the floor map already follows.

### 7 · The viewer answers a question, not "show me everything"

Filters are entity, actor and date range, because those are the three ways somebody actually
arrives: *what happened to this order*, *what did this person do*, *what happened on Tuesday*. A
free-text search over `old_value` would be a second copy of everything in the product, outside
every retention story — the refusal M11 already made about message search.

Every row renders as a sentence — *"Priya changed Butter Chicken's price from ₹480 to ₹520"* — with
the raw values beneath. A JSON blob on screen is a log, not a record.

---

## Not in scope

- **No push, email or WhatsApp.** Phase 2; the columns exist so the table does not change.
- **No background job.** Decision 4.
- **No audit of reads.** Who looked at what is a different product with a different retention
  story, and DPDP is not improved by recording more.
- **No full-text search over audit values.** Decision 7.
- **No retention policy.** The gap M11 opened stays open and stays named; M16 owns it.
- **No AI summarisation of the trail.** Vision §26, Phase 3.

---

## Acceptance criteria

1. A price change, a recipe edit, an order void and a stock adjustment each produce one audit row
   with correct before and after values — `docs/modules.md`'s own test.
2. **A new mutating service method with no audit declaration and no exemption fails the build.**
3. All ten existing `_audit` helpers are gone, and every test that covered them still passes.
4. The two reason-carrying audits — waiter assignment and shift correction — keep their reasons.
5. No audit row is written for any read.
6. The notification centre renders the real conditions on seeded data, and renders **nothing** when
   none is true.
7. Dismissing one condition does not dismiss another of the same kind.
8. A waiter sees no financial notification; an owner sees no single overdue task.
9. `GET /audit` is bounded, filterable three ways, and issues a bounded number of queries.
10. A manager cannot open the audit trail; the owner, the admin and the accountant can.
11. Every audit row renders as a sentence, with raw values available beneath it.
12. Generic suites 1–5 pass, with a victim row for `notification`.

---

## Chunks — three PRs against `feat/m14-audit`

**A · The decorator and the build-failing test.** `@audited`, `AuditedService`, the AST guard, and
the exemption list with its reasons. No behaviour change yet.

**B · The migration of all ten.** Ten services, ten helpers deleted, every existing test green.

**C · Notifications and the screens.** The derived conditions, the `notification` table for read
state, the escalation map, the viewer and the centre. Ends with `make check` clean and the manual
script written.
