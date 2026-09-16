# Security & Compliance

You asked for "no possibility of hacking". No system achieves that, and anyone who promises it is
selling something. What this document does promise is **defence in depth, structural controls rather
than remembered ones, and a written account of what we protect and how.**

The governing principle: *security that depends on a developer remembering is not a control.* Every
item below is enforced by structure, by a test, or by CI — not by discipline.

## What we are protecting

| Asset | Why an attacker wants it | Worst case |
|---|---|---|
| Customer PII (phone, name, visit history) | Resale, spam, competitor poaching | DPDP breach notification, fines, trust gone |
| Employee PII (phone, DOB, wages) | Identity theft | Legal exposure, staff trust gone |
| Financial data (sales, margins) | Competitor intelligence | Business harm |
| **Recipes and food costs** | **Directly valuable trade secret** | The restaurant's core IP, leaked |
| Credentials / sessions | Everything above | Total compromise |
| Stock ledger integrity | Concealing theft | The product's central number becomes a lie |

That fourth row is unusual and worth stating: for a restaurant, recipes and costings *are* the
business. We hold them for many restaurants at once. That makes this a higher-value target than a
generic SaaS of the same size.

## The threat model

**Realistic attackers, in order of likelihood:**

1. **A curious or disgruntled employee.** By far the most likely. Has valid credentials, physical
   device access, and motive (hiding waste, hiding comps, seeing wages, seeing margins).
2. **A competitor restaurant** wanting menus, costs and supplier prices.
3. **An opportunistic scanner** hitting the public QR/guest endpoints.
4. **A departing employee** whose access was never revoked.
5. **Credential stuffing** against reused passwords.

Note what is *not* at the top: a sophisticated targeted attacker. Designing for #1 and #2 — insider
misuse and tenant boundary violations — is where the effort belongs.

## Controls, mapped to OWASP Top 10

### A01 Broken Access Control — the one that matters most here

This is both the most likely failure and the most damaging. Four independent layers:

1. **Structural tenant scoping.** All data access goes through repositories constructed with a
   `TenantScope` from the token. There is no way to obtain an unscoped session in a request path
   (ADR 0003). A route cannot reach the ORM at all (`docs/engineering-standards.md` §1).
2. **Permission checks in the service layer**, by permission string, never by role name (ADR 0007).
3. **Persona separation.** Guest requests cannot enter staff routing — different route tree,
   different token type, different middleware (ADR 0009).
4. **Row-Level Security in Postgres** as a backstop, enabled once the schema stabilises.

**Automated enforcement:** a generic test enumerates *every* registered staff endpoint and asserts
restaurant A's token returns 403/404 for restaurant B's resources. A new endpoint is covered the
moment it is registered — no one has to remember to write the test. A second generic test asserts no
guest token reaches any staff route.

**IDOR** is prevented by the same scoping: an id from another tenant simply does not exist to that
query. We do not rely on unguessable UUIDs for authorisation.

### A02 Cryptographic Failures
- TLS 1.2+ everywhere, HSTS, no mixed content.
- Passwords: **argon2id** (not bcrypt, not SHA-anything), per-user salt, tuned cost.
- Refresh tokens stored **hashed**, never plaintext — a database read must not yield live sessions.
- Secrets in the platform secret manager, never in the repo, never in an image layer.
  `.env` is gitignored; a pre-commit secret scan (`gitleaks`) blocks accidental commits.
- Database encrypted at rest (managed by the provider); backups encrypted.

### A03 Injection
- SQLAlchemy parameterised queries only. Raw SQL requires review and must carry an explicit tenant
  filter (ADR 0003).
- Pydantic validates every input with `extra="forbid"` — unknown fields are rejected, so mass
  assignment is structurally impossible.
- React escapes by default; `dangerouslySetInnerHTML` is banned by an eslint rule.
- File uploads: allow-list of MIME types, size cap, extension re-derived from content, stored with a
  generated key, served from a separate origin, never executed.

### A04 Insecure Design
- Threat-model question in every module spec: *what would an insider do with this?*
- **The server never trusts client-supplied money.** Prices, taxes, discounts and totals are
  recomputed server-side from the menu and recipe. A tampered client can order anything; it cannot
  change what anything costs.
- **Comps and discounts require an authoriser** (`order_discount.authorised_by NOT NULL`) and land in
  the audit log. This is an anti-fraud control, not bookkeeping.
- **The stock ledger is append-only.** Concealing theft requires a compensating entry that is itself
  logged and attributable.

### A05 Security Misconfiguration
- `DEBUG=false` in every non-local environment, asserted at startup — the app refuses to boot
  otherwise.
- Strict CORS allow-list. CSP with no `unsafe-inline`. `X-Frame-Options: DENY`.
- Error responses never leak internals (`docs/engineering-standards.md` §4).
- Default-deny: a route with no explicit permission declaration fails closed, and a test asserts
  every registered route declares one.

### A06 Vulnerable Components
- Locked dependencies (`backend/uv.lock`, `frontend/package-lock.json`), committed, and
  installed **frozen** — `uv sync --frozen` and `npm ci` in CI and in the image, so a build can
  never resolve a version the tests never saw. `backend/tests/test_toolchain_pins.py` fails when a
  lockfile is missing or older than `pyproject.toml`. [built: M01-R]
