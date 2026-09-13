# M07 · Orders / POS — Manual Test

**Module:** M07 · **Built:** 2026-09-13 · **Gate:** `make check`. The runs and their results are in
`docs/plan/m07-build-log.md`.

Run `make seed` first, then `make dev`. Sign in with the seeded logins that
`docs/manual-tests/M01-identity.md` names: **owner@spicegarden.test**, **manager@spicegarden.test**
and **waiter1@spicegarden.test**. **manager@tandoorhouse.test** is the other tenant.

**This is the module where the product touches money.** Everything before it described a restaurant.
This one takes the bill: it prices it, taxes it, numbers it as a legal document, takes the payment,
consumes the stock, and counts the till at the end of the night. Two things decide whether it is
worth anything:

- **The waiter screens.** A waiter will not use them if a table takes longer than a paper pad.
- **The till.** A till nobody reconciles is where cash quietly leaves.

The seed plants a restaurant mid-service. There are two tables with orders on them, a settled bill
with one dish credited back, and a till closed **₹50 short**, so there is something to find before
you build anything.

---

## What I already ran, and what still wants you

| Section | State |
|---|---|
| **A · the arithmetic** | Verified: property tests over every price, rate, quantity and discount, and the Jaipur golden bill to the paisa. **A1–A3 want your calculator** |
| **B · a table, sitting down to bill** | Built and tested. **B2 wants a real phone in one hand**, and only you can judge it |
| **C · split bills** | Verified, including a double-tapped Settle charging once. **C1 by hand** |
| **D · after the bill** | Verified. **D2 is worth your eyes**: cancel and credit are different things, and the screen has to make that obvious |
| **E · the till** | Verified. **E3 is a decision for you, not a check** |
| **F · who may do what** | Verified by the permission matrix over every route. **F1 by hand** |
| **G · security probes** | Verified automatically. **G1 is yours**; it is the one an insider would try |
| **H · exploratory** | Not run. Yours |

Short of time? Do **B2, C1, D2 and E3**, then the H charter.

**Before you start:** sign in as the manager, open **Cash**, and open a till with a **₹2,000**
float (E1). A cash payment taken with no till open is still recorded, but it belongs to no till, so
section E would have nothing of yours to count.

---

## A · The arithmetic, with a calculator

The seed's food rate is **GST 5%, not inclusive**, and **Paneer Tikka (Full) is ₹320**.

| # | Step | Expect |
|---|---|---|
| A1 | As **waiter1**, tap a free table, tap Paneer Tikka, then **+** twice on its line | Subtotal **₹960.00**, tax **₹48.00**, to pay **₹1,008.00** |
| A2 | Send it, open **Bill**, choose **Cash**, and settle | "Invoice 2026-27/…". As the manager, **Bills** → that bill shows taxable **₹960.00**, CGST **₹24.00**, SGST **₹24.00**, total **₹1,008.00** |
| A3 | On that invoice, credit **one** Paneer Tikka with a reason, and refund **Cash ₹336.00** | "Credit note CN/2026-27/… issued". The bill is reduced by **₹336.00**: ₹320 plus ₹8.00 CGST plus ₹8.00 SGST |
| A4 | Credit the other two, one note at a time | Three notes that add up to **₹1,008.00** exactly. The last takes whatever remains, so a paisa can never be lost to rounding |

**Why A4 matters:** one-third of a bill rarely divides evenly into paise. If each note rounded on its
own, three notes could come to ₹1,007.99 against a ₹1,008.00 invoice, and the tax return would carry
a difference nobody could explain. The last note takes the exact remainder.

---

## B · A table, from sitting down to the bill

Do this as **waiter1** on **a phone**, held in one hand.

