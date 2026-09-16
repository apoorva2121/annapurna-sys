# M10 · Customers, Feedback & Guest App — Manual Test

**Module:** M10 · **Built:** 2026-09-16 · **Gate:** `make check`. The runs and their results are in
`docs/plan/m10-build-log.md`.

Run `make seed` first, then `make dev`. Sign in with the seeded logins that
`docs/manual-tests/M01-identity.md` names: **owner@spicegarden.test**, **manager@spicegarden.test**,
**waiter1@spicegarden.test**. **manager@tandoorhouse.test** is the other tenant.

**This is the first module with a screen you cannot test from a desk.** The guest app runs on a
stranger's phone, over their network, from a QR code printed on paper. Sections C and D need an
actual phone and, ideally, an actual person who has never seen this product — a family member is
perfect, and better than any of us, because they will not know where to look.

Two things here are irreversible or legally shaped, and both want your eye specifically:
**section F** (erasure destroys a person's details and cannot be undone) and **section E** (consent —
built to a standard that does not commence until **13 May 2027**, and which nothing in the product
may describe as current law).

---

## What I already ran, and what still wants you

| Section | State |
|---|---|
| **A · the customer a waiter sees** | Verified mechanically. **A4 is a judgement** |
| **B · the two QR codes** | Verified: a table code opens the menu and nothing else; a bill code opens one bill and dies with it. **B5 wants a phone** |
| **C · the guest app on a real phone** | **Not verifiable by any test.** Entirely yours |
| **D · three taps** | Timed by nobody but you. The module's response rate lives here |
| **E · consent** | Verified: one row per purpose, never pre-ticked, withdrawal as easy as granting. **E4 is the wording** |
| **F · erasure** | Verified: the details go, the money stays, the consent history stays. **F3 is a decision** |
| **G · complaints** | Verified, including that "did they come back" is derived and unwritable. **G4 is yours** |
| **H · who may see what** | Verified by the permission matrix and by suite 5 over every guest route. **H2 by hand** |
| **I · exploratory** | Not run. Yours |

Short of time? Do **C**, then **D**, then **F3**. C and D are the module: a guest app nobody can use
in ten seconds on a bad network collects nothing, and everything downstream — M13's analytics, M17's
fairness figures — is built on what it collects.

---

## A · The customer a waiter sees

| # | Step | Expect |
|---|---|---|
| A1 | As **waiter1**, open **Customers** and then Ravi Kumar | You can. Deliberate: a waiter who cannot see a customer cannot greet one |
| A2 | As waiter1, try to edit him, or to erase him | Refused. Seeing and changing are different permissions |
| A3 | As the manager, add an allergy to somebody, seat them, and look at the kitchen ticket | The allergy is on the ticket. A spice level is **not** — noise on a ticket is how a real allergy gets skimmed past |
| A4 | Read the profile as a waiter would, thirty seconds before greeting somebody | **Your judgement:** is what matters at the top? If you have to scroll to find the allergy, tell me — that is the one line on the screen somebody's health depends on |

---

## B · The two QR codes

| # | Step | Expect |
|---|---|---|
| B1 | Open `/guest.html?t=<a table's slug>` | The menu. No sign-in, no app |
| B2 | From that same session, try to reach the bill | Refused. A table sticker is worth the menu, which is on the wall anyway |
| B3 | Ask for a bill, mint its QR, and open `/guest.html?b=<token>` | That bill, and the three questions |
| B4 | Mint the QR **again** (a reprint), then reload the first phone | Refused. A bill folder left on a cleared table stops being a key the moment somebody reprints |
| B5 | Do B1 and B3 on an actual phone, on mobile data | Both open. **Write down how long each took** |

---

## C · The guest app on a real phone

**Use your own phone, on mobile data, not the office wifi.** That is the network this runs on.

| # | Step | Expect |
|---|---|---|
| C1 | Scan the table QR | The menu, in a browser, with no app to install and no sign-in |
| C2 | Time how long from scan to reading a dish | Under three seconds on mobile data. Write down the number |
| C3 | Look for anything that is not the menu | There is nothing else. No cost, no staff name, no prep time, no admin link. **If you find one, tell me immediately** |
| C4 | Turn on the veg-only filter | Non-vegetarian dishes disappear. **Your call: is one filter enough, or do people want spice level too?** |
| C5 | Open a dish with options | Required questions first, Add disabled until they are answered. A single-choice group is round buttons; a multi-choice group is squares |
| C6 | Photograph the table QR, go home, and scan the photo tomorrow | The menu, still. That is deliberate — the menu is on the wall too |
| C7 | Photograph the **bill** QR and scan it a day later | Refused. A bill code dies with the bill |

