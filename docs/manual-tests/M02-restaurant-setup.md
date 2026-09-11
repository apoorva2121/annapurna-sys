# M02 · Restaurant Setup — Manual Test

**Module:** M02 · **Est. time:** 30 min · **Tester:** you · **Environment:** local Compose

---

## What I already ran, and what still needs you

I drove the API and the browser through the mechanical steps before handing this over, so your time
goes on the parts a script cannot do. **This is information, not permission to skip.** The last
three defects in this module were found by doing exactly these steps by hand *after* every automated
check was green — including one where the entire feature was unreachable in the demo data.

| Section | State |
|---|---|
| **A · happy path** | Verified A1–A4 and A9–A12 against the API. **A5–A8 (the floor plan, in a browser) still want a human** — reordering and deactivation are where a wrong answer looks right. |
| **B · validation** | B1–B7 verified against the API. **B8 wants your eyes**: are the refusals readable, or do they read like a developer wrote them? |
| **C · permissions** | C1 and C2 verified. **C3 (the manager) still wants a human** — it is the decision the spec argued about. |
| **D · security probes** | D1 and D2 verified against the API. **Please still do D1 yourself.** It is the one failure that stops everything. |
| **E · the business day** | Not run in a browser. **Entirely yours** — E1 is the single most valuable step in this script. |
| **F · switching branch** | Verified against the API. **F1–F3 want a browser**, because the whole point is what a person sees. |
| **G · exploratory** | Not run. **Entirely yours**, and the highest-value ten minutes here. |

Short of time? Do **E1, D1, A5–A8, C3, F2** and the G charter. About twelve minutes, and it covers
everything I could not.

---

## Preconditions

```
make dev          # api, db and web; wait for all three
make migrate      # 0004, 0005 and 0006 are new in this module
make seed         # idempotent, safe to re-run
```

Open **http://localhost:5173**. All logins use password `Staging#2026`.

| Login | Role | Restaurant |
|---|---|---|
| `owner@spicegarden.test` | owner | Spice Garden — Koregaon Park |
| `admin@spicegarden.test` | admin | Spice Garden — Koregaon Park |
| `manager@spicegarden.test` | manager at Koregaon, **waiter at Baner** | both branches |
| `waiter1@spicegarden.test` | waiter | Spice Garden — Koregaon Park |
| `manager@tandoorhouse.test` | manager | Tandoor House — Baner *(the other tenant)* |

**What the seed now builds that it did not before:** the floor (2 dining areas, 14 tables), 3
kitchen stations, 2 tax rates, a **second Spice Garden branch**, and Vikram's second posting there.
The second branch is deliberately **empty** — no areas, no tables. That is a real state the product
meets on day one of onboarding, and F3 is where you look at it.

---

## A · Happy path

| # | Step | Expect |
|---|---|---|
| A1 | Sign in as **owner**. Open **Settings** | Timezone `Asia/Kolkata`, currency `INR`, day starts `05:00` |
| A2 | Read the sentence under *The business day starts at* | *"An order at 01:30 am on Tuesday counts towards Monday's sales."* |
| A3 | Change the FSSAI number, Save | Green "Settings saved." The value persists on reload |
| A4 | Open **Floor plan** | Two areas — **AC Hall**, then **Terrace**, in that order |
| A5 | Press **↓** on AC Hall | The two swap. Reload: the new order holds |
| A6 | Select **Terrace** | The table list below changes to Terrace's tables |
| A7 | Add a table `T99`, 4 seats, in Terrace | Appears in the list, status **free** |
| A8 | Set `T99`'s status to **reserved** | Saves immediately. Reload: still reserved |
| A9 | Open **Kitchen stations** | tandoor, main_kitchen, chinese |
| A10 | Rename *Tandoor* to *Tandoor & Grill*, press Rename | Saves. The **code stays `tandoor`** |
| A11 | Open **Tax rates** | GST 5% and GST 18%, both marked **Current** |
| A12 | Press **Replace this rate** on GST 5%, name it *GST 12%*, rate 12, start a month out, Add | Two rows: the old one now **Superseded** with an end date one day before the new one starts |

**A12 is the one to look at properly.** The old rate is still listed, still readable, with its
period closed. That is the entire design: an invoice from last month cites a rate that must still
be there to cite.

---

## B · Validation

| # | Step | Expect |
|---|---|---|
| B1 | Settings → timezone `Asia/Kolkta` (typo), Save | Refused: not a known timezone. **Not** saved |
| B2 | Settings → timezone `Asia/Calcutta`, Save | **Accepted** — a real IANA alias |
| B3 | Settings → currency `inr`, Save | Accepted, stored as `INR` |
| B4 | Floor → add an area named `   ` (spaces only) | Refused. *(This returned 201 and created an empty name until it was caught.)* |
| B5 | Floor → add a second area called **Terrace** | Refused: that name is taken |
| B6 | Floor → deactivate **AC Hall** while it has tables | Refused, and it says **how many tables** are in the way |
| B7 | Tax → add a rate starting **yesterday** | Refused: a rate cannot start before today |
| B8 | Read the refusals in B1, B5, B6 and B7 again | **Your call:** do they tell a restaurant owner what to do next, or do they read like a developer wrote them? |

---

## C · Permissions

| # | Step | Expect |
|---|---|---|
| C1 | Sign in as **waiter1** | **No** Settings, Floor plan, Stations or Tax links in the nav |
| C2 | As waiter1, type `/settings` in the address bar | A plain refusal, not a blank screen |
| C3 | Sign in as **manager** (Koregaon). Look at the nav | **No setup links.** This is spec decision 1: a manager runs a shift; changing what a day means or what tax is charged is not running a shift. **If you disagree with that, now is the time — it is one line in `permissions.json`.** |

