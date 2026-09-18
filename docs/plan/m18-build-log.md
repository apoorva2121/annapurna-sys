# M18 · Compliance & Risk Alarms — Build Log

Spec: `docs/modules/M18-compliance-spec.md`. Manual script: `docs/manual-tests/M18-compliance.md`.
Rules: `docs/compliance-rules.md`. Schema: `docs/schema.md` §14.

---

## State

| Chunk | What | State |
|---|---|---|
| A | The rule catalogue, two tables, migration 0053, the evaluator, 35 tests | ✅ committed |
| B | Six routes, two permissions, migration 0054, the CSV export, 11 tests | ✅ committed |
| C | The findings screen, the owner's card, the discipline test | ✅ committed |
| — | Manual pass | **Owner's** |

Built on 2026-09-19, on `feat/m11-communication` after M17.

---

## What this module is, and the way it can fail

`docs/compliance-rules.md` opens with a sentence that is both the reason this module exists and the
reason it is dangerous:

> **Never fill an Indian rate, threshold or commencement date from memory** — research returned
> stale-but-confident law three times in one session.

A product that warns a restaurant about the law is a product that can be *confidently wrong* about
the law. And a confidently wrong warning is worse than no warning at all, because it teaches an
owner to ignore the next one — which will be the true one.

So this module's whole design is about being checkable rather than about being clever. Nothing here
is a judgement the product asks to be trusted on:

- every rule carries its **instrument**, its **commencement date** and the **date the citation was
  last checked**, and all three reach the screen;
- every finding carries the **evidence** it was raised from, so a person can check the working;
- a rule that is **not in force says so in words**, above its citation, never in a colour;
- the export lists **every rule that was checked**, including the ones that found nothing.

---

## The four decisions

### 1 · Four states, and only one of them may block

`in_force`, `notified_not_in_force`, `unsettled`, `unverified`. `docs/compliance-rules.md`'s second
standing rule is that these must never be conflated, and only the first is safe to build on.

The rule is kept **structurally rather than by review**:

```python
def __post_init__(self) -> None:
    if self.severity is Severity.CRITICAL and self.status is not RuleStatus.IN_FORCE:
        raise ValueError(
            f"{self.code}: only a rule in force may be critical. This one is "
            f"{self.status.value}, so it may inform and must not block."
        )
```

Two rules in the shipped catalogue prove it works. **DPDP** commences 13 May 2027 — notified, not
in force — and is advisory; its text opens with *"this is not law today."* The **service charge**
position rests on a Delhi High Court single judge upholding the CCPA guidelines in March 2025 with
an appeal pending: unsettled, advisory, and the text says the position is live.

`tests/test_m18_compliance.py::TestTheRuleThatGovernsTheRules` asserts this over the **whole
catalogue**, including rules nobody has written yet, and separately asserts that the constructor
refuses the combination — without which the first test only says the ten rules happen to be fine
today.

### 2 · The rule catalogue is code, not a table

A rule is a query plus a citation, and a query does not live in a row.
`compliance_rule` is eliminated in schema.md for exactly that reason: such a table would hold
the words and leave the detection in code, free to drift apart from them. So
`app/core/compliance.py` holds both, and `compliance_finding.rule_code` is deliberately **not a
foreign key** — a finding raised by a rule later withdrawn keeps its code and its words, which is
exactly what an inspection asks about.

### 3 · Evaluation runs when somebody opens the screen

ADR 0005 leaves this product with no background job, so there is no nightly sweep. `GET
/compliance/findings` evaluates, writes what it newly found, resolves what has been put right, and
commits. It is the only read in this product that writes, and that is stated in the route's
docstring rather than left to be discovered.

The consequence is worth stating in the product and not only here: **`raised_at` is when the
product first noticed, not when the condition began.** A licence that expired in March and is first
opened in June raises a finding dated June. The screen says so under every finding, and the export
says so at the top, because an inspection is exactly the wrong place to discover a date meant
something else.

### 4 · The record is the product

M14's notification centre is derived and stores only what a person *did* about a condition, because
a condition that resolves should disappear. This is the opposite case: the export is what an owner
hands an inspector, and it has to reconstruct *what was known when*, which today's data cannot do
however carefully it is queried.

So `compliance_event` is append-only — `raised`, `acknowledged`, `suppressed`, `resolved` — and
**suppressing is a recorded decision rather than a deletion**. The finding stays on the list,
marked, with the reason and the person attached. Advice ignored is still advice given.

---

## The ten rules, and what each is conditional on