---

## D · Three taps

| # | Step | Expect |
|---|---|---|
| D1 | Ask for the bill, scan the QR on it, and rate the meal. Time it from scan to "thank you" | **Under fifteen seconds.** Write down the number |
| D2 | Count the taps after the screen opens | Food, service, would-you-return. **Three.** A fourth is one I have to justify |
| D3 | Submit with no phone number at all | Accepted. Anonymous is the normal path, not a degraded one |
| D4 | Tap Send twice quickly on a slow connection | **One** record, and "thank you" both times — never an error saying you already did it |
| D5 | Try to rate the same meal again from the same QR | The first answers come back, unchanged |
| D6 | Hand the phone to somebody who has never seen it. Say nothing | **This is the test.** Do they finish it without asking you anything? If they ask even one question, tell me which |

---

## E · Consent

| # | Step | Expect |
|---|---|---|
| E1 | On the feedback screen, look at the phone number field before touching anything | Optional, below the ratings, and **every tick is empty**. If any box is pre-ticked, stop and tell me — that is the one thing this module must never do |
| E2 | Tick only "Offers and news", give a number, submit | Recorded. Then, as the manager, open that customer: **marketing on, everything else never asked** — not "off" |
| E3 | On the guest screen, withdraw it | Gone, in one tap, from the same screen. No email, no phone call, no asking a waiter |
| E4 | Read the notice as a customer would | **Your judgement:** is it plain? Does it say what the number is for in words a person uses? `docs/consent-notices.md` has the exact text and a new version is a new section, never an edit |
| E5 | As the manager, look for anywhere the product calls this a legal requirement | **There is nowhere.** These obligations commence 13 May 2027 and the product says nothing that calls them current. If you find a screen that does, that is a defect |

---

## F · Erasure

| # | Step | Expect |
|---|---|---|
| F1 | As the manager, open a customer with a few visits and note the restaurant's total sales for those days | — |
| F2 | Erase them, reading the confirmation carefully first | The name, number, email and preferences are gone. The orders are **all still there** and the sales total has not moved by a paisa |
| F3 | Read the confirmation wording before you press it. **Does it tell you what you are about to destroy, and that the same person coming back tomorrow will be a new customer with no history?** | Your call. It is irreversible, and a confirmation that undersells that is the defect |
| F4 | Look at the consent history afterwards | Still there, with nobody's name on it. That is the record proving the erasure was lawful |
| F5 | Try to erase the same customer again | Refused, readably |

---

## G · Complaints

| # | Step | Expect |
|---|---|---|
| G1 | Open **Complaints** as the manager | Two: one nobody has finished with, one sorted |
| G2 | Try to mark one sorted with the box empty | Refused. A complaint marked sorted with nothing written down is paperwork |
| G3 | Sort one, saying what was done | It leaves the open list once you close it |
| G4 | Read the complaint number aloud, as if to a customer on the phone | **Your judgement:** is "Complaint 2" what you would say? If your restaurant already numbers complaints differently, tell me — it is cheap to change now |

---

## H · Who may see what

| # | Step | Expect |
|---|---|---|
| H1 | Sign in as **waiter1** and open a customer | They can. Deliberate: `docs/customer-experience.md` puts the regular's card on the waiter's screen, and a waiter who cannot see a customer cannot greet one |
| H2 | As waiter1, try to edit that customer, or erase them | Refused. Seeing and changing are different permissions |
| H3 | As waiter1, look for a way to export or download the whole customer list | **There is none, in any role.** The export is one person at a time, on purpose |
| H4 | As **manager@tandoorhouse.test**, search for a Spice Garden customer's number | Not found — the same answer as for a number nobody has |
| H5 | Take the guest token from your phone's browser and try it against a staff URL | Refused. Two applications, not two roles (ADR 0009) |

---

## I · Exploratory charter

**45 minutes, and bring somebody who has never seen this product.**

Sit at a table. Order something. Scan both codes. Rate the meal. Then try to break it: scan
somebody else's bill code, rate a meal twice, give a number and withdraw it, go into a lift and lose
signal halfway through.

**What I want to know, and cannot find out myself:**

- Would a real guest bother? Three taps is my estimate of what people tolerate, not a measurement.
- Does anybody hesitate at the phone number field? Where exactly — the field, the ticks, or the
  notice?
- Does the bill on the phone match the printed one, line for line, every time?
- Would you put this QR on your own tables tomorrow? If not, what is the one thing stopping you?

**Report a failure as:** section and step number · what you expected · what you saw. For C2 and D1,
the number of seconds is the finding — send it even when it passes.