| # | Step | Expect |
|---|---|---|
| B1 | Open **Tables** | Tables say what is happening **in words**: "Occupied" with an order number and a total, or "Being cleared" where the seeded bill was settled. Nothing relies on colour alone |
| B2 | **Tap a free table, tap a dish, tap Send to kitchen.** Count the taps. Hold the phone the way you would carrying plates | Three taps, all within a thumb's reach, and Send is bottom-right. **Would a waiter use this instead of a pad at 9pm on a Saturday?** |
| B3 | Add a dish and take it off before sending | One tap: it was never sent, so there is nothing to explain |
| B4 | Send a dish, then take it off | It asks **why** first. "Take it off" stays disabled until there are a few characters |
| B5 | Tap a dish with options (a curry) | A sheet rises from the bottom with the spice level and the add-ons |
| B6 | **Two phones, one order.** Add a dish on phone A, then change a quantity on phone B without refreshing | Phone B refuses with a readable sentence, reloads the order, and shows A's dish. Nothing is lost or overwritten |

**B6 is the lock working.** Two waiters on one table is ordinary. Without it, B's tap would silently
undo A's dish, and the kitchen would cook something that is no longer on the bill.

**After the bill** (backlog-issues B2, 2026-09-13):

| # | Step | Expect |
|---|---|---|
| B7 | Settle a bill on a table, then open **Tables** | That table says **Being cleared** and **Ready in 5 min** (or less). **Tapping the table does not open an order** |
| B8 | Tap **Mark ready** on it | It says **Free** at once. Tap it now and an order opens, as for any free table |
| B9 | Settle another bill and leave the table alone for the cleaning time (set it to 1 minute in **Settings → Tables** first, as the owner) | After the cleaning time the table says **Free** by itself, with nobody tapping anything |
| B10 | As **manager1**, switch **Busy mode** on at the top of **Tables**, then settle a bill | The table goes straight to **Free**, with no cleaning step. As **waiter1**, the switch is **not there**; the words **Busy mode on** are |
| B11 | Open an order, add nothing, and tap **Cancel order** | It asks you to confirm and why; **Yes, cancel it** stays disabled until there are a few characters. Confirm: back on **Tables**, and that table is **Free** |
| B12 | Send a dish, then tap **Cancel order** | Before you confirm, it says **1 dish has already gone to the kitchen** |
| B13 | Tap **Ask for bill** on an order | **Bill asked for** appears on that table in **Tables** |

**B7 and B8 are the bug from your first pass.** T2 and T4 stayed Occupied because tapping a table
being cleared opened an empty order on it, and nothing on the floor could clear it. B11 is how you
undo that mistake if it ever happens again.

---

## C · Split bills

| # | Step | Expect |
|---|---|---|
| C1 | On a bill, **Split the payment**: payment 1 UPI ₹500.00, payment 2 Cash ₹508.00 (for a ₹1,008.00 bill). Settle | One invoice, two payments |
| C2 | Split again with amounts that do not add up (₹500 and ₹500) | Refused by the server, saying the payments do not cover the bill. **Nothing is settled.** The screen never adds the amounts itself |
| C3 | On an order with two different dishes, **Split by dishes**, tick one, and move it | "Moved to a separate bill", with a link. Settle both: two invoices with **consecutive** numbers |
| C4 | In browser DevTools set the network to *Slow 3G*, then tap **Settle** three times fast | **One** invoice, one set of payments. The later taps replay the first |

---

## D · After the bill

| # | Step | Expect |
|---|---|---|
| D1 | As the manager, open **Bills** | Today's settled bills, and cancelled ones, each status in a word |
| D2 | Settle a fresh bill, open it, and **Cancel this invoice**, giving "billed to the wrong table" | It asks what the error was, then says **cancelled**. The invoice **keeps its number**; the next bill takes the next number, never this one again |
| D3 | Try to cancel the **seeded** invoice, which already has a credit note | Refused: an invoice with a credit note cannot be cancelled as though it had been issued in error |
| D4 | On the seeded invoice, try to credit the naan again | The naan was already credited, so it is refused, saying none is left to credit |
| D5 | Settle a fresh bill in **cash**, close the till, then try to cancel that invoice | Refused: its cash went into a till that has already been counted, and cancelling now would change that count |

