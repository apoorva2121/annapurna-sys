# M01 · Identity, Roles & Permissions — Manual Test

**Module:** M01 · **Est. time:** 25 min · **Tester:** you · **Environment:** local Compose

> **Rewritten against the built module.** The original was written before the code existed, as a
> format demonstration, and said its step values would be confirmed when M01 shipped. They are now.
> What changed and why is listed at the bottom under *Changes from the pre-build draft* — read that
> if you remember the old steps, skip it otherwise.

---

## What I already ran, and what still needs you

I drove the API and the browser through the mechanical steps before handing this over, so your time
goes on the parts a script cannot do. **This is information, not permission to skip** — if you have
25 minutes, run the whole thing; the last defect in this module (the lockout, number 19 in the
build log) was found by doing exactly these steps by hand after every automated check was green.

| Section | State |
|---|---|
| **A · happy path** | Partly — I verified A1–A6 and A12–A13 in a browser. **A7–A11 (add, assign a role, deactivate, include-deactivated) still want a human.** |
| **B · validation** | B1, B2, B3, B4, B6, B7, B8 verified against the API. **B5 and B9 want your eyes** — B9 especially: are the messages actually readable? |
| **C · permissions** | C1–C3 verified in a browser as the waiter; C6 and C7 verified against the API. **C4 (chef) and C5 (manager) still want a human.** |
| **D · security probes** | D1, D2, D3, D5 verified. **Please still do D1 yourself** — it is the one failure that stops everything, and it is worth you seeing it refuse. **D6 and D7 need a browser.** |
| **E · usability** | Not run. **Entirely yours** — needs a real phone, in a real hand. |
| **F · exploratory** | Not run. **Entirely yours**, and the highest-value ten minutes here. |

If you are short of time, do **D1, A7–A11, C4, C5, E2, E4** and the F charter. That is about ten
minutes and covers everything I could not.

---

## Preconditions

```
make dev        # api, db and web; wait for all three
make seed       # idempotent, safe to re-run
```

- Open **http://localhost:5173**. There is no staging URL yet; the day-2 deploy slipped and the M01
  spec's risk table says plainly that this must not block the module.
- Seeded logins — all use password `Staging#2026`:

| Login | Also works as | Role | Restaurant |
|---|---|---|---|
| `owner@spicegarden.test` | `9820011001` | Owner | Spice Garden |
| `manager@spicegarden.test` | `9820011003` | Manager | Spice Garden |
| `waiter1@spicegarden.test` | `9820011009` | Waiter | Spice Garden |
| `chef@spicegarden.test` | `9820011004` | Chef | Spice Garden |
| `manager@tandoorhouse.test` | `9820022002` | Manager | **Tandoor House** (a second organization) |

- Use a private/incognito window so nothing is cached between roles.
- **Every login accepts the phone number as well as the email.** Most waiters and kitchen staff in a
  real restaurant have no email they check, so please use a phone number for at least one sign-in.

---

## A · Happy path

| # | Step | Expected | P/F |
|---|---|---|---|
| A1 | Open the app | Login screen. No restaurant name, no data of any kind before signing in. | ☐ |
| A2 | Sign in as `owner@spicegarden.test` | Lands on a page headed **"Spice Garden - Koregaon Park"**, and "Signed in as Rajesh Mehta". | ☐ |
| A3 | Read the top bar | Shows the restaurant name, and links for Staff and Your profile. | ☐ |
| A4 | Open **Your profile** | Your name, **employee code `EMP001`**, restaurant, roles, and the full list of what you can do. | ☐ |
| A5 | Open **Staff** | 19 employees. Each row shows name, code, role, and Active. | ☐ |
| A6 | Find `Santosh Pawar` and `Deepak Yadav` | Both marked **"No login"**. They are real employees who never sign in — that has to work (ADR 0007). | ☐ |
| A7 | Tap **Add employee**. Name `Test Waiter`, code `TEST01`, phone `9000000001`, joined today. Leave the login field **blank**. Save | Lands on the new employee's page. No password was required. | ☐ |
| A8 | On that page, tick **Waiter** under Roles and save | "Roles updated." | ☐ |
| A9 | Go back to Staff | `Test Waiter` is listed, Active, role `waiter`. | ☐ |
| A10 | Open `Test Waiter` and press **Deactivate** | Row becomes Inactive. | ☐ |
| A11 | Back to Staff | `Test Waiter` is **gone from the list**. Tick **Include deactivated** — he reappears, marked Inactive. | ☐ |
| A12 | Sign out | Returns to the login screen. | ☐ |
| A13 | Press the browser **Back** button | **No data visible.** Login screen, or a redirect to it. | ☐ |

