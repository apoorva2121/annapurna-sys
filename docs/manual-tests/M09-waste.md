# M09 · Waste — Manual Test

**Module:** M09 · **Built:** 2026-09-16 · **Gate:** `make check`. The runs and their results are in
`docs/plan/m09-build-log.md`.

Run `make seed` first, then `make dev`. Sign in with the seeded logins that
`docs/manual-tests/M01-identity.md` names: **owner@spicegarden.test**,
**manager@spicegarden.test**, **kitchen1@spicegarden.test** (a chef) and
**waiter1@spicegarden.test**. **manager@tandoorhouse.test** is the other tenant.

**This module has exactly one acceptance criterion that matters, and you are the only person who
can test it.** `docs/waste-model.md`: *"If logging waste is slow, it doesn't get logged, and the
whole module is fiction."* Everything else here — the cost arithmetic, the paired ledger movement,
the approval split — is verified automatically and is worth nothing if a cook will not use the
screen.

So section B is the module. **Time yourself. On a phone. Standing up.** Over ten seconds is a fail,
and the number you get is the finding, whatever it is.

The seed plants waste across all four stages over the last few days, including one event awaiting
approval and one day with nothing logged at all — so the summary opens on something real and you
are not asked to build the problem before you can see it.

---

## What I already ran, and what still wants you

| Section | State |
|---|---|
| **A · the money** | Verified: the cost comes from the batches FEFO took it from, to the paisa, including waste spanning two batches at different prices. **A2 wants your calculator** |
| **B · ten seconds** | **Not verifiable by any test.** Entirely yours, and the module lives or dies on it |
| **C · what the screen refuses to tell you** | Verified mechanically — no rupee figure renders before Log is pressed. **C2 is a judgement** |
| **D · the ledger** | Verified: never an event without its movement, in either direction. **D1 by hand** |
| **E · approval** | Verified, including that an approver is never the person who logged it. **E3 is yours** |
| **F · the report** | Verified: split by stage, shares add to a hundred. **F2 is the question the module exists to answer** |
| **G · who may do what** | Verified by the permission matrix over every route. **G1 by hand** |
| **H · exploratory** | Not run. Yours |

Short of time? Do **B**, then **F2**, then the H charter. B cannot be recovered by any amount of
automated testing, and F2 is the only way to know whether the report is worth reading.

---

## A · The money, with a calculator

The seed's paneer costs **₹0.36 per gram** — ₹360 a kilo.

| # | Step | Expect |
|---|---|---|
| A1 | As **kitchen1**, log **½ kg** of paneer, reason **Over-preparation** | After logging: **₹180.00** |
| A2 | Work it out yourself: 500 g × ₹0.36 | ₹180.00. If the screen says ₹0.18 the unit was not converted, which is the defect that once made cabbage cost ₹40 a gram — tell me immediately |
| A3 | Open **Stock → On hand** and note the paneer figure, then log ¼ kg more and look again | Down by exactly **250 g**. Logging waste takes it off the shelf; it is not a note |
| A4 | Log waste of an item you know has **no stock left** | It still records, and on-hand goes negative. Deliberate — a kitchen that cannot log the waste in front of it stops logging |

---

## B · Ten seconds

**Use a phone. Stand up. Use one hand. Time it from tapping Log waste to seeing the cost.**

| # | Step | Expect |
|---|---|---|
| B1 | Time yourself logging one item, one quantity, one reason | **Under ten seconds.** Write down the actual number |
| B2 | Do it four more times with different items and reasons | Still under ten. If it creeps up, tell me which step is slow — the item list, the presets, or finding the reason |
| B3 | Count your taps | Should be **three**: item, quantity, reason. A fourth is a tap I have to justify |
| B4 | Try it one-handed while holding something in the other hand | Every button takes the press first time. If you miss one, tell me which |
| B5 | Look at the quantity buttons. Are ¼, ½, 1, 2 the right four? | Your call. If a kitchen actually throws away "one tray" or "one container", the presets are wrong and it is cheap to change now |
| B6 | Is the item you want near the top, or do you hunt for it? | Today the list is unordered. If you hunt, that is a finding and the fix is to sort by what gets wasted most |

**B is the section only you can do.** A test can assert there is no text box. It cannot tell me
whether a cook standing at a bin at 9pm will actually use this instead of not bothering.

---

## C · What the screen refuses to tell you