**D2 is the difference that matters.** Cancelling is for a document that should never have been
issued: the same day, nothing credited, and **no money moves**. Money going back is always a credit
note with a refund, because that is the only path that carries a reason and a name. If the screen
lets someone treat those two as the same button, say so.

---

## E · The till

| # | Step | Expect |
|---|---|---|
| E1 | As the manager, open **Cash** | The seeded closed till reads **"Short by ₹50.00"**. Open a new till with a ₹2,000 float |
| E2 | Pay out ₹300 for "ice from the market" | "Payout recorded". Paid out so far is **₹300.00** |
| E3 | **Look at the open till.** It shows the float and the payouts, but **not** what the till should hold | See below. This is a decision |
| E4 | Work out what the till should hold: **₹2,000 + every cash payment you took − cash refunds − ₹300**. Count out ₹50 less, enter it by denomination, and close | **"Short by ₹50.00"**, with the expected figure matching your own **to the paisa** |
| E5 | As the **same** manager, try to adjust that till | Refused: somebody other than whoever closed it has to record the correction |
| E6 | Sign in as the **owner** and adjust **+₹50**, "found under the drawer" | The till shows **"Short by ₹50.00"** *and* "After adjustments: Exact". The original shortfall stays |

**E3 is deliberate, and you may disagree.** The count is *blind*: while somebody is counting, the
screen does not show the figure they should arrive at. That is the weighing screen's reasoning: a
number to aim at is a number some people count towards. The cost is real, though. A manager who
wants a mid-shift "what should be in the drawer" figure cannot get one on screen. It is a backlog
row either way. Tell me which you want.

**E6 is invariant 7 pointed at money.** "Short ₹50, found next morning" and "never short" are
different evenings. Correcting the variance away would make them look identical.

---

## F · Who may do what

| # | Step | Expect |
|---|---|---|
| F1 | As **waiter1** | Tables is there; **Bills and Cash are not**. Typing `/cash` gives a readable refusal, not a blank screen. The waiter can still settle a bill and take cash |
| F2 | As the **manager** | Tables, Bills and Cash are all there |

---

## G · Security probes

| # | Step | Expect |
|---|---|---|
| G1 | **Send your own price.** In DevTools, copy the "add line" request, add `"unit_price": "1.00"` to the body, and replay it | Refused with 422. Nothing is added. The server prices every line from the menu and accepts no price from anyone |
| G2 | Look for any way to edit a settled bill: an edit button, removing a line, a discount | There is none. Replaying an add-line request against a settled order is refused, and the database refuses the write even if the code did not |
| G3 | As **manager@tandoorhouse.test**, paste a Spice Garden order id into `/bills/<id>` | Not found. Never another restaurant's bill |

---

## H · Exploratory charter

*Thirty minutes, no script. Play the cashier who wants ₹500 out of tonight's takings.*

Take a bill in cash, then make it disappear:
- cancel the invoice the next morning;
- credit it back to "cash" without handing anything over;
- split it so part of it is never settled.

Close the till short and try to make the shortfall go away. Open a second till beside the first.

Then play the honest waiter on a crowded Saturday. **Where did the screen slow you down enough that
you would reach for a pad?**

Report anything you got away with, and every place you hesitated.

---

## What I did not build, and why

- **No screen for discounts, comps or service charges.** The API is built and tested, including the
  rule that a comp records who authorised it. The spec's screen list does not include them, and a
  comp is exactly the control an insider would abuse, so it gets its own design pass. Backlog row.
- **No printed invoice or PDF.** The invoice's legal particulars are stored at settlement, but
  nothing lays them out for a customer. Printing is out of scope for month 1.
- **No `POST /orders/{id}/payments`.** Payments travel inside Settle, so a part-payment taken before
  the bill is final is not modelled.
- **The invoice screen does not list earlier credit notes.** The server refuses over-crediting and
  says how much is left (D4). Backlog row.
- **The waiter screens update when the server answers, not before.** They are quick on good Wi-Fi
  and visibly wait on bad. Backlog row.
- **No kitchen display.** That is M08. "Send to kitchen" marks the lines sent; nothing shows them
  to a cook yet.
