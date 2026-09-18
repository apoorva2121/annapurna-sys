# M14 · Audit & Notifications — Build Log

Spec: `docs/modules/M14-audit-spec.md`. Manual script: `docs/manual-tests/M14-audit.md`.

---

## State

| Chunk | What | State |
|---|---|---|
| A+B | `@audited`, `record`, `AuditSubjectRepository`, the AST guard, and all ten helpers migrated | ✅ committed |
| C | Migrations 0049–0050, the derived centre, the trail's endpoint, two screens | ✅ committed |
| — | Manual pass | **Owner's** |

Built in one autonomous run on 2026-09-18, on `feat/m11-communication` after M13.

Chunks A and B landed together rather than separately. The spec had A shipping the guard with no
behaviour change and B migrating the helpers, but a guard that recognised the ten existing helpers
would have been a knowingly weakened guard shipped on the promise of strengthening it later. One
commit, one rule, no interim.

---

## The finding that matters most

**Three money-affecting order methods took no actor at all.**

`OrderService.update_line`, `add_charge` and `remove_charge` each change what a table is charged,
and each was written with no `Actor` parameter — so nothing in the product *could* record who did
it, however carefully somebody wrote the audit call. They had none.

That is exactly the class of gap `tests/test_audit_declarations.py` exists to find, and it was found
on the day the guard was written rather than by an owner asking who added a ₹400 service charge.
The parameter is added, the routes pass the actor they already hold, and all three now write a row.

Two more the migration surfaced:

**`inventory.py`'s helper hard-coded `entity_type="stock_movement"`** for all four of its call
sites — two of which pass a *batch* id and a *count* id. "What happened to this batch" has returned
nothing since M05, and would have gone on doing so: the rows exist, they are simply filed under the
wrong table. Each call site now names its own entity.

**`WastageService.create_reason` and `update_reason` took no actor either.** Those flags decide
whether waste needs a second person's approval — the control M09 built — and changing one was
attributable to nobody.

---

## The decisions that changed on contact

### 1 · Two ways to declare, because there are two kinds of audit-worthy fact

The spec said the decorator would replace every hand-written call. It does not, and pretending it
did would have made the trail worse.

`@audited` writes a **diff**: what the row was, what it became. That covers most acts — a price
changed, a role granted, a till closed. But some facts are not in the row:

- *"This void sent one line to the kitchen and ₹640 of food with it."*
- *"This settlement found a dish with no recipe."*
- *"The payout was ₹2,000, and here is why."* — a payout adds a `cash_movement` and changes
  `cash_session` not at all, so a diff of the till would be empty.

Forcing those into a diff would have lost the half a person actually reads. So M14 ships **one
writer** (`record`) and **one rule** (the guard), and `@audited` is the shorthand for the diff case.
The guard accepts a decorator, an explicit `record(...)` call, or one level of a private helper that
makes one — the last because three public methods write the same waiter-handover row and spelling it
out three times would be the duplication this module exists to remove.

### 2 · The exemption list is 28 entries, not the handful the spec imagined

104 public service methods mutate something. 47 audit call sites existed. The rest are exempt, and
each carries a sentence.

The strongest of them is the customers one, and it is worth repeating here because it runs the
opposite way to intuition: **auditing every customer edit would work against DPDP rather than for
it.** An audit row holds old and new values, so recording each change would copy a person's name
and number into a table M10's erasure does not reach — building the retention problem the erasure
exists to solve. The customer record is itself the record, it is on screen, and the one act that
cannot be undone — erasure — *is* audited.

Ten whole modules are exempt rather than method by method: messages, tasks, the kitchen rail,
feedback, attachments, complaints and the cursors. Each states why, and the guard asserts that an
exempt module contains **no** audited method — because if one act there were worth a row, the
exemption would be hiding the next one somebody adds beside it.

### 3 · The notification table is smaller than the schema sketched, on purpose

`docs/schema.md` §12 described a stored notification: severity, title, body, channels,
dispatched_at. That shape needs a writer, and **there is no background job in this product**. A
table filled by a job that is not running is a centre that is silently empty — which looks exactly
like nothing being wrong, and is the worst failure a notification system has available.

So the centre is derived and the table holds one thing: what a person did about a condition.

`channels` and `dispatched_at` are **not** kept, which departs from the spec's own decision 4. The
argument for keeping them was avoiding a Phase 2 redesign; against them is that this codebase
already carries a backlog row about `customer.visit_count` and `lifetime_value` — columns nothing
writes — as a defect class that shipped a screen reading numbers nobody maintained. Adding two more
knowingly, to save one migration later, is repeating a mistake with its own row in the backlog.

### 4 · The centre needs no permission, and the generic suite disagreed

`GET /notifications` declares no permission, because what it *shows* is already decided per
condition by what each person can act on. A route-level permission would be a second, weaker copy
of that rule, and the P1 design has no code for it — which
`test_the_shipped_catalogue_is_a_subset_of_the_p1_design` forbids inventing.

Suite 4 refused the build for exactly that, as it is supposed to. Both routes are now on its
allow-list beside `/auth/me` and `/auth/switch`, with the argument written out where somebody
auditing the list will read it.

---

## The defect, and the rule it leaves behind

```
FAILED tests/test_waste_endpoints.py::TestReasons::test_the_stage_cannot_be_changed
ValidationError: 2 validation errors for PricedStockItemResponse
ingredient
  Error extracting attribute: InvalidRequestError: 'StockItem.ingredient' is not available
  due to lazy='raise'
... 34 failed, 262 passed
```

The first snapshot read the mapped object and called `session.expire()` on it to see the
after-state. It worked — and it expired *the caller's* object, so the route that had just created a
stock item serialised it, found its eagerly-loaded relationship gone, and returned a 500.

**An audit decorator that changes what the method it wraps returns is worse than no decorator**: it
turns a recording mechanism into a source of bugs in the paths it records. The snapshot reads
columns now, which touches no identity map.
`TestTheDecoratorDisturbsNothing` holds it, with that output in its docstring.

---

## What is not here

- **No push, email or WhatsApp.** Phase 2.
- **No background job.** Decision 3 above, and the reason the centre is derived.
- **No audit of reads.** Who looked at what is a different product with a different retention story,
  and asserted by `test_reading_the_trail_writes_nothing_to_it`.
- **No free-text search over audit values.** A second copy of everything in the product, outside
  every retention story — the refusal M11 made about message search.
- **No retention policy.** The gap M11 opened stays open and stays named; M16 owns it.
- **No escalation ladder beyond who sees a condition.** Vision §25's four tiers are implemented as
  *audience*, not as repetition: an overdue task goes to its assignee, and to somebody who holds
  `task.assign` because chasing them is the job. Nothing repeats itself more loudly, because a
  notification that shouts is a notification somebody turns off.

---

## Tests

| File | Count |
|---|---|
| `tests/test_audit_decorator.py` | 17 |
| `tests/test_audit_declarations.py` | 5 |
| `tests/test_audit_endpoints.py` | 13 |
| `frontend/src/staff/screens/NotificationsScreen.test.tsx` | 4 |
