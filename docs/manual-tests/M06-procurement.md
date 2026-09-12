# M06 · Procurement — Manual Test

**Module:** M06 · **Built:** 2026-09-13 · **Gate:** `make check` clean.

Run `make seed` first, then `make dev`.

**This is the cheapest money in the product.** `docs/waste-model.md` §1: *ordered 50 kg, delivered
47 kg, invoiced 50 kg* happens constantly and nobody notices, because nobody weighs. Receiving loss
runs 1–3% of spend and it is the only waste stage whose fix is a scale and a screen rather than a
change in anybody's habits. One sentence pays for the software:

> Supplier A short-delivered 4.2% across 31 deliveries this quarter — ₹18,400.

That sentence is unanswerable unless ordered, invoiced and received are three separate numbers. The
whole module exists to keep them separate, and **section C is where you find out whether a real
person will keep them separate too.**

---

## What I already ran, and what still wants you

| Section | State |
|---|---|
| **A · the three numbers** | Verified — golden case, arithmetic to the paisa, and 100% coverage on every money path. **A4 wants your calculator** |
| **B · the order's life** | Verified, including every refusal. Nothing here needs you unless something reads oddly |
| **C · the weighing screen** | Built and tested. **This is the section that matters and it is entirely yours** — C2 in particular |
| **D · what it cost** | Verified. **D3 is worth your eyes**: does the confirmation panel tell you something you did not know? |
| **E · the delivery record** | Verified. **E1 is the product's headline. Judge the sentence** |
| **F · who may do what** | Verified by the permission matrix over every route. **F2 by hand** |
| **G · security probes** | Verified automatically. **G2 is yours** — it is the one an insider would try |
| **H · exploratory** | Not run. Yours |

Short of time? Do **C2, D3, E1** and the H charter. Fifteen minutes, and C2 is the one that decides
whether this module is worth anything in a real kitchen.

---

## A · The three numbers, and the fourth

The seed plants a short delivery on purpose, so there is something to find without you building it.

| # | Step | Expect |
|---|---|---|
| A1 | Sign in as **owner**, open **Purchase orders** (`/purchasing/orders`) | Two orders. One **Delivered**, one **Part delivered** |
| A2 | Open **Suppliers** → **Konkan Fresh Produce** → **Delivery record** | A sentence at the top naming the supplier, the number of deliveries, and rupees billed and not delivered |
| A3 | Look at the table underneath | **Billed** and **Arrived** are two separate columns, with different numbers in them |
| A4 | Take one row: multiply (Billed − Arrived) by that item's price by hand | It equals the rupee figure in the last column, exactly |

**A4 is the module in one calculation.** If those two columns were ever collapsed into one
"quantity", the figure in A4 could not exist, and neither could the sentence in A2.

---

## B · An order's life

| # | Step | Expect |
|---|---|---|
| B1 | **Raise an order**: pick a supplier, add two items with quantities and prices, save | It appears as **Draft**, with an ordered value you did not type |
| B2 | Check that value | It is the quantities times the prices. **You never sent it** — the server computed it, because a client that could name its own total would be choosing what its own order cost |
| B3 | Edit the draft: change an item and save | The value changes with it |
| B4 | Press **Send to supplier**, then try to edit it again | Refused, with a sentence: sending fixes the lines, and cancelling and raising another is the way to correct one |
| B5 | Cancel a *sent* order without typing a reason | The button will not fire. A cancellation nobody has to explain is exactly the one that hides an over-order |
| B6 | Cancel it with a reason | Status **Cancelled**, and your reason is shown under the row, permanently |

---

## C · The weighing screen — the section that matters

Open a **Part delivered** or **Sent** order and press **Book in a delivery**.

| # | Step | Expect |
|---|---|---|
| C1 | Read the two input labels | **"What the bill says"** and **"What the scale says"** — and the ordered quantity beside them as plain text |
| C2 | **Imagine you are the store manager at 7am with a driver waiting.** Read those two labels again | See below. This is the test |
| C3 | Type 10000 into the bill and 9000 into the scale | No rupee figure appears anywhere. None |
| C4 | Type something into **Refused on quality** | A reason box appears, and the form will not post until you fill it |
| C5 | Type "about nine kilos" into a weight and post | Refused before it reaches the server, with a sentence |
| C6 | Post a proper delivery | The confirmation panel replaces the form |

**C2 is the whole question and only you can answer it.** A store manager who types the invoiced
figure into both boxes destroys the entire value of this module, and **every test in this project
would still pass.** Two labels that cannot be mistaken for one another are the only defence there
is. So: standing at a delivery door, would you fill those two boxes with two different numbers, or
would you copy the first into the second because it is faster? If the second — say so, and the
labels are wrong, not you.

**C3 is deliberate and worth understanding before you call it a gap.** `docs/waste-model.md` is
explicit that showing the rupee value of a loss *before* it is recorded suppresses honest reporting.
A screen that said *"this weight will flag your supplier for ₹4,200"* while you were holding the
scale would be asking you to choose between an accurate number and an awkward conversation, and
some people will move the number. The figures come after the weights are fixed.

---

