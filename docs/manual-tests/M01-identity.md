# M01 · Identity, Roles & Permissions — Manual Test

**Worked example.** Written before the module is built so the format is agreed up front. Step
numbers and expected values will be confirmed against the real screens when M01 ships.

**Module:** M01 · **Est. time:** 25 min · **Tester:** you · **Environment:** staging

---

## Preconditions

- Staging URL: `https://staging.<app>.dev` (I will fill this in at handover)
- Seeded logins — all use password `Staging#2026`:

| Login | Role | Restaurant |
|---|---|---|
| `owner@spicegarden.test` | Owner | Spice Garden |
| `manager@spicegarden.test` | Manager | Spice Garden |
| `waiter1@spicegarden.test` | Waiter | Spice Garden |
| `chef@spicegarden.test` | Chef | Spice Garden |
| `manager@tandoorhouse.test` | Manager | **Tandoor House** (a second restaurant, for isolation tests) |

- Use a private/incognito window so nothing is cached between roles.

---

## A · Happy path

| # | Step | Expected | P/F |
|---|---|---|---|
| A1 | Open the staging URL | Login screen. No data visible before login. | ☐ |
| A2 | Log in as `owner@spicegarden.test` | Lands on the Owner dashboard. Top bar reads "Spice Garden". | ☐ |
| A3 | Read the user menu (top right) | Shows your name and the role "Owner" | ☐ |
| A4 | Open Settings → Staff | A list of employees with name, role, active status | ☐ |
| A5 | Tap "Add employee". Fill: name `Test Waiter`, phone `9000000001`, role `Waiter`, joined today. Save | Employee appears in the list, marked Active | ☐ |
| A6 | Open `Test Waiter`, change role to `Captain`… if no Captain role exists, change to `Manager`. Save | Role updates in the list without a page reload | ☐ |
| A7 | Deactivate `Test Waiter` | Row shows Inactive. **Still in the list** — not deleted. | ☐ |
| A8 | Log out | Returns to login. | ☐ |
| A9 | Press the browser Back button | **No dashboard data visible.** Login screen or a redirect to it. | ☐ |

> A7 and A9 matter more than they look. A7 verifies we deactivate rather than delete
> (ADR 0008) — historical orders must keep pointing at that person. A9 catches cached
> pages leaking after logout.

---

## B · Validation

| # | Step | Expected | P/F |
|---|---|---|---|
| B1 | Log in with a correct email and a wrong password | "Invalid email or password." **Not** "wrong password" — it must not confirm the email exists. | ☐ |
| B2 | Log in with an email that does not exist | The **same** message as B1, word for word | ☐ |
| B3 | Get the password wrong 5 times in a row | Account locks with a clear message saying roughly how long | ☐ |
| B4 | Add an employee with no name | Inline error next to the field. Nothing saved. | ☐ |
| B5 | Add an employee with phone `12345` | Inline error: not a valid phone number | ☐ |
| B6 | Add a second employee with a phone already in use | Clear message that the number is taken | ☐ |
| B7 | Anywhere an error appeared — read it | Plain English. No error codes, no SQL, no stack trace, no table names. | ☐ |

---

## C · Permissions

| # | Step | Expected | P/F |
|---|---|---|---|
| C1 | Log in as `waiter1@` | Lands on the **waiter** screen, not the dashboard | ☐ |
| C2 | Look at the navigation | No Settings, no Staff, no Reports, no financial figures | ☐ |
| C3 | As waiter, open Settings → Staff **by typing the URL directly** | Blocked. A clear "You don't have access" — **not** a blank page or a crash. | ☐ |
| C4 | Log in as `chef@` | Kitchen screen. No prices, no margins, no staff management. | ☐ |
| C5 | Log in as `manager@` | Operational screens **and** staff management. No owner-only financials. | ☐ |
| C6 | Log in as `owner@` | Everything | ☐ |

---

## D · Security probes

Two minutes, and they verify the controls in `docs/security.md` for real.

| # | Step | Expected | P/F |
|---|---|---|---|
| D1 | As `manager@spicegarden`, copy an employee's URL (with its id). Log out. Log in as `manager@tandoorhouse`. Paste that URL. | **Denied or not-found.** If you can see a Spice Garden employee from Tandoor House, stop testing and tell me immediately — that is the most serious bug this product can have. | ☐ |
| D2 | As `waiter1@`, open DevTools → Network. Find any API call. Copy its URL, change the path to `/api/v1/staff/employees`, open it in a tab. | `403`. Not data. | ☐ |
| D3 | Log in as `waiter1@` in window 1. In window 2 as `owner@`, deactivate that waiter. Back in window 1, click anything. | Waiter is logged out **immediately** — not on next login | ☐ |
| D4 | Log in, copy the URL after login, log out, paste the URL in a fresh tab | Login screen. No data. | ☐ |
| D5 | On the login screen, open DevTools → Network, log in, inspect the response | No password, no password hash anywhere in the response | ☐ |

---

## E · Usability

| # | Step | Expected | P/F |
|---|---|---|---|
| E1 | Time yourself logging in from a cold start | Under 10 seconds including typing | ☐ |
| E2 | Do the whole login on a phone, one-handed | Every control reachable with a thumb; nothing needs zoom | ☐ |
| E3 | Turn off wifi, try to log in | A clear "You appear to be offline" — **not** a spinner forever, not a raw error | ☐ |
| E4 | Add an employee on a phone | Form is usable; the keyboard does not cover the field you are typing in | ☐ |
| E5 | Look at the staff list on a phone | Readable without horizontal scrolling | ☐ |

---

## F · Exploratory charter — 10 minutes

**Goal: get into something you should not be able to reach, or make the app show a broken screen.**

Suggested: log in as the waiter and go looking for anything with money on it. Use the browser Back
and Forward buttons aggressively. Open two roles in two windows and act in both. Refresh mid-action.
Submit a form twice quickly. Rotate the phone mid-form. Type a very long name. Paste emoji into
every field.

**Write down anything that felt wrong, even if nothing broke.** Slow, confusing, too many taps,
unclear wording — all findings.

Notes:

```


```

---

## Result

- Steps passed: ____ / 30
- Failures (step number → what you expected → what you saw):

```


```

- Exploratory findings:

```


```
