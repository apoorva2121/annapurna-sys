# M08 · Kitchen / KOT — Manual Test

**Module:** M08 · **Built:** 2026-09-16 · **Gate:** `make check`. The runs and their results are in
`docs/plan/m08-build-log.md`.

Run `make seed` first, then `make dev`. Sign in with the seeded logins that
`docs/manual-tests/M01-identity.md` names: **owner@spicegarden.test**,
**manager@spicegarden.test**, **waiter1@spicegarden.test** and **kitchen1@spicegarden.test**.
**manager@tandoorhouse.test** is the other tenant.

**This is the first module whose test cannot be done at a desk.** Everything before it could be
checked by reading a screen. This one is a wall tablet read from two metres, through steam, by
somebody wearing a glove, and the only way to know whether that works is to stand two metres away
and try. `docs/ui/conventions.md` calls the KDS "the one people get wrong", and it is not wrong
about a colour or a font — it is wrong when a chef looks up, cannot tell which ticket is late, and
goes back to shouting.

Two questions decide whether this module is worth anything:

- **Can you work from it without walking to it?** If you have to approach the screen to read a
  ticket, it has failed, however correct the data is.
- **Does it tell you when it has stopped being true?** A display that silently freezes is worse
  than one that is obviously broken, because the kitchen keeps believing it.

---

## What I already ran, and what still wants you

| Section | State |
|---|---|
| **A · a round through the kitchen** | Verified: 17 endpoint tests over every transition, both permissions and the refusals. **A1–A3 by hand** |
| **B · two metres** | **Not verifiable by any test I can write.** Entirely yours, and the most important section here |
| **C · when the network goes** | Verified: a client that misses three events and reconnects receives all three. **C1 wants you to actually pull the cable** |
| **D · served belongs to the floor** | Verified. **D2 is the one to think about**, not just check |
| **E · a remake** | Verified. **E2 is a judgement about wording** |
| **F · who may do what** | Verified by the permission matrix over every route. **F1 by hand** |
| **G · security probes** | Verified automatically, including a cursor from another restaurant's stream. **G1 is yours** |
| **H · exploratory** | Not run. Yours |

Short of time? Do **B (all of it), C1 and D2**, then the H charter. B is the section that cannot be
recovered by any amount of automated testing.

**Before you start:** open the kitchen display on the largest screen you have, put it where a
kitchen screen would go, and **stand back from it**. Reading this section from a laptop on your
desk will tell you nothing.

---

## A · A round through the kitchen

As **waiter1** on a phone, and **kitchen1** on the wall screen. Two people, or two browsers.

| # | Step | Expect |
|---|---|---|
| A1 | As waiter1, open table **T6**, add **two dishes from different stations**, and Send | On the kitchen screen, **two tickets appear within a second**, one per station, without touching the screen |
| A2 | On the kitchen screen, press **Seen it**, then **Start cooking**, then **Ready** | Each press moves the ticket on. The elapsed time keeps counting throughout |
| A3 | Back as waiter1, add **one more dish** to the same table and Send again | A **third ticket** appears. The first two are untouched — same numbers, same clocks. This is the module's central decision: a second send is a second piece of paper, not an edit to the first |
| A4 | On the kitchen screen, open a ticket and press **This dish is ready** on one dish only | The dish is marked, and the **ticket does not** go ready. It goes ready when the last dish does |

---

## B · Two metres

**Stand two metres from the screen.** Do not lean in. If you cannot answer a question from there,
the answer is "fail" and the step number is what I need.

| # | Step | Expect |
|---|---|---|
| B1 | From two metres, read the **order number** on any ticket | Readable without moving. It is the thing you look for first, and it is sized for that |
| B2 | From two metres, name **which ticket is oldest** | Obvious without reading any clock. The rail is oldest-first and worked from the top |
| B3 | Wait for a ticket to pass its target (or add a dish with a long prep time) | It says **LATE** in a word, has a red edge, and its clock is red. Three signals, because one of them is colour and a lot of kitchen staff cannot rely on colour |
| B4 | **Put a glove on** and press the buttons | Every button takes the press first time. If you miss one, tell me which |
| B5 | Look at a ticket with a modifier ("no onion") and one with a special instruction | Both stand out from the dish name. These are what send a dish back when they are missed |
| B6 | Breathe on the screen, or hold it at the angle a real one would sit at | Still readable. Not a joke: the contrast has to survive a screen that is never clean |