## D · What it actually cost

| # | Step | Expect |
|---|---|---|
| D1 | On the confirmation panel, find **On the shelf** | It is what arrived **minus what you refused** — not what arrived, and not what was billed |
| D2 | Open **Stock on hand** | That same figure, and no other, has been added to the item |
| D3 | Go back and book another delivery, this time filling in **Invoice total** and **Of which tax** | The landed cost per unit on the panel is *higher* than the price on the order |
| D4 | Open **Ingredients and recipes** and find that item | Its cost per unit is now the landed figure, and it is marked as coming from a purchase rather than a market estimate |

**D3 is a legal point, not an accounting nicety.** `docs/compliance-rules.md` §A6: a restaurant on
the 5% composition scheme **bears** input GST and cannot reclaim it. So the tax on the invoice is
part of what the stock cost, and a system that stored only the quoted price would understate this
restaurant's food cost by the whole tax rate — on the number the entire product is judged by.

**D4 is the first time this restaurant's food cost stops being an estimate.** Before M06 every price
came from a researched national average (`library/market-rates.yaml`). After one delivery, it comes
from their own supplier's bill.

---

## E · The delivery record

| # | Step | Expect |
|---|---|---|
| E1 | Open a supplier's **Delivery record** | A sentence first, then the table. Biggest loss at the top |
| E2 | Open the record for a supplier who has delivered everything | *"…has delivered everything they billed for in this period"* — a sentence, not a blank screen |
| E3 | Open one for a supplier with no deliveries at all | An explanation of what will appear and how, not "No data" |

**E1 is the product's headline, and the judgement is whether the sentence lands.** Read it as the
owner: does it tell you something you would act on, or is it a statistic? If you would not pick up
the phone after reading it, the sentence is wrong.

---

## F · Who may do what

| # | Step | Expect |
|---|---|---|
| F1 | Sign in as the **chef** | No Purchase orders link, no Suppliers link. Typing `/purchasing/orders` gives a readable refusal, not a blank screen |
| F2 | Sign in as the **accountant** and open Purchase orders | The list is there, and **Raise an order** is there |
| F3 | As the accountant, open a sent order | **No "Book in a delivery" link anywhere** |

**F3 is separation of duties and it is the design's, not an oversight.** `seed/organization.yaml`
gives the accountant `purchase.manage` and withholds `stock.receive`: the person who reconciles what
a supplier billed may raise an order and may never sign for one. In a four-person restaurant one
human will hold both, which is entirely ordinary — so who raised it and who received it are both
stored and both shown. The control is visibility, not a block that would be absurd to enforce.

---

## G · Security probes

| # | Step | Expect |
|---|---|---|
| G1 | Book a delivery with an invoice number, then book the same invoice number again for that supplier | Refused, naming the date the first one was booked |
| G2 | **Try to change a delivery after it is booked.** Look for an edit button, a delete, anything | There is none, anywhere. The API has no such route and the database refuses the write |
| G3 | Sign in as a different restaurant's owner and try a supplier id from this one in the URL | Not found. Never somebody else's row |

**G2 is the control an insider would attack, and it is worth understanding why it is absolute.** A
receipt is the only record of how much arrived. If it stayed editable, the attack is one edit: weigh
47, take 3 home, then change the receipt to say 50 so the invoice reconciles and the variance report
goes quiet. The stock movements would still say 47 and the two records would disagree, with nothing
able to say which had been altered. So the database refuses `UPDATE` and `DELETE` on a goods receipt
outright, exactly as it does on the stock ledger. **A correction is a stock adjustment with a
reason**, which leaves a trail naming who corrected it — strictly better than an editable receipt,
which leaves none.

---

## H · Exploratory charter

*Thirty minutes, no script. Play the store manager who does not want to be caught.*

Try to make the restaurant's own numbers look better than they are. Book a delivery you did not
receive. Record a weight you did not measure. Make a short delivery disappear after the fact. Use
two spellings of one supplier so their record is split in half. Cancel an order that embarrassed
you. Book the same invoice twice and see whether the second one is stopped by something or by
nobody.

Then play the honest one in a hurry: it is 7am, there is a driver waiting and a queue behind him,
and you have four crates to weigh. **How much of this screen would you actually fill in?**

Report anything you got away with, and anything you would have skipped.

---

## What I did not build, and why

- **No idempotency on receiving.** Two taps on "Book it in" for a delivery with *no invoice number*
  will book it twice. With an invoice number the second is refused. `Idempotency-Key` is M07's
  mechanism (`docs/modules.md` puts the table there) and inventing a second one three weeks early
  would be the wrong kind of tidy. In the backlog, to be un-deferred with M07.
- **No credit notes or returns to supplier.** A rejection at the gate is modelled because it happens
  while the driver waits; a credit note three days later is a legal document needing its own table
  and a payables concept this module has none of.
- **No reorder suggestions.** That chain needs M07's sales history; forecasting against seeded data
  would be theatre.
- **Mixed-rate invoices apportion tax pro rata by value**, which is exact for a single-rate invoice
  and an approximation otherwise. Worth asking a pilot restaurant whether their invoices mix rates.
