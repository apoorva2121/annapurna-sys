# M13 · Dashboards & Reports — Manual Test

**Module:** M13 · **Built:** 2026-09-18 · **Gate:** `make check`. The runs and their results are in
`docs/plan/m13-build-log.md`.

Run `make seed` first, then `make dev`. Sign in with the seeded logins that
`docs/manual-tests/M01-identity.md` names: **owner@spicegarden.test**,
**manager@spicegarden.test**, **accountant@spicegarden.test** and **waiter1@spicegarden.test**.
**manager@tandoorhouse.test** is the other tenant.

**Read this before you start, or the reports will look broken.** The seed holds a handful of days
of trading, not the 120 days these screens were designed for — the generator that produces those is
**M15**, and it does not exist yet. So every number here will be small, some charts will have two
points, and the variance report will have few lines. **That is the data, not the report.** What you
are judging in this pass is whether the *shape* of each screen is right and whether the numbers you
can check by hand are correct; whether the reports find real patterns is M15's pass, and the
fourteen planted signals are its exit criterion, not this one's.

**The question this module has to answer** is not "are the numbers right" — the tests establish
that, against data built to break them. It is **section C**: would you change what you do on Monday
because of this screen? A correct number nobody acts on is the thing this product exists to
replace.

---

## What I already ran, and what still wants you

| Section | State |
|---|---|
| **A · the money** | Verified: revenue, covers, average bill, and every baseline. **A3 wants your calculator** |
| **B · the variance** | Verified against a fixture with a known gap and a known waste: ₹144 variance, ₹90 explained, ₹54 not. **B4 is the question** |
| **C · would you act on it** | **Not verifiable by any test.** Entirely yours, and the module lives or dies on it |
| **D · the dishes** | Verified: the quadrant, the frozen cost, the advice. **D3 is a judgement** |
| **E · the business day** | Verified: a 01:30 order counts to the previous day in every report. **E1 by hand** |
| **F · CSV** | Verified: the export and the screen agree row for row. **F2 in Excel** |
| **G · who may see what** | Verified by the permission matrix over every route. **G1 and G3 by hand** |
| **I · the waste report** | Verified: the split by stage, the shares within a paisa, and that it agrees with M09's own summary. **I3 is the one for you** |
| **J · drill-through** | Verified: every link is gated on the permission that opens the screen behind it. **J1 by hand** |
| **H · exploratory** | Not run. Yours |

Short of time? Do **C**, then **B4**, then the H charter.

---

## A · The money, with a calculator

| # | Step | Expect |
|---|---|---|
| A1 | As **owner**, open the home dashboard | Today's revenue, covers and open orders, each with **yesterday beside it** — not a bare number |
| A2 | Open **Reports → Sales** | A row per business day, and revenue / covers / average bill each with the previous period beside them |
| A3 | Add up the daily revenue column yourself | It equals the total. If it does not, the rounding is wrong somewhere and I need to know immediately |
| A4 | Check the average bill: total revenue ÷ number of bills | Matches, to the paisa |
| A5 | Look at the payment split | The methods add up to the revenue. A refund reduces its own method rather than appearing separately |
| A6 | Compare a day's figure to what M07's bills screen shows for the same day | The same number. Two screens disagreeing about one day is the worst thing this module can do |

---

## B · The variance — **the report this product exists for**

| # | Step | Expect |
|---|---|---|
| B1 | As **owner** or **accountant**, open **Reports → Food cost variance** | A line per ingredient: what the recipes say was used, what the shelf says was used, the gap, and how much of the gap was logged as waste |
| B2 | Find an ingredient where the two differ | The **variance** is actual minus theoretical — positive means more was used than the recipes say, which is the direction that costs money |
| B3 | Look at the **unexplained** column | Variance minus the waste somebody wrote a reason for. This is the only line in the product that says *this much of your food went somewhere nobody can account for* |
| B4 | **The question.** Imagine this column showed ₹18,000 for a month | Would you know what to do next? If the answer is "no, I'd need to know which dish / which shift / which person", say so — that is the next feature and I would rather hear it now than guess |
| B5 | Log some waste (M09), then reload the variance report | The unexplained figure goes **down** by what you logged. Logging waste does not change what was used; it changes how much of it you can account for |

---

## C · Would you act on it — **this is the module**

Twenty minutes, no steps, no expected results. Open each of the five screens as the owner and
answer three questions in writing:

| # | Question |
|---|---|
| C1 | Which single number on any of these screens would make you do something differently tomorrow? |
| C2 | Which number is on screen that you would never look at? (I will remove it.) |
| C3 | What did you look for that is not here? |

C3 is worth more than everything else in this file. The reports I can imagine are the reports a
developer imagines; the one you go looking for at 11pm on a Sunday is the one that sells this.

