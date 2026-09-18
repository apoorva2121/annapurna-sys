# M18 · Compliance & Risk Alarms — Manual Test

**Module:** M18 · **Built:** 2026-09-19 · **Gate:** `make check`. Runs and results:
`docs/plan/m18-build-log.md`. Rules: `docs/compliance-rules.md`. Spec:
`docs/modules/M18-compliance-spec.md`.

Run `make seed`, then `make dev`. Sign in as **owner@spicegarden.test**,
**manager@spicegarden.test**, **accountant@spicegarden.test** and **waiter1@spicegarden.test**.

---

## Read this first, because this module can be wrong in a way the others cannot

Every other module in this product is judged by whether it does what it says. **This one is judged
by whether what it says is true** — about Indian law, to somebody whose licence depends on it.

`docs/compliance-rules.md` opens with the sentence this module was built under:

> **Never fill an Indian rate, threshold or commencement date from memory** — research returned
> stale-but-confident law three times in one session.

A confidently wrong warning is worse than no warning. An owner who acts on a false alarm once will
ignore the true one after it. So the question in every section below is not only *"did the right
thing appear"* — it is:

**If an inspector were standing next to you, would you be comfortable showing them this screen?**

Two things follow from that, and they are what most of this pass is about:

1. **Nothing here should ever say something is required when it is not.** Two of the ten rules are
   about law that is not in force today. They must say so in words, on the screen, above their
   citation.
2. **Nothing here should be noisy.** A compliance screen that shouts at a restaurant that has done
   nothing wrong is a compliance screen nobody opens.

---

## What I already ran, and what still wants you

| Section | State |
|---|---|
| **A · a clean restaurant** | Verified by test: the card renders nothing at all when nothing is outstanding |
| **B · the findings** | Verified: each rule fires on its own condition and not on anything else |
| **C · the citations** | Verified by test: every finding carries an instrument and a checked-on date. **C3 is the question** |
| **D · what is not law today** | Verified by test: no rule that is not in force can be critical. **D2 is the question** |
| **E · acting on one** | Verified: acknowledging, suppressing with a reason, and the refusal without one |
| **F · the export** | Verified: the note, the findings, and every rule that found nothing |
| **G · who may see and who may decide** | Verified: a manager reads and cannot dismiss; the floor sees neither |
| **H · exploratory** | Not run. Yours |

Short of time? Do **C3**, then **D2**, then **H**.

---

## A · A clean restaurant

| # | Step | Expect |
|---|---|---|
| A1 | As **owner**, open **Today** on a freshly seeded database | Look at the dashboard as a whole first |
| A2 | Look for a compliance card | If the restaurant is clean, **there is nothing there at all**. No green tick, no "0 issues", no score |
| A3 | Open **Compliance** from the header | "Nothing to act on. Everything checked came back clear." |

> **Why this matters.** A widget that always shows something trains its reader to skim past it. If
> you find yourself wanting a green tick here, say so — but the argument against it is that the day
> this module has something real to say, you will skim past that too.

---

## B · The findings

Use **Settings → Restaurant** to create each condition, then reopen **Compliance**.

| # | Step | Expect |
|---|---|---|
| B1 | Set the FSSAI expiry to yesterday | "Act on this" — the licence has expired |
| B2 | Set it to **today** | **Nothing.** A licence valid *to* a date is valid on it |
| B3 | Set it 20 days out | "Worth fixing" — it expires soon |
| B4 | Set it 60 days out | Nothing |
| B5 | Clear the FSSAI number entirely | **One** finding, not three. Three alarms about one absent field would read as a broken product |
| B6 | Clear the GSTIN while the restaurant is on the regular scheme and has issued bills | "Act on this" — Rule 46 requires it on a tax invoice |
| B7 | Switch the restaurant to **composition** | The GSTIN finding goes. A composition dealer does not issue a tax invoice |
| B8 | Add a menu item with no allergen statement | "Worth fixing", naming how many items |
| B9 | Leave a dish without a calorie figure | **Nothing**, for a single restaurant on a State licence. The declaration binds a Central Licence holder or a chain of ten or more |