> A10–A11 matter more than they look. They verify we deactivate rather than delete (ADR 0008) —
> historical orders must keep pointing at that person. A13 catches cached pages leaking after
> sign-out.

---

## B · Validation

| # | Step | Expected | P/F |
|---|---|---|---|
| B1 | Sign in with a correct email and a wrong password | "Invalid login or password." **Not** "wrong password" — it must not confirm the address exists. | ☐ |
| B2 | Sign in with an email that does not exist | The **same** message as B1, word for word. | ☐ |
| B3 | Get the password wrong **6 times** for `waiter1@spicegarden.test` | The same "Invalid login or password." every time; from the fourth try each answer takes a little longer. **Never** "locked" (backlog-issues B5). | ☐ |
| B4 | Now type the **correct** password | Signed in — after a short wait. Five guesses by a stranger cannot keep a waiter out. | ☐ |
| B5 | As owner, add an employee with the name left blank | Refused before it is sent. Nothing saved. | ☐ |
| B6 | Add an employee with phone `12345` | "not a valid phone number". Nothing saved. | ☐ |
| B7 | Add an employee with employee code `EMP001` (already used) | Clear message that the code is in use. | ☐ |
| B8 | Add an employee with login `owner@spicegarden.test` (already used) | Clear message that the phone number or email is in use. | ☐ |
| B9 | Re-read every error you saw | Plain English. No error codes in the sentence, no SQL, no stack trace, no table names. | ☐ |

> **Two employees may share a contact phone number, deliberately.** Only a *login* identifier has to
> be unique. Two brothers working in a family restaurant on one phone is ordinary, and refusing it
> would be the software telling the restaurant it is wrong about its own staff. B8 is the
> uniqueness that actually matters.

---

## C · Permissions

| # | Step | Expected | P/F |
|---|---|---|---|
| C1 | Sign in as `waiter1@` — **use the phone number `9820011009`** | Signs in. Lands on the restaurant page with **no Staff link**, and a note saying nothing is assigned to them yet. | ☐ |
| C2 | Look at the top bar as the waiter | Only "Your profile". No Staff. | ☐ |
| C3 | As the waiter, type `http://localhost:5173/staff` into the address bar | **"You do not have access to this."** — a readable refusal, not a blank page, not a crash. | ☐ |
| C4 | Sign in as `chef@` | Has a Staff link and can read the list — a chef needs to know who is on. Opening a person shows **no** edit form, no roles, no deactivate. | ☐ |
| C5 | Sign in as `manager@spicegarden.test` | Full staff management: add, edit, assign roles, deactivate. | ☐ |
| C6 | As the manager, open `Rajesh Mehta` (the owner) and try to change his roles | Refused: you cannot change someone more senior than you. | ☐ |
| C7 | As the manager, open **your own** record and try to change your roles | Refused: you cannot change your own roles. | ☐ |

> C6 and C7 are the seniority ladder. In M01 a manager and an owner hold the *same seven
> permissions*, so permissions alone cannot stop a manager promoting themselves — `role.rank` is
> what does, and these two steps are the only place you can see it working.

---

## D · Security probes

Five minutes, and they verify the controls in `docs/security.md` for real.