---

## D · The dishes

| # | Step | Expect |
|---|---|---|
| D1 | Open **Reports → Dish performance** | Every dish with units, revenue, food cost, margin, rating and where it sits: **star**, **plough-horse**, **hidden gem** or **dog** |
| D2 | Find a dish with a high food-cost percentage | It is a plough-horse if it sells well. The advice beside it suggests checking the portion against the recipe *before* the price — that order is deliberate |
| D3 | Read the advice on three dishes | **Does it read as advice, or as instruction?** It must never read as though the product has decided. If any line feels like it is telling you to remove a dish, tell me — that is the wrong tone and I will change it |
| D4 | Edit a recipe (M04) to make a dish more expensive, then reload this report | **Last week's figures do not move.** The cost is frozen on the bill at settlement, so a recipe change today cannot rewrite last month. This is the single most important behaviour on this screen |

---

## E · The business day

| # | Step | Expect |
|---|---|---|
| E1 | If you can, settle an order after midnight but before 5am | It counts towards the **previous** day in every report — the day the restaurant was still serving |
| E2 | Compare the dashboard's "today" with the sales report's last row | The same day and the same number |

---

## F · Getting it out

| # | Step | Expect |
|---|---|---|
| F1 | On any report, press **Export CSV** | A file downloads, named after the report |
| F2 | Open it in Excel and compare it to the screen | **Row for row, the same numbers.** A CSV that disagrees with the screen is the worst defect a report can have: both look authoritative |
| F3 | Check the decimals in Excel | Money to two places, no scientific notation, no lost trailing zeroes |

---

## G · Who may see what

| # | Step | Expect |
|---|---|---|
| G1 | As **manager**, look for the sales and variance reports | They are **not there**, and the address refuses. The P1 design gives the money to the owner and the accountant; a manager runs the floor |
| G2 | As **manager**, open dish performance and waste | Both work. Operations are the manager's |
| G3 | As **accountant**, open the sales and variance reports | Both work |
| G4 | As **waiter1**, try any report address | Refused with a readable message |
| G5 | As **manager@tandoorhouse.test**, open every report | Their own restaurant's figures only — never Spice Garden's |

---

## I · The waste report

There are **two waste screens in this product on purpose**, and this is the one behind the reports.
M09's (**Waste → Summary**) sits behind `stock.view`, which a chef holds and an accountant does not;
this one sits behind `report.operational.view`, which an accountant holds and a chef does not.
Neither role can reach the other's, so both exist. They must always agree.

| # | Step | Expect |
|---|---|---|
| I1 | As **owner**, open **Reports → Waste** | A total at the top and a line per reason underneath, grouped by where it happened. **Never one number on its own** — the total is the heading, the stages are the answer |
| I2 | Add up the share column | 100%, give or take a paisa. Three equal thirds come to 99.99% and that is arithmetic, not a bug |
| I3 | **The question.** Look at the biggest stage | Does it tell you who to talk to? Receiving is the store manager at the gate, prep is the chef and the batch size, service is portion control. If the biggest line does not suggest a person and an action, tell me |
| I4 | Compare it with **Waste → Summary** (M09) as the **manager**, same dates | The same lines and the same figures. Two waste screens disagreeing would be the worst defect in this module |
| I5 | As **accountant**, open **Reports → Waste**, then try M09's **Waste → Summary** | The report opens; M09's refuses. That is the reason both exist |
| I6 | Export it | A CSV with the stage, the reason, the times, the cost and the share |

---

## J · Drill-through — every figure reaches its rows

Decision 4: *a figure that cannot be opened is a figure nobody trusts the second time it surprises
them.*

| # | Step | Expect |
|---|---|---|
| J1 | On the **variance** report, click an ingredient's name | The stock ledger opens. Its movement history is the rows the variance was computed from |
| J2 | On **dish performance**, click a dish's name | The dish-cost screen opens |
| J3 | On the **sales** report, click a day | The bills screen opens |
| J4 | As **accountant**, look at the same three | The names are **plain text, not links** — an accountant reads the books and does not hold the ledger, the costing screen or the bills. A link that answered "you do not have access to this" would read as a broken product |

---

## H · Exploratory charter — 20 minutes

**Charter:** *Try to make two screens in this product disagree about the same day.*

Ideas: compare the dashboard against the sales report; the sales report against M07's bills; the
variance report against M09's waste summary; a CSV against its own screen; a report for "this week"
against seven single-day reports added up. Change a date range and change it back. Look at a day
with no trading at all.

Any disagreement is a finding, however small. **Two numbers that should match and do not is worse
than one number that is missing**, because the missing one is obvious and the mismatched pair
quietly teaches somebody not to trust either.
