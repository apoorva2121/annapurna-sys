# M17 · Workload Fairness & Recognition — Manual Test

**Module:** M17 · **Built:** 2026-09-19 · **Gate:** `make check`. Runs and results:
`docs/plan/m17-build-log.md`. Design: `docs/workload-fairness.md`. Decisions: ADR 0011.

Run `make seed`, then `make dev`. Sign in as **owner@spicegarden.test**,
**manager@spicegarden.test**, **waiter1@spicegarden.test** and **cleaner@spicegarden.test**.

---

## Read this first, because this module is different

Every other module in this product is judged by whether it works. **This one is judged by whether
it is fair**, and that is a judgement only a person can make.

`docs/workload-fairness.md` opens with the sentence the whole design is built around:

> **A measurement system aimed at morale can destroy morale if built carelessly.**

You are the test of whether it was built carefully. The question in every section is not "did the
number come out right" — the tests cover that — it is **would you be happy for this screen to be
shown to you about you?**

If the answer is no anywhere, that is the most valuable thing this pass produces, and I would
rather remove the feature than ship it wrong.

---

## What I already ran, and what still wants you

| Section | State |
|---|---|
| **A · the workload screen** | Verified: shares, assists, and the row that carries more than its hours. **A4 is the question** |
| **B · my own figures** | Verified: every role can open it, sentences rather than formulas. **B5 is the question** |
| **C · disagreeing** | Verified: a dispute blocks publication until answered |
| **D · the freeze** | Verified by test: a correction after publication does not move a published score |
| **E · the scheme** | Verified: a volume-heavy scheme is refused with the reason |
| **F · what is never shown** | Verified: no bottom ranking, and below five people nobody sees anybody else |
| **G · exploratory** | Not run. Yours |

Short of time? Do **A4**, then **B5**, then **G**.

---

## A · The workload screen — the primary one

| # | Step | Expect |
|---|---|---|
| A1 | As **owner**, open **Workload** | A row per person: hours, covers, assists, and two shares — of the work and of the roster |
| A2 | Find somebody whose share of the work is above their share of the hours | The row says so **in words**: "Carrying more than their share of the roster" |
| A3 | Look for a points column or a rank | **There is none, on purpose.** This screen exists so a conversation about workload does not have to start with a score |
| A4 | **The question.** Look at the busiest row | Is your first thought *"I should change the rota"* or *"that person should slow down"*? The screen is built for the first. If it reads as the second, tell me — that is the wrong screen and I will change it |

---

## B · My own figures

| # | Step | Expect |
|---|---|---|
| B1 | As **cleaner** — the role with the fewest permissions in the product — open **My performance** | It opens. Every role can see their own figures, always, and it is not a setting anybody can change |
| B2 | Read the metric rows | Sentences: "You served 214 covers", "12 people rated their visit". Not a formula and not a weight table |
| B3 | Find "How late the kitchen ran" | It is shown **and** it says it counts for nothing. That is deliberate: it is what makes a low score explainable instead of an accusation |
| B4 | Read the line at the bottom | "These figures are used for rewards and for fairer rosters. Nothing else reads them." **If that is not true, tell me** — it is a promise made in the product |
| B5 | **The question.** Imagine this is your screen, about your work | Does it read as feedback, or as a verdict? That single distinction is what ADR 0011 says decides what this feature is |

---

## C · Disagreeing with it

| # | Step | Expect |
|---|---|---|
| C1 | As **waiter1**, on My performance, write something under "Something not right?" | It sends |
| C2 | As **owner**, try to publish that period | **Refused**, naming how many challenges are unanswered |
| C3 | Answer the challenge — accept it, or decline it with a reason | It is recorded with your name on it |
| C4 | Publish again | It works |
| C5 | Try to dispute somebody *else's* figures | Refused. A challenge is raised by the person whose figures they are |

---

## D · The freeze

| # | Step | Expect |
|---|---|---|
| D1 | Publish a period and note somebody's points | — |
| D2 | Correct a clock time inside that period (M12) | The roster changes |
| D3 | Look at the published period again | **The points have not moved.** A later correction must never rewrite the basis on which a bonus was paid |
| D4 | Try to publish the same period twice | Refused |

---

## E · The scheme

| # | Step | Expect |
|---|---|---|
| E1 | As **owner**, create a scheme with the suggested weights | Accepted |
| E2 | Try one where volume is weighted above accuracy and rating combined | **Refused, with the reason in words**: it pays people to rush |
| E3 | Try giving "how late the kitchen ran" a weight | Refused: it is not something a person controls |
| E4 | As **manager**, try to create a scheme | Refused. It decides what the restaurant pays people to do |

---

## F · What is never shown

| # | Step | Expect |
|---|---|---|
| F1 | As **manager**, open the team view with fewer than five scored people | You see **only your own row**. With three waiters, naming the top two names the third |
| F2 | With five or more | The top contributors and your own row — never a full ordered list |
| F3 | Look for anybody's position on a team screen | There is none. Only your own screen tells you where you came, and only about you |

---

## G · Exploratory charter — 25 minutes

**Charter:** *Try to use this feature to make somebody's life worse.*

That is the real test. Try to: find a bottom ranking; see somebody else's score without the team
permission; publish over an unanswered dispute; make an attendance figure punish approved leave;
get a score to move after it was published; find a screen that shows a number without saying what
it means.

**Every one of those that succeeds is a defect I want to hear about today.** And if you find a way
to use this feature punitively that the product does not prevent, that is worth more than all the
other findings put together — `docs/workload-fairness.md` says software cannot fully prevent it,
and the least we can do is know where the gaps are.