- `pip-audit` and `npm audit` in CI; a high/critical finding fails the build.
- Renovate for scheduled updates. Minimal dependency count — every library is attack surface.
  [planned: M16]

### A07 Identification & Authentication Failures
- Short-lived access JWT (15 min) + rotating refresh token (30 days), revocable server-side.
- **No automatic lock** (backlog-issues B5, G-15). Each wrong password for one login waits longer
  than the last — 1s, 2s, 4s… from the third, capped at 30s — and a network with 30 failures in
  ten minutes is refused for a while. Both are the same for a login nobody holds, so neither says
  whether a login exists. An account is locked only by a person, and that is revealed only to
  someone who typed the right password. Attempts are remembered by a hash of the login
  (`login_attempt`), never the login itself.
- The network is the address the server sees. Behind the production proxy that means trusting
  its forwarded address, which waits for the deploy (R7): trusting it with no proxy in front would
  let anyone choose their own address and walk around the budget.
- Session invalidation on password change, on role change, and on employee deactivation.
- **Offboarding is one action:** deactivating an employee revokes every session immediately. Attacker
  #4 in the threat model exists because most systems make this three separate steps.
- MFA available for `owner` and `admin` from day one, optional but supported.

### A08 Data Integrity Failures
- Idempotency keys prevent duplicate financial effects (ADR 0010).
- Optimistic locking prevents lost updates; row locking prevents stock oversell.
- Nightly reconciliation flags any negative batch as a data-integrity alert.

### A09 Logging & Monitoring Failures
- `audit_log` records every price, recipe, stock, void, comp and permission change with actor,
  before and after (`docs/schema.md` §12).
- **PII is redacted from application logs** by a logging filter, not by remembering
  (`docs/observability.md`).
- Alerts on: repeated auth failures, permission denials in bursts, cross-tenant 403 spikes, negative
  stock, comps above threshold.

### A10 SSRF
- The application fetches no user-supplied URL. If image-by-URL is ever added, it goes through an
  allow-list and a non-privileged egress path.

## The guest surface is hostile input

The QR ordering path is unauthenticated and public, so it is treated as fully untrusted:

- Table tokens are **short-lived** (rotating, ~2h) and scoped to one table at one restaurant. A
  photographed QR code is effectively public and must expire.
- Aggressive per-IP and per-token rate limits; menu responses cached and cheap.
- Guest responses carry **no** cost, margin, recipe, employee name, or other guests' data — enforced
  by separate response schemas (ADR 0009), so a staff field cannot leak by accident.
- Feedback and order endpoints are write-limited to prevent spam and rating manipulation.
- No enumeration: guest lookups by phone return the same response whether or not the number exists.

## India-specific compliance

**DPDP Act 2023** (Digital Personal Data Protection) — applies directly; we process customer and
employee personal data.

- **Notice and consent** at collection, in plain language, for a stated purpose. QR feedback collects
  a phone number only with an explicit tick, never pre-ticked.
- **Purpose limitation** — a phone number collected for a bill is not marketing consent.
- **Data principal rights** — access, correction, erasure. Build the export and erasure paths in the
  Customer module (M10), not as a later scramble. Erasure anonymises the customer row and keeps the
  order (financial records must be retained); it does not cascade-delete revenue history.
- **Retention limits** — personal data is deleted when its purpose ends. Configurable per restaurant,
  with a default and a scheduled purge job.
- **Breach notification** to the Data Protection Board and affected persons — the runbook lives in
  `docs/observability.md`.
- **Consent artefacts are recorded** with timestamp and version of the notice shown.

**GST**
- Invoice numbering is **sequential per restaurant per financial year with no gaps** — legally
  required. A cancelled order must not create a gap; cancellations retain their number with a
  cancelled status. This is why `order` has no delete (ADR 0008).
- CGST/SGST split stored per line, computed at order time, never re-derived at display.
- Refunds are credit notes, linked to the original invoice.
- E-invoicing (IRN) applies above the turnover threshold — out of scope for month 1, but invoice
  data is modelled so it can be generated without a schema change.

**FSSAI** — licence number displayed on the bill; `menu_item.food_type` (veg/non-veg/egg) is a
labelling requirement, which is why it is `NOT NULL`.

**Employment records** retained per statutory minimums; wage data is permission-gated separately
from other employee fields.

## What we explicitly do not claim

- Not penetration-tested by a third party. Worth commissioning before the first paying multi-outlet
  customer; roughly ₹1–3L in India.
- Not SOC 2 or ISO 27001 certified. Not required at this stage; will be asked for by chains.
- No formal bug bounty.
- No protection against a fully compromised restaurant device with a valid logged-in session — that
  is why the audit log matters.

## Security review checkpoints

- **Per module** — the threat question in the spec; `ruff S` rules; the generic isolation and
  permission tests must pass.
- **Per phase** — a focused review pass over the diff (`/security-review`).
- **Before production** — the full checklist in `docs/manual-tests/security-checklist.md`, including
  the adversarial tests you run by hand.