| Code | Severity | Status | Fires when |
|---|---|---|---|
| `fssai.expired` | critical | in force | The expiry date has passed. The day itself is *not* expired |
| `fssai.expiring` | warning | in force | Inside 30 days of expiry |
| `fssai.malformed` | critical | in force | The number is absent or not 14 digits — **and a bill has been issued** |
| `fssai.tier` | warning | in force | Turnover has passed the band the licence covers |
| `gst.gstin_missing` | critical | in force | Invoices are issued, the restaurant is not on composition, and the GSTIN is absent or malformed |
| `gst.rate_missing` | critical | in force | An active tax group has no rate current today |
| `labelling.allergens` | warning | in force | A live menu item has no allergen statement |
| `labelling.calories` | warning | in force | Items lack calories **and** the restaurant holds a Central licence or has ≥10 outlets |
| `dpdp.consent` | advisory | **notified, not in force** | Customers are on file with no consent recorded |
| `ccpa.service_charge` | advisory | **unsettled** | A service charge rate is configured |

The conditionality in the last column is most of the design. A rule that fires at everybody is a
rule everybody turns off.

---

## What the tests found

### 1 · The event insert preceded the finding insert

```
sqlalchemy.exc.IntegrityError: ForeignKeyViolationError: insert or update on table
"compliance_event" violates foreign key constraint
"compliance_event_compliance_finding_id_restaurant_id_fkey"
DETAIL:  Key (compliance_finding_id, restaurant_id)=(01a0b657-…, 01a0b657-…) is not present in
table "compliance_finding".
```

SQLAlchemy's unit of work orders inserts by **relationship** dependencies. These two mappers are
joined only by a composite `ForeignKeyConstraint` in `__table_args__` — deliberately, to avoid a
lazy-loading surface — so there was nothing for it to order them by. `_raise` now flushes before
appending the event, with the reason written beside it.

### 2 · A DPDP advisory on every brand-new tenant

The rule asked whether any consent rows existed. Zero-and-zero is a tenant with **no customers**,
not a tenant with a gap. `Facts.consent_rows` became `Facts.customers_without_consent`, counted as
customers on file with no consent row.

### 3 · A red `critical` four minutes into onboarding

```
AssertionError: [{'rule_code': 'fssai.malformed', 'severity': 'critical', 'state': 'open', ...}]
```

A restaurant that has issued no bill has an *incomplete setup*, which is M02's business and not a
licence risk. `_malformed_licence` now waits for the first invoice — the same condition `_gstin`
already used. Both of these are the same defect wearing different clothes, and it is the defect
this module most needs to avoid: **being ignored when it is right**.

### 4 · The generic tenant-isolation suite refused the build

```
AssertionError: cross-tenant access succeeded on:
['POST /api/v1/staff/compliance/findings/{finding_id}/suppress -> 400']
```

Suppressing validated the reason before looking the finding up, so a cross-tenant probe with no
reason got 400 instead of 404 — which tells a stranger their guessed id exists. Existence in scope
is now decided first, so a refusal never distinguishes *"not yours"* from *"badly formed"*. Suite 1
also required a victim finding row; this is the tenth module in a row it has refused the build for.

### 5 · A test asserting the wrong thing

The default FSSAI number in the test fixture was `10012345678901`, whose state code is `00` — a
**Central** licence, covered by the calorie declaration on its own limb whatever the outlet count.
The rule was right and the fixture was a chain by accident. The default is now a State licence and
both limbs are tested.

---

## Permissions

`compliance.view` → owner, admin, **manager**, accountant. `compliance.act` → owner, admin.

The manager holds the first and not the second, and the asymmetry with `audit.view` is deliberate:
a manager is denied the audit trail because they are frequently the *subject* of it, whereas a
compliance finding is about the restaurant. The person who runs the floor is the person most able
to act on an expired licence and the least appropriate person to decide it does not matter.

---

## What is deliberately not here

- **No blocking.** Nothing in this module prevents an action. It informs, and the P1 permission
  design decides who may act. A product that refuses to save a menu item over an allergen rule
  would be making a legal judgement on a restaurant's behalf.
- **No automatic filing.** GST e-invoicing and returns are out of scope for month 1 (CLAUDE.md),
  and this module does not creep toward them.
- **No rule the product cannot cite.** The `unverified` state exists so a future rule can be
  carried without being asserted; nothing ships in it today.

---

## Runs

| Run | Result |
|---|---|
| `pytest tests/test_m18_compliance.py` | 35 passed |
| `pytest tests/test_m18_endpoints.py` | 11 passed |
| `pytest tests/test_generic_suites.py` | 29 passed |
| `pytest tests/test_permission_seed.py` | 8 passed |
| `vitest run` (frontend) | 433 passed |
| `make check` | see below |
