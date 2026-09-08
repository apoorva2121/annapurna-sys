# Pre-Production Security Checklist

Run **once**, in full, before any real restaurant's data or money touches the system. Then re-run
after any change to auth, permissions, the guest surface, or file uploads.

Controls and reasoning: `docs/security.md`. Roughly 90 minutes.

Anything marked 🔴 is a **stop**: do not go to production until it passes.

---

## 1 · Tenant isolation 🔴

The most serious class of bug this product can have.

| # | Check | Expect | P/F |
|---|---|---|---|
| 1.1 | Generic isolation suite green across every registered staff route | All pass | ☐ |
| 1.2 | 🔴 By hand: log in to restaurant B, paste a URL containing restaurant A's order id | Denied / not-found | ☐ |
| 1.3 | Repeat 1.2 for employee, customer, recipe, stock batch, invoice | All denied | ☐ |
| 1.4 | Call a list endpoint with `?restaurant_id=<other>` appended | Parameter ignored; only your own data | ☐ |
| 1.5 | Confirm no raw SQL exists without an explicit tenant filter (`grep`) | None | ☐ |

## 2 · Authentication 🔴

| # | Check | Expect | P/F |
|---|---|---|---|
| 2.1 | Passwords hashed with argon2id; no plaintext or reversible storage anywhere | Confirmed in DB | ☐ |
| 2.2 | Refresh tokens stored **hashed** | A DB read yields no usable session | ☐ |
| 2.3 | Unknown email and wrong password give identical responses **and similar timing** | No enumeration | ☐ |
| 2.4 | Lockout after 5 failures; backoff applies | Locked | ☐ |
| 2.5 | 🔴 Deactivate an employee mid-session → they are logged out on next action | Immediate | ☐ |
| 2.6 | Password change invalidates all other sessions | Confirmed | ☐ |
| 2.7 | Access token expires in ~15 min; refresh rotates | Confirmed | ☐ |
| 2.8 | MFA works for owner and admin | Confirmed | ☐ |

## 3 · Authorisation

| # | Check | Expect | P/F |
|---|---|---|---|
| 3.1 | Every registered route declares a required permission | Build passes the assertion | ☐ |
| 3.2 | Permission matrix suite green for every role × route | All pass | ☐ |
| 3.3 | `grep` for role-name comparisons in code (`== "manager"`) | None outside seeds | ☐ |
| 3.4 | Waiter cannot void an order, apply a comp, or see margin | Denied | ☐ |
| 3.5 | Chef cannot see prices or wages | Denied | ☐ |

## 4 · Guest surface 🔴

| # | Check | Expect | P/F |
|---|---|---|---|
| 4.1 | 🔴 No guest token reaches **any** staff route | All denied | ☐ |
| 4.2 | Guest responses contain no cost, margin, recipe, or employee name | Verified in raw JSON | ☐ |
| 4.3 | Table token expires; an old QR stops working | Expired | ☐ |
| 4.4 | Rate limits fire on rapid guest requests | 429 | ☐ |
| 4.5 | Guest phone lookup returns the same response for existing and non-existing numbers | No enumeration | ☐ |
| 4.6 | A guest cannot read another table's order | Denied | ☐ |

## 5 · Money integrity 🔴

| # | Check | Expect | P/F |
|---|---|---|---|
| 5.1 | 🔴 Tamper the price in a request body → server recomputes and ignores it | Correct total | ☐ |
| 5.2 | Tamper discount, tax, or total the same way | All ignored | ☐ |
| 5.3 | Double-submit a settle with the same Idempotency-Key | Charged once | ☐ |
| 5.4 | Two concurrent settles of one order | One wins, one 409 | ☐ |
| 5.5 | Comp without an authoriser | Rejected | ☐ |
| 5.6 | Invoice numbers sequential per financial year, **no gaps**, including cancellations | Verified | ☐ |
| 5.7 | No float anywhere in a money path (`grep` for `float(`) | None | ☐ |

