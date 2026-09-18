# M18 · Compliance Risk Alarms — Module Spec

**Depends on** M02 (restaurant identity), M03 (menu), M14 (notifications). Richer with M07's real
turnover and M10's consent.
**Status** — spec written 2026-09-19, before any code, per `docs/sdlc.md` step 1.
Build log: `docs/plan/m18-build-log.md`. Rules and their statutory basis: `docs/compliance-rules.md`.

Tables: `compliance_finding`, `compliance_event`. **The rule catalogue is code, not a table** —
decision 2 below.

---

## Why this module exists

`docs/modules.md` states it in two sentences that decide everything else:

> Indian restaurants are shut down for paperwork far more often than for bad food, and the owner is
> usually the last to know a licence lapsed. The product already holds every fact needed to see it
> coming — licence dates, turnover, food types, tax rates, GSTIN. **This module is the difference
> between holding those facts and acting on them.**

And `docs/compliance-rules.md` states the way it can go wrong, from experience inside this project:

> The research that produced it returned **stale-but-confident law three times in one session.**

So a rule that cannot cite its instrument and the date somebody checked it does not ship. A rumour
rendered as an alarm is worse than no alarm, because it teaches an owner to dismiss the card.

---

## The decisions that matter

### 1 · Four states, and only one of them may block

`in_force` · `notified_not_in_force` · `unsettled` · `unverified`.

**Only `in_force` may raise a `critical`.** A rule commencing in 2027 may inform and must say so in
words — "this becomes law on 13 May 2027" — and a rule whose appellate position is unsettled says
that too. Conflating the four is the specific failure `docs/compliance-rules.md` was written to
prevent, and it is enforced by a test rather than by care.

### 2 · The rule catalogue is code, not a table

`docs/modules.md` proposed a seeded `compliance_rule` table. It is not built, and the reason is the
same one M14 gave about notifications: **a rule is a query plus a citation**, and the query cannot
live in a row. A table would hold the half that does not matter and leave the half that does — the
detection — in code anyway, in a different file, free to disagree with it.

So the catalogue is a module of typed rules, each carrying its instrument, its commencement, the
date it was last checked, and the function that evaluates it. `tests/test_m18_compliance.py` asserts
every rule has all four. A table is still the right answer the day a tenant may write their own
rule; none may, and none should.

### 3 · Findings are stored, and evaluated on read

Unlike M14's notification centre, **the record is the product here**: the export is what an owner
hands an inspector, and it has to reconstruct *what was known when*. That cannot be derived from
today's data.

There is still no background job (ADR 0005), so evaluation runs **when somebody opens the screen**:
newly-detected findings are written, cleared ones are resolved, and both are events. The
consequence is stated plainly on the export rather than hidden: **`raised_at` is when the product
first noticed, not when the condition began.** An owner who never opens the screen has no record,
which is true of a paper file in a drawer as well.

### 4 · Acknowledging is an event, never a status flip

`compliance_event` is append-only: `raised`, `acknowledged`, `resolved`, `suppressed`. Suppression
is allowed — an owner may dismiss a finding with a reason — and is a *recorded decision*, not a
deletion. **Advice ignored is still advice given**, and the export shows it that way.

### 5 · Every finding explains, instructs, and stops

Three sentences: what is wrong, what it risks, what to do next. Never a bare statute reference at
somebody who did not ask for one, and **never an opinion about consequences or a quantified
penalty** — the app states the rule, the fact, and the gap. Anything past that is legal advice, and
this product is not qualified to give it.

### 6 · Silence when nothing is wrong

The owner's home shows nothing at all when there are no findings. A compliance card that is always
there, always saying "all clear", is a card people stop seeing — which is the same argument the
locked alert colours rest on.

---

## The rules shipped, each with its instrument

| # | Rule | Instrument | Status | Severity |
|---|---|---|---|---|
| 1 | FSSAI licence expired | FSS (Licensing and Registration) Regulations, 2011 | in_force | critical |
| 2 | FSSAI licence expires within 30 days | as above | in_force | warning |
| 3 | FSSAI licence number malformed | `^[12][0-9]{13}$`, `docs/compliance-rules.md` §A3 | in_force | critical |
| 4 | Licence tier below what turnover requires | FSS (Licensing and Registration) Amendment Regulations, 2026, w.e.f. 1 Apr 2026 | in_force | warning |
| 5 | GSTIN absent or malformed while tax invoices are issued | CGST Rules, Rule 46 | in_force | critical |
| 6 | A tax group in use with no rate effective today | CGST Act s.14 | in_force | critical |
| 7 | A live menu item with no allergen statement | FSS (Labelling and Display) Regulations, 2020 | in_force | warning |
| 8 | Calorie declaration required and absent | FSS (Labelling and Display) Regulations, 2020 | in_force, **conditional** | warning |
| 9 | DPDP consent architecture | DPDP Act 2023, Phase 3 | **notified_not_in_force** | advisory |
| 10 | Service charge levied by default | CCPA guidelines 2022; Delhi HC 2025 | **unsettled** | advisory |

Rules 9 and 10 exist precisely to prove the state machine: neither may ever raise a `critical`, and
`test_only_a_rule_in_force_can_raise_a_critical` asserts it over the whole catalogue.

---

## Not in scope

- **A FoSCoS lookup.** Format validation removes typos; only the registry verifies a licence, and
  nothing in this product may imply a well-formed number is a verified one (`docs/compliance-rules.md`
  §A3).
- **Penalties, notice periods, or any quantified consequence.** Decision 5.
- **A user-authored rule.** Decision 2.
- **Aggregator obligations.** `docs/compliance-rules.md` §C lists them and says why they do not
  apply; a rule that fired on one would be wrong about what this product is.

---

## Acceptance criteria

1. A rule not `in_force` cannot produce a `critical`, asserted over the whole catalogue.
2. Every rule carries an instrument, a commencement, a `checked_on` date and an evaluator.
3. Acknowledging appends an event; the finding's history survives it.
4. A suppressed finding stays in the record with its reason.
5. A finding that clears is resolved rather than deleted, and does not re-raise on the same
   evidence.
6. The export reconstructs what was known when, from the events.
7. The owner's home renders nothing when there are no findings.
8. Every finding carries what is wrong, what it risks, and what to do next.
9. Generic suites 1–5 pass, with victim rows for both tables.

---

## Chunks — two PRs against `feat/m18-compliance`

**A · The catalogue and the findings.** Ten rules, two tables, the evaluator, and the tests that
hold the state machine.

**B · The surface.** Endpoints, the owner's card, the findings list, the export, and the manual
script. Ends with `make check` clean.