| # | Step | Expected | P/F |
|---|---|---|---|
| D1 | As `manager@spicegarden`, open any employee and **copy the URL** (it has an id in it). Sign out. Sign in as `manager@tandoorhouse.test`. Paste that URL. | **"That employee was not found."** If you can see a Spice Garden employee from Tandoor House, stop testing and tell me immediately — that is the most serious bug this product can have. | ☐ |
| D2 | Sign in as `waiter1@`. Open DevTools → Network. Visit `http://localhost:8000/api/v1/staff/employees` in a tab. | `401` or `403`. **Not** data. | ☐ |
| D3 | Sign in as `waiter1@` in window 1. In window 2, as `owner@`, deactivate Suresh Patil. Back in window 1, reload. | The waiter is signed out. Not "on next login". | ☐ |
| D4 | Sign in, copy the URL you land on, sign out, paste it into a fresh tab | Login screen. No data. | ☐ |
| D5 | On the login screen, open DevTools → Network, sign in, inspect the response body | No password, no password hash, no refresh token anywhere in it. | ☐ |
| D6 | In DevTools → Application → Cookies, find `restaurant_os_refresh` | Marked **HttpOnly**. In the Console, `document.cookie` does **not** show it. | ☐ |
| D7 | While signed in, press **F5** | You stay signed in. (This is the refresh cookie doing its job — the access token did not survive the reload.) | ☐ |

---

## E · Usability

| # | Step | Expected | P/F |
|---|---|---|---|
| E1 | Time yourself signing in from a cold start | Under 10 seconds including typing. | ☐ |
| E2 | Do the whole sign-in on a phone, one-handed | Every control reachable with a thumb; nothing needs zoom. | ☐ |
| E3 | Turn off wifi, try to sign in | "You appear to be offline…" — **not** a spinner forever, not a raw error. | ☐ |
| E4 | Add an employee on a phone | Form is usable; the keyboard does not cover the field you are typing in. | ☐ |
| E5 | Look at the staff list on a phone | Readable without horizontal scrolling. | ☐ |

---

## F · Exploratory charter — 10 minutes

**Goal: get into something you should not be able to reach, or make the app show a broken screen.**

Suggested: sign in as the waiter and go looking for anything you should not see. Use Back and
Forward aggressively. Open two roles in two windows and act in both. Refresh mid-action. Submit a
form twice quickly. Rotate the phone mid-form. Type a very long name. Paste emoji into every field.

**Write down anything that felt wrong, even if nothing broke.** Slow, confusing, too many taps,
unclear wording — all findings.

Notes:

```


```

---

## Known gaps in M01 — not bugs, please do not report these

- **No waiter or kitchen screen.** A waiter and a chef land on the same plain page. Ordering is
  M07, the kitchen display is M08.
- **No "reset someone else's password" button.** The endpoint and the permission exist; the screen
  is not in M01's frontend scope.
- **No forgotten-password flow.** No email or SMS provider is wired until M14. An owner resets a
  staff password; a forgotten owner password is a support action in month 1.
- **No MFA enrolment.** The column exists; the flow is backlogged.
- **Roles are assigned after creating a person, not during.** Deliberate: folding role assignment
  into create would let anyone holding `employee.create` grant roles as a side effect and bypass the
  seniority ladder entirely.

---

## Changes from the pre-build draft

Recorded so the difference is auditable rather than quietly rewritten.

| Old step | Why it changed |
|---|---|
| "Lands on the Owner dashboard" | There is no dashboard in M01. It lands on a page naming the restaurant, which is what acceptance criterion 1 actually asks for. |
| "Settings → Staff" | Settings is M02. Staff is a top-level link. |
| Set the role while adding an employee | Role assignment is a separate, separately-permissioned step, for the reason in the Known gaps list. Split into A7 and A8. |
| "change role to `Captain`" | No Captain role exists. The nine system roles are fixed by `docs/schema.md` §1; `waiter` is named "Waiter / Captain". |
| "Deactivated row stays in the list" | It leaves the default list and returns under **Include deactivated**. The row is never deleted, which is what ADR 0008 requires; showing inactive staff by default would put leavers in front of a manager every day. |
| "Waiter lands on the waiter screen" / "Chef lands on the kitchen screen" | M07 and M08. What M01 must get right is that neither is offered staff management, and C3 checks the refusal is readable. |
| "second employee with a phone already in use" | `employee.phone` is deliberately not unique — see the note under section B. Replaced by B7 (duplicate employee code) and B8 (duplicate login), which are the constraints that exist. |
| — | D6 and D7 are new: the httpOnly cookie and surviving a page reload were not covered, and both are load-bearing for the session design. |

---

## Result

- Steps passed: ____ / 41
- Failures (step number → what you expected → what you saw):

```


```

- Exploratory findings:

```


```