| # | Step | Expect |
|---|---|---|
| C1 | Start logging. Before you pick a reason, look for any rupee figure anywhere on screen | There is none. Deliberate: `docs/waste-model.md` says showing the value before suppresses honest reporting, and a figure on screen while somebody is deciding is one some people record towards |
| C2 | Now finish, and read the cost that appears | **A judgement for you:** does it read as teaching or as an accusation? It should make somebody think "I should batch less", not "I am in trouble". If the wording lands wrong, people stop logging and the module dies quietly |
| C3 | Look for an Undo | There isn't one. The waste happened; unmaking the record would be unmaking the number. Correcting a mistake is a stock adjustment, which stays visible |

---

## D · The ledger

| # | Step | Expect |
|---|---|---|
| D1 | Log waste, then open **Stock → On hand** and the item's history | One movement of type `wastage`, matching the quantity, referencing the event |
| D2 | As the manager, look at the waste summary and then at on-hand | The two agree about how much left the shelf. They are one transaction: there is no state where a report shows waste that the stock book never saw |
| D3 | Log the same waste twice quickly (tap Log twice on a slow connection if you can) | **One** record, not two. Double-booked waste is a second consumption and a food-cost figure wrong all month |

---

## E · Approval

| # | Step | Expect |
|---|---|---|
| E1 | As **kitchen1**, log waste with reason **Expired** | Logged, and marked as needing a manager to check it |
| E2 | Still as kitchen1, try to approve it | You cannot. The people who log most of the waste do not sign it off — that is the whole point of approval |
| E3 | As the **manager**, approve it | Approved, with your name and the time. **Your judgement:** is the approval worth the friction? It is the only control standing between an expensive reason code and somebody logging theft as waste. If it is too slow to be used, say so |
| E4 | As the manager, log waste with reason **Expired** yourself, then try to approve your own | Refused. One person cannot be both people |

---

## F · The report

| # | Step | Expect |
|---|---|---|
| F1 | Open **Waste** as the manager | Split by stage — At the door, In storage, In prep, In service — with a share per row. The shares add to **100%** |
| F2 | Read it as an owner would. **Does it tell you what to do on Monday?** | This is the question the whole waste model exists to answer. `docs/waste-model.md` wants the report to say "fix the makhani batch size and you recover ₹9,000/month". If it reads as a number without an action, tell me what is missing — that gap is M13's brief |
| F3 | Check that **prep** is the biggest line | It should be. The model says prep is 4–8% of food cost, the biggest and the least measured. If the seed makes the stages look level, the demo is teaching the wrong thing |
| F4 | Look for staff meals and manager comps in the report | They are **not there**, deliberately. Indian restaurants feed staff; counted as waste it looks like theft and poisons every variance number |

---

## G · Who may do what

| # | Step | Expect |
|---|---|---|
| G1 | Sign in as **waiter1** and look for Log waste on the home screen | Not there. Waste is a kitchen and storeroom event; a dish a customer sent back is recorded by whoever takes it off the bill |
| G2 | As waiter1, type `/waste` into the address bar | Refused, with a readable message rather than a blank screen |
| G3 | As **kitchen1**, try to add a new reason | Refused. A reason carries the stage every report groups by, so inventing one changes what the restaurant's numbers mean — it sits with the tax rates |
| G4 | As **manager@tandoorhouse.test**, open the waste summary | Tandoor House's own waste and none of Spice Garden's |

---

## H · Exploratory charter

**30 minutes. Pretend it is the end of a Saturday service.**

Throw things away for real — or pretend to — and log every one as you go. Log a tray of gravy. Log
a returned dish. Log something you have no stock of. Log the same thing twice by accident. Let
somebody else log while you are logging.

**What I want to know, and cannot find out myself:**

- Would you actually do this during service, or only at close? If only at close, the module is
  half of what it should be and the presets are the wrong design.
- Does the cost shown afterwards change what you do next time, or do you stop reading it?
- Is "the stage" a thing a kitchen thinks in, or is it a category imposed from outside? The entire
  report rests on those four words meaning something to the people using them.
- After a week of this, would an owner trust the number? That is the only measure that counts: a
  variance figure nobody trusts is cover for everything it was built to expose.

**Report a failure as:** section and step number · what you expected · what you saw. For section B,
the number of seconds is the finding — send it even when it passes.
