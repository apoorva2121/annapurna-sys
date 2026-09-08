# 0007 — Authentication split from employee data; permission-based RBAC

**Status:** Accepted · 2026-09-08 · Supersedes the `user` / `user_restaurant_role` sketch in ADR 0003

## Context
The earlier model had one `user` table doing three unrelated jobs: holding credentials, describing a
person's employment, and carrying a role enum. Three problems follow:

1. Not every employee logs in. Cleaners and some kitchen staff need to be *referenced* by tasks,
   shifts and wastage events without ever having a password.
2. Customers will eventually authenticate too (QR ordering, feedback). They are not employees, and
   should not need a row in an employee table to log in.
3. A role enum makes permissions a code branch. Vision doc §23 requires configurable per-role
   visibility, which an enum cannot express without redeploying.

## Decision
Three separate concerns, three sets of tables.

```
user_account   (credentials, sessions, MFA)   -- optional, nullable link
     │ 1:0..1
employee       (who they are, employment)
     │
employee_role_assignment  (employee × restaurant × role)
     │
role ──< role_permission >── permission
```

- **`user_account`** holds only authentication: identifier, password hash, status, MFA, lockout.
  It knows nothing about restaurants or jobs. `user_session` holds refresh tokens.
- **`employee`** is the business profile, owned by the organization. `user_account_id` is nullable
  and unique — an employee without login is normal and supported.
- **`role`** rows are seeded per organization from a system template (owner, admin, manager, chef,
  kitchen_staff, waiter, store_manager, cleaner, accountant) and may be customised. System roles
  carry `is_system = true` and cannot be deleted.
- **`permission`** is a static catalogue of `resource.action` strings (`order.void`,
  `stock.adjust`, `report.financial.view`). Code checks permissions, never role names.
- **`employee_role_assignment`** is per restaurant, so one manager can hold different roles at
  different branches of a chain.

`customer` remains entirely separate from `employee`, with its own optional `user_account_id`.

## Alternatives rejected
- **Role enum on the user** — what we had. Cannot express §23 without code changes.
- **Fully dynamic permissions from day one** (users granted individual permissions) — real
  requirement eventually, unnecessary complexity now. `employee_permission_override` can be added
  later without touching anything else.
- **One `person` table for staff and customers** — they share almost no columns and have opposite
  privacy requirements.

## Consequences
- Authorisation is `require_permission("order.void")`, never `if role == "manager"`. A hard rule.
- Permission checks happen in the service layer, after tenant scoping, never in route handlers.
- Seeding roles and permissions is a migration, so the permission catalogue is version-controlled
  and diffable.
- Deactivating an employee disables their login but leaves every historical reference intact.