---

## D · Security probes

| # | Step | Expect |
|---|---|---|
| D1 | Sign in as **manager@tandoorhouse.test** (the *other tenant*). Open Floor plan | **Tandoor House's** floor — empty. Never Spice Garden's areas or tables |
| D2 | While signed in as Tandoor House, copy a Spice Garden area id from the owner's session and `PATCH /api/v1/staff/setup/dining-areas/<that id>` | **404.** Not 403 — a 403 would confirm the id names something real |

**D1 is the one that stops everything.** Please do it yourself even though I have.

---

## E · The business day — the most valuable step here

| # | Step | Expect |
|---|---|---|
| E1 | Settings → set the day start to **01:00**, and watch the sentence underneath | It re-reads: *"An order at 12:30 am on Tuesday counts towards Monday's sales."* **The sentence is computed, not written** — it is produced by the same function the server uses, so it cannot drift from the real rule |
| E2 | Set it to **00:00** | The sentence is replaced by: at midnight the business day is the calendar day |
| E3 | Set it back to **05:00** and Save | Saved |

**Why E1 matters more than it looks.** ADR 0004 calls this the setting owners misunderstand most.
A label saying "05:00" teaches nobody. **Your judgement is what I need here: after reading that
sentence, would a restaurant owner who has never met this idea understand what they are choosing?**
If not, the wording is worth changing — the mechanism is right, the sentence is a first draft.

---

## F · Switching branch

Vikram (`manager@spicegarden.test`) is a **manager at Koregaon and a waiter at Baner**. That is
deliberate: switching must visibly change what he can do.

| # | Step | Expect |
|---|---|---|
| F1 | Sign in as **manager@spicegarden.test** | A restaurant picker appears in the header. Signed in at **Koregaon**, with the **Staff** link |
| F2 | Switch to **Spice Garden — Baner** | The page reloads at Baner. **The Staff link is gone** — he is a waiter there |
| F3 | Open Floor plan at Baner | Empty, with a line telling you to add an area before adding tables |
| F4 | Switch back to Koregaon | Staff link returns |
| F5 | Sign in as **owner** instead | **No picker at all** — he works at one restaurant, and a switcher with one option is a control that does nothing |

**F2 is the security-relevant one.** Permissions are re-resolved at the target rather than carried
across; arriving at Baner still holding manager rights would be privilege escalation performed by
navigating.

**A note on what F cannot show you.** The switch is remembered on the session row, so it survives
the fifteen-minute token refresh. Without that, F2 would work and then silently undo itself
mid-task — you would find yourself back at Koregaon with nothing on screen to explain it. Proving
that by hand means waiting fifteen minutes; there is a test for it instead
(`test_refreshing_after_a_switch_stays_at_the_new_branch`).

---

## G · Exploratory — ten minutes, your charter

> **Charter:** *You are an owner setting this restaurant up for the first time, and you are not
> careful.* Rename things to nonsense. Reorder the floor until it is wrong. Try to deactivate
> everything. Put a tax rate a decade out. Reload in the middle of edits. Open two tabs and change
> the same area in both.

What I want back is not a bug list. It is the answer to one question: **at any point, did the screen
tell you something that was not true?** A wrong number is recoverable. A screen that says "saved"
when nothing was saved, or shows an order under the wrong day, is the failure this module exists to
prevent.

---

## Known, and deliberate

Things you will notice that are not defects:

- **Reordering is ↑/↓ buttons, not drag.** The spec said drag; this ships buttons, recorded in
  `docs/backlog.md` with the reasoning. Buttons are the keyboard path drag would need anyway, and
  they work with a glove and a steamed screen.
- **Reordering is two requests and is not atomic.** If the second fails, two areas share a position.
  The list stays stable — it is ordered by `(seq, id)` — but the order is not what you asked for.
  Backlogged with the row above; both want the same fix.
- **The second branch is empty.** Deliberate: onboarding's day one is a real state worth seeing.
- **A tax rate cannot be edited, only replaced.** Including to fix a typo made five seconds ago.
  Spec decision 2 accepted that cost: code cannot tell a typo from a cover-up.

## Known, and not yet decided — please read this one

**A superseded tax rate has nothing pointing at its successor.** `menu_item_variant.tax_group_id`
(schema §3) is a direct reference to one `tax_group` row. When a rate is replaced, every menu item
still points at the closed row, and nothing links it to the new one.

History is safe — `order_line.tax_rate` is copied at order time, so past invoices keep the rate they
charged. What is missing is the *forward* step: on a changeover somebody must re-point every menu
item at the new rate, and neither a mechanism nor a screen for that exists.

`seed/operations.yaml` gives each rate a `code` (`GST5`, `GST18`) which looks like exactly the
stable family key this needs, and `docs/schema.md` has no column for it.

**I did not fix this.** It changes an approved schema, M06 is the module that first depends on it,
and an external review is about to look at the same code. It is in `docs/backlog.md` with M06 as the
trigger. If you would rather I add `tax_group.code` now, it is a small migration and much cheaper
before M06 creates foreign keys pointing at these rows than after.

---

## Changes to the world since M01's script

- `make seed` now also creates the floor, stations and tax rates. Previously this data sat in
  `seed/operations.yaml`, validated, and loaded by nothing.
- A **second Spice Garden branch** exists, and Vikram has a role at both. Without it the branch
  switcher renders nothing in the demo data and F could not be run at all.
- `manager@spicegarden.test` is now a waiter at Baner as well as a manager at Koregaon. If a step in
  M01's script assumed he has one posting, this is why.
