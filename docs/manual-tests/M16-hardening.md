# M16 · Hardening & Production — Manual Test

**Module:** M16 · **Built:** 2026-09-19 · **Gate:** `make check`. Runs and results:
`docs/plan/m16-build-log.md`. Checklist evidence:
`docs/manual-tests/evidence/security-checklist-2026-09-19.md`. Commands:
`docs/deploy/production-runbook.md`.

Run `make seed`, then `make dev`. Sign in as **owner@spicegarden.test** and
**waiter1@spicegarden.test**.

---

## Read this first, because most of this module is not a screen

M16 built almost no user interface. What it did was **run the security checklist in full for the
first time** and fix what that found, which means the things to test by hand fall into three
groups:

1. **Two fixes that are invisible when they work** — headers a browser reads and a date rule that
   only matters one night a year. Sections A and B.
2. **Six rows nobody can tick from a laptop.** They need a live console, they are written as
   commands in `docs/deploy/production-runbook.md`, and **the honest outcome of this pass may be
   that they stay unticked.** Section E.
3. **The guest QR**, which is the one thing here you can hold in your hand. Section D.

The one question this module is really asking you: **is anything on the checklist ticked that you
would not be comfortable defending?** A checklist row marked pass on the strength of somebody
reading the code is a row that has not been run, and saying so is worth more than a tick.

---

## What I already ran, and what still wants you

| Section | State |
|---|---|
| **A · the security headers** | Verified by test: `tests/test_security_headers.py` reads `docs/security.md` and asserts what it promises is sent. **A3 is the question** |
| **B · the financial-year boundary** | Verified by test, including 01:30 on 1 April |
| **C · the checklist record** | Every one of 62 rows carries a pass, a fail, a stated N/A, or "console". **C2 is the question** |
| **D · the guest QR** | Not run. Yours — nothing has ever been scanned |
| **E · the console rows** | Not run, **not ticked**. Yours, and §10 is a 🔴 stop |
| **F · exploratory** | Not run. Yours |

Short of time? Do **D**, then **C2**, then **E**.

---

## A · The security headers

These were promised by `docs/security.md` for sixteen modules and sent by nothing.

| # | Step | Expect |
|---|---|---|
| A1 | Open the staff app, open the browser's network tab, reload, click the document request | Response headers include `content-security-policy`, `x-frame-options: DENY` and `x-content-type-options: nosniff` |
| A2 | Look for `strict-transport-security` on **localhost** | **Absent, and that is correct.** A `max-age` on localhost pins your browser to HTTPS for a year. It appears only over TLS |
| A3 | Use the app normally for five minutes — open a dropdown, a dialog, the date pickers, the kitchen display | **Does anything look broken or unstyled?** |

> **A3 is the question.** The CSP allows inline *styles* (Radix positions popovers with `style=`)
> and forbids inline *scripts*. If a menu renders in the wrong place or a dialog appears at the top
> left of the screen, the policy is too tight and I want to know today rather than from the pilot.

---

## B · The financial year

| # | Step | Expect |
|---|---|---|
| B1 | Settle a bill today and note the invoice number | `2026-27/000001` — the year is in the number |
| B2 | Settle a second | `…/000002`. Consecutive, no gaps (Rule 46(b)) |
| B3 | Void or cancel one, then settle another | The cancelled one **keeps its number**; the next is the next number. GSTR-1 Table 13 needs the cancelled document |

The 1 April case cannot be done by hand without changing the clock — it is covered by
`tests/test_financial_year_boundary.py`, including a bill at 01:30 on 1 April, which belongs to
business day 31 March and to the **new** year's series.

---

## C · The checklist record

| # | Step | Expect |
|---|---|---|
| C1 | Open `docs/manual-tests/evidence/security-checklist-2026-09-19.md` | 62 rows, none blank |
| C2 | **Read the rows marked PASS and pick three at random.** Follow the evidence to the test or the line of code it names. | **Does the evidence actually support the claim?** |
| C3 | Read row 2.8 | MFA does not exist, marked N/A with the reason. **You are shipping without it** |
| C4 | Read §10 | Every row is console, none is ticked, and 10.3 is a 🔴 stop |

> **C2 is the point of this section.** I marked those rows myself. A checklist somebody grades
> their own work on is worth what you make it worth by spot-checking it.

---

## D · The guest QR — the one thing you can hold

| # | Step | Expect |
|---|---|---|
| D1 | With `make dev` running: `python scripts/guest_links.py --html guest-qr.html` | A link printed per table, and a page written |
| D2 | Open `guest-qr.html` in a browser | One card per table, each with a scannable code |
| D3 | **Scan one with a phone on the same network** | The guest menu opens — for that table, with no password |
| D4 | Order something to that table as a waiter, then reload the guest page | The bill appears, itemised, with the GST split |
| D5 | Edit the `?t=` value in the URL — change one character | Refused. The slug is 128 bits and determines the tenant |
| D6 | Scan a second table's code | A different table's bill. Never the first one's |

> **D3 is the first time a QR in this product has ever been scanned.** If anything about the phone
> experience is wrong — text too small, the veg filter hard to reach, the bill hard to read at
> arm's length on a table — that is a finding, and the guest surface is the one a paying customer
> sees.

---

## E · The rows only you can run

**None of these is ticked and none should be until you have run it.** Commands are in
`docs/deploy/production-runbook.md`.

| # | Step | Expect |
|---|---|---|
| E1 | Check the Neon project's **history window** | Probably 6 hours. **Raise it before real data.** This is how far back a restore reaches |
| E2 | Perform a restore into a scratch branch, following `docs/runbooks/restore.md` exactly | It works, and **you time it** against the 1-hour RTO |
| E3 | Note everything in that runbook that was wrong or confusing | Fix it there. Nobody has followed it |
| E4 | Arm cost alerts at 50/80/100%, then **fire one deliberately** | The email arrives. An alert nobody has seen arrive is configured, not working |
| E5 | `gitleaks detect --source . --no-banner` | Clean |
| E6 | Confirm Sentry PII scrubbing is on **before** the first event | On |

> **E2 is the row this module cannot close for you**, and it is the one most often skipped and
> most often regretted. On Neon it is worse than an untested backup: it may be a window that has
> already closed.

---

## F · Exploratory charter — 20 minutes

**Charter:** *Find something this module claims that is not true.*

Try to: frame the staff app in an `<iframe>` and click a button through it; find a response
missing the headers; find a checklist row whose evidence does not say what the row says; find a
guest link that reaches another table; find a screen the CSP has quietly broken.

**And the one that matters most:** read `docs/security.md` and `docs/observability.md` and ask of
each promise, *"where is the code?"* Two of them turned out to be wishes — HSTS/CSP/X-Frame, and
"automated daily backups, 30-day retention". **If you find a third, that is the most valuable
finding in this pass**, because the pattern is the point: a control written in a document and
implemented nowhere reads as safety while being none.
