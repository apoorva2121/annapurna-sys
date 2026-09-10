# Backlog

Ideas that arrived mid-module. **Nothing here is scope** until it is promoted into
`docs/modules.md` deliberately, between modules — never during one.

This file exists because the vision document has 36 sections and the single most reliable way to
finish nothing is to act on all of them.

| Idea | Source | Notes |
|---|---|---|
| Upgrade vitest 3 → 5 for GHSA-82fw-gwwq-j7x9 | M00, 2026-09-09 | Path traversal in `@vitest/mocker`. **Dev dependency only — never in the production bundle**, and the gate is `npm audit --audit-level=high`, which this moderate does not trip. Deferred because vitest 5 is two majors up and would re-open the vite/vitest peer alignment settled in M00. Revisit when vitest 5 has a Vite 6/7 story, or immediately if it is ever reclassified high. |
| Notify the owner when a manager changes someone's roles | M01, 2026-09-10 | Requested during M01: managers hold `employee.role.assign`, and the owner should hear about it. M01 writes the `audit_log` row (actor, target, before/after, ip, timestamp), so **the event is already captured and nothing is lost**. What is missing is delivery — the `notification` table, severity tiers and channels are M14's deliverable, and building them here would be building M14. M14 turns these existing rows into notifications; no M01 change needed then. |
| Disambiguate a login identifier that exists in two organizations | M01, 2026-09-10 | Email and phone are unique *per organization*, so one address can legitimately belong to two (a consultant working for two restaurant groups). Login currently resolves globally and refuses an ambiguous match with the standard identical error, which is safe but locks that person out. Fix when it first happens: an organization picker on the login form, or a per-tenant subdomain. |