**B is the section only you can do.** A test can assert that a font is 40px. It cannot tell me that
a chef looks up mid-service and knows what to cook.

---

## C · When the network goes

| # | Step | Expect |
|---|---|---|
| C1 | With the kitchen screen open, **turn the wifi off** on that device | Within a few seconds a **banner** says it is not live and that what is on screen may be out of date. It does not clear itself and it does not hide |
| C2 | While it is offline, send **two more orders** from the waiter's phone | Nothing on the kitchen screen, and it still says so |
| C3 | Turn the wifi back on | The screen catches up **on its own** — both missed orders appear, without a refresh. This is the whole point of the module's design |
| C4 | Reload the kitchen screen entirely (F5) | The rail is the same. Nothing was lost and nothing is doubled |

---

## D · Served belongs to the floor

| # | Step | Expect |
|---|---|---|
| D1 | On the kitchen screen, look for a way to mark a dish **served** | There isn't one, anywhere. Deliberate |
| D2 | As waiter1, open the order and mark it **served** | The ticket leaves the kitchen rail. **Think about this one rather than just checking it**: the kitchen says when food is ready, the floor says when it reached a table, and the gap between the two is a number a manager can act on. If that split feels wrong to you in a real kitchen, say so now — it is cheap to change today and expensive in three modules' time |
| D3 | Take a dish off an order that has already gone to the kitchen (with a reason) | It disappears from the kitchen screen **immediately**. A kitchen still cooking a cancelled dish is the failure this module exists to prevent |

---

## E · A remake

| # | Step | Expect |
|---|---|---|
| E1 | On the kitchen screen, open a ticket, press **Send it back**, give a reason, submit | A **new ticket** appears, marked REMAKE, with its own clock starting at zero. The original dish keeps the reason on it |
| E2 | Read the wording on the remake form | It should read as recording what happened, not as blaming whoever cooked it. If it reads like an accusation people will stop using it and the data dies. **Your call on the wording** |
| E3 | Try to submit a remake with the reason left empty | Refused. The reason is the whole value of recording a remake |
| E4 | Note that nothing asks you to log waste | Correct and deliberate. A dish sent back for being cold may be reheated rather than binned; M09 offers the link and a person decides |

---

## F · Who may do what

| # | Step | Expect |
|---|---|---|
| F1 | Sign in as **waiter1** and open the kitchen display | It opens. A waiter may watch the kitchen |
| F2 | As waiter1, try to press **Seen it** or **Ready** on a ticket | Refused. The floor watches the kitchen and does not drive it — seeing that table six's mains are still cooking is information; declaring them ready is a way to make the numbers look better |
| F3 | Sign in as the **accountant** and go to `/kitchen` by typing the address | Refused, with a readable message rather than a blank screen |

---

## G · Security probes

| # | Step | Expect |
|---|---|---|
| G1 | As **manager@tandoorhouse.test**, open the kitchen display | Tandoor House's own tickets and **none of Spice Garden's**, on the rail and on the live stream both |
| G2 | Copy a ticket's address from one restaurant and open it signed in as the other | Not found. Not "forbidden" — the other restaurant's tickets do not exist as far as this one is concerned |
| G3 | As the chef, press **Ready** on a ticket twice | The second press is refused with a message saying where the ticket is. There is no way to move a ticket backwards, and no delete anywhere in this module |

---

## H · Exploratory charter

**45 minutes. Pretend it is Saturday at 8pm.**

Send six orders in three minutes across two tables. Let some go late. Remake one. Cancel a dish
mid-cook. Turn the wifi off while doing it. Have somebody else press things on the waiter's phone
at the same time.

**What I want to know, and cannot find out myself:**

- At what point does the rail become unreadable? Six tickets? Twelve? What breaks first — the
  reading, or the finding?
- Does the elapsed time make you act, or does it become wallpaper you stop seeing?
- Is "one button, the next step" right, or does a real kitchen skip steps — and if it does, which
  ones, and would you rather press fewer buttons or keep the measurement?
- Would you trust it enough to take the paper tickets away? That is the real question, and it is
  the only one that matters.

**Report a failure as:** section and step number · what you expected · what you saw. A photograph
of the screen from two metres is worth more than a description for anything in section B.
