# 0009 — Employee and customer are two applications, not two roles

**Status:** Accepted · 2026-09-08

## Context
The platform serves two populations with almost nothing in common:

| | Employee | Customer |
|---|---|---|
| Who | ~15 known, trained people | Thousands of strangers |
| Auth | Password + session, long-lived | Anonymous, or phone OTP |
| Device | Restaurant-owned tablet/phone | Their own phone, hostile network |
| Data reach | Broad, by permission | Their own order only |
| Trust | Accountable, auditable | None assumed |
| Volume | Low, steady | Spiky, unbounded, scrapeable |

The tempting design is one application where `role = customer` is just another role. That fails in a
specific and predictable way: a single codebase with a shared middleware stack means every new
endpoint is one forgotten permission check away from exposing staff data to the public internet.
The blast radius of that mistake is the whole business.

## Decision
Two applications, separated structurally rather than by a conditional.

```
/api/v1/staff/*      employee API   — session JWT, permission-checked, full domain
/api/v1/guest/*      customer API   — table token or OTP, narrow, read-mostly
```

- **Separate route trees, separate middleware stacks, separate dependency chains.** No handler is
  reachable from both. A guest request cannot physically enter staff routing.
- **Separate auth realms.** `user_account` backs staff. Guests get either a short-lived,
  table-scoped token minted from the QR code, or phone OTP for order history. A guest token can
  never satisfy a staff dependency, because they are different types.
- **Separate frontend bundles.** The guest app is a small, fast, mostly-anonymous PWA. It ships none
  of the staff code — no admin routes to discover, no permission strings to enumerate.
- **Separate rate limits.** Guest endpoints are public and abusable; staff endpoints are not.
- **Data minimisation on the guest side.** Guest responses expose dish names, prices and the
  guest's own order. Never cost, margin, recipe, employee name, or another guest's anything.

`customer` is therefore **not** a row in `role`. It never was in this schema, and this ADR is why.

## Alternatives rejected
- **One app, `role = customer`** — the default design. One missing `require_permission` becomes a
  public data breach. Discipline is not a security control.
- **Separate service/deployment per persona** — stronger isolation, but doubles deploy and
  operational cost for a product at pilot scale. Route-tree separation inside one deployable gets
  most of the benefit now; this ADR does not block splitting later, because the seam already exists.

## Consequences
- Some serialisation logic is duplicated between staff and guest schemas. **That duplication is the
  feature** — it means a field added for staff cannot silently appear in a guest response.
- Two auth test suites, and a test that asserts no guest token can reach any staff route.
- The QR table token needs a short TTL and rotation, since a photographed QR is effectively public.
- `docs/security.md` treats the guest surface as fully untrusted input.