> **B9 is the shape of the whole module.** A rule that fires at everybody is a rule everybody turns
> off. If you can find a rule here that fires at a restaurant it does not bind, that is a defect.

---

## C · The citations — the heart of the pass

| # | Step | Expect |
|---|---|---|
| C1 | Open any finding | Under it: where the rule comes from, when it came into force, and **when that citation was last checked** |
| C2 | Read the "first detected" line | It says this is when the *system noticed*, which may be later than when the condition started |
| C3 | **Pick one finding and look the instrument up yourself.** | **Is what the product says about it true?** |

> **C3 is the most valuable thing in this pass.** Everything else is testable by machine. Whether
> the FSS (Labelling and Display) Regulations 2020 actually say what this screen says they say is
> not, and I would rather find out from you than from an inspector. If any citation is wrong, stale,
> or overstated, that is the single most important defect this module can have.

---

## D · What is not law today

| # | Step | Expect |
|---|---|---|
| D1 | Find the **DPDP** advisory (it appears once customers are on file without consent) | "For information". Its first line says **notified, but not in force yet — this is not law today** |
| D2 | Read it as an owner would. | **Could you come away from this thinking you must do something now?** |
| D3 | Find the **service charge** advisory (configure a service charge rate) | "For information", and the text says a Delhi High Court judge upheld the CCPA guidelines in March 2025 **with an appeal pending** |
| D4 | Look for any finding marked "Act on this" whose rule is not in force | There is none, and there structurally cannot be |

> **D2 is the question.** The distinction between *in force*, *notified but not in force*,
> *unsettled* and *unverified* is the thing this module must never blur. If the wording reads as an
> instruction rather than as information, tell me — it is a wording defect and it is serious.

---

## E · Acting on one

| # | Step | Expect |
|---|---|---|
| E1 | As **owner**, "Mark as seen" on a finding | It stays on the list, marked. Only fixing the condition removes it |
| E2 | Reopen the screen | Still marked as seen. The count of things to look at has gone down by one |
| E3 | "Set aside…" without typing a reason | The button will not submit |
| E4 | Set one aside **with** a reason | It stays on the list, marked, with your reason recorded |
| E5 | Read the hint above the reason box **before** you type | It tells you the reason stays on the record and that setting aside does not remove it from the export |
| E6 | Now actually fix the underlying condition and reopen | The finding goes. Check **Everything ever raised** — it is there, resolved, not deleted |

---

## F · The export

| # | Step | Expect |
|---|---|---|
| F1 | Click **Download the record** | A CSV |
| F2 | Open it. Read the first row | A note saying each finding is dated when the system detected it, and that rules not "in_force" are shown for information |
| F3 | Scroll past the findings | A section: **rules checked and found nothing**, listing every remaining rule with its instrument |
| F4 | Compare it against the screen | Same findings, same words, same dates |

> **Why F3 exists.** *"We checked these ten things"* is a different claim from *"here are three
> problems"*, and it is the one an inspection is interested in.

---

## G · Who may see, and who may decide

| # | Step | Expect |
|---|---|---|
| G1 | As **manager**, open Compliance | You can read every finding |
| G2 | As **manager**, look for "Mark as seen" or "Set aside" | **They are not there.** A manager acts on the restaurant; deciding a licence warning does not matter is the owner's |
| G3 | As **accountant** | Reads, cannot act |
| G4 | As **waiter**, look in the header | No Compliance link. Try `/compliance` directly — refused |

---

## H · Exploratory charter — 25 minutes

**Charter:** *Try to make this product tell a restaurant something untrue about Indian law.*

Try to: make a rule fire at a restaurant it does not bind; make an advisory read like an
obligation; find a finding with no citation, or with a citation whose `checked_on` date predates
the instrument; get a critical out of a rule that is not in force; make the screen say something
the export does not; suppress a finding and find it gone from the record; find a threshold or a
date anywhere in the product that you cannot trace to an instrument.

**Every one of those that succeeds is a defect I want to hear about today.** And if you find a
place where the product asserts something about Indian law that you cannot verify from the citation
it gives you, that is worth more than all the other findings put together — it is the exact failure
`docs/compliance-rules.md` was written to prevent.