## 6 · Input and uploads

| # | Check | Expect | P/F |
|---|---|---|---|
| 6.1 | Unknown JSON field on any endpoint | 422, not silently accepted | ☐ |
| 6.2 | SQL metacharacters in every text field | Stored literally; no error | ☐ |
| 6.3 | `<script>alert(1)</script>` in a name, then view it everywhere it renders | Escaped, never executed | ☐ |
| 6.4 | Upload a `.exe` renamed to `.jpg` | Rejected on content, not extension | ☐ |
| 6.5 | Upload a file over the size cap | Rejected | ☐ |
| 6.6 | Uploaded files served from a separate origin, never executed | Confirmed | ☐ |

## 7 · Configuration and transport

| # | Check | Expect | P/F |
|---|---|---|---|
| 7.1 | 🔴 `DEBUG=false` in production; app refuses to boot with it true | Confirmed | ☐ |
| 7.2 | TLS enforced; HSTS present; no mixed content | Confirmed | ☐ |
| 7.3 | CSP set, no `unsafe-inline`; `X-Frame-Options: DENY` | Confirmed | ☐ |
| 7.4 | CORS is an allow-list, not `*` | Confirmed | ☐ |
| 7.5 | 🔴 No secrets in the repo or image layers (`gitleaks`) | Clean | ☐ |
| 7.6 | `pip-audit` and `npm audit` free of high/critical | Clean | ☐ |
| 7.7 | Trigger a 500 → response shows a generic message + reference id only | No stack trace | ☐ |

## 8 · Logging and audit

| # | Check | Expect | P/F |
|---|---|---|---|
| 8.1 | 🔴 Search production logs for a known test phone number and email | Zero hits — redacted | ☐ |
| 8.2 | Search logs for `password`, `token`, `refresh` | Zero values | ☐ |
| 8.3 | Price change, recipe edit, void, comp, stock adjust each produce an audit row with before/after | All present | ☐ |
| 8.4 | Audit rows cannot be edited or deleted through any endpoint | Confirmed | ☐ |
| 8.5 | Sentry PII scrubbing active before the first event | Confirmed | ☐ |

## 9 · DPDP and GST compliance 🔴

| # | Check | Expect | P/F |
|---|---|---|---|
| 9.1 | Consent notice shown before collecting a customer phone; **not pre-ticked** | Confirmed | ☐ |
| 9.2 | Consent recorded with timestamp and notice version | Stored | ☐ |
| 9.3 | Customer data export works | Produces a file | ☐ |
| 9.4 | 🔴 Erasure anonymises the customer but **retains the order and revenue** | Totals unchanged | ☐ |
| 9.5 | Retention purge job runs and respects the configured window | Confirmed | ☐ |
| 9.6 | Bill shows GSTIN, FSSAI licence, CGST/SGST split, veg/non-veg marks | All present | ☐ |
| 9.7 | Refund produces a credit note linked to the original invoice | Confirmed | ☐ |

## 10 · Backup and recovery 🔴

| # | Check | Expect | P/F |
|---|---|---|---|
| 10.1 | Daily automated backups running, encrypted | Confirmed | ☐ |
| 10.2 | Point-in-time recovery enabled | Confirmed | ☐ |
| 10.3 | 🔴 **Restore actually performed** into a scratch DB and data verified | Restored and checked | ☐ |
| 10.4 | Restore completed within the 1-hour RTO | Timed | ☐ |
| 10.5 | `docs/runbooks/restore.md` followed exactly as written, by you | Followable while stressed | ☐ |

> 10.3 is the one most often skipped and most often regretted. An untested backup is not a backup.

---

## Sign-off

- Date: ____________  Run by: ____________
- 🔴 items all passing: ☐ Yes ☐ **No — do not deploy**
- Open non-blocking findings:

```


```
