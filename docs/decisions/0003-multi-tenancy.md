# 0003 — Shared database, `restaurant_id` scoping, enforced in the repository layer

**Status:** Accepted · 2026-09-08

## Context
Multi-branch is an explicit requirement (§31). A cross-tenant data leak is the one bug that would
end this product commercially, so the mechanism must be structural, not remembered.

## Decision
One database, one schema. Every tenant-owned table carries `restaurant_id NOT NULL` with an index.
All data access goes through repositories constructed with a `TenantScope` resolved from the JWT;
the base repository injects the filter. Endpoints cannot obtain an unscoped session.

Postgres Row-Level Security is **not** enabled in month 1 — it is the intended second layer once
the schema stabilises, tracked as a follow-up.

## Alternatives rejected
- **Schema- or database-per-tenant** — clean isolation, but migrations across hundreds of schemas
  and cross-branch analytics (§31) become painful, and connection-pool cost rises fast.
- **Filtering in service code** — one forgotten `where` is a breach. Structure beats discipline.

## Consequences
Every endpoint gets a test proving restaurant A cannot read restaurant B's row. Any raw SQL must
justify itself in review. Organization-level entities (`user`, `customer`) scope to
`organization_id` instead — they are deliberately shared across a chain's branches.
