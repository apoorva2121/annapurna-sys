# Project Explanation — Restaurant OS, end to end

A complete account of what this product is, how it is built, how data moves through it, and how
somebody would build it again from an empty directory.

Written 2026-09-28 against the repository at `C:\dev\restaurant-os`, branch
`feat/m11-communication`. Every number in it was read out of the code, not remembered.

---

## Table of contents

1. [What the product is](#1--what-the-product-is)
2. [The shape of the system](#2--the-shape-of-the-system)
3. [The seven invariants](#3--the-seven-invariants)
4. [Technology, and why each piece](#4--technology-and-why-each-piece)
5. [Repository layout](#5--repository-layout)
6. [The layering rule](#6--the-layering-rule)
7. [Identity, tenancy and access control](#7--identity-tenancy-and-access-control)
8. [The data model](#8--the-data-model)
9. [End-to-end data flows](#9--end-to-end-data-flows)
10. [Cross-cutting mechanics](#10--cross-cutting-mechanics)
11. [The frontend](#11--the-frontend)
12. [Testing](#12--testing)
13. [Build, migrations and seed data](#13--build-migrations-and-seed-data)
14. [Deployment and operations](#14--deployment-and-operations)
15. [How to recreate this from scratch](#15--how-to-recreate-this-from-scratch)
16. [Traps that cost real time](#16--traps-that-cost-real-time)

---

## 1 · What the product is

A multi-tenant SaaS platform for Indian restaurants. It runs the floor and the kitchen, and it
turns what happens there into the one number a restaurateur cannot otherwise get: the gap between
what the food **should** have cost, according to the recipes, and what it **actually** cost,
according to the stockroom.

That gap is the product. Point of sale is table stakes and a dozen vendors sell it. Nobody hands a
single-outlet owner in Jaipur a defensible figure for where four thousand rupees of paneer went
last week. Every design decision in the codebase bends toward being able to answer that question
in SQL.

The acceptance query, stated in the domain model and treated as the architecture's exit criterion:

> For last week, per dish: units sold, revenue, theoretical food cost from recipes, actual
> ingredient consumption from the ledger, the variance between them, waste attributed to it,
> average prep time, and average customer rating.

If a schema change would break that query, it is the wrong change.

### Scale of what exists

| | |
|---|---|
| Database tables | 80, across 14 domains |
| Database columns | 930 |
| Permissions | 55 |
| Role templates | 9 |
| Screens | 62, across two applications |
| Modules delivered | M00 through M19 |

### What is deliberately absent

Payment gateway integration, printer and hardware drivers, offline-first sync, GST e-invoicing
filing, computer vision, React Native, and multi-branch rollups. None of them is *blocked* by the
design. None of them is built.

---

## 2 · The shape of the system

```
   ┌──────────────────────┐        ┌──────────────────────┐
   │   Staff application  │        │  Guest application   │
   │  React PWA, 59 pages │        │  React, 3 screens    │
   │  waiter · kitchen ·  │        │  QR code, no login   │
   │  manager · owner     │        │                      │
   └──────────┬───────────┘        └──────────┬───────────┘
              │  Bearer access token           │  guest token
              │  Idempotency-Key on writes     │  (scoped to one table
              │  Server-Sent Events for KDS    │   or one bill)
              ▼                                ▼
   ┌─────────────────────────────────────────────────────────┐
   │                    FastAPI application                  │
   │                                                         │
   │  /api/v1/staff/...            /api/v1/guest/...         │
   │  ─────────────────            ────────────────          │
   │  route    parse, authorise, call one service            │
   │  service  business rules, transactions, audit           │
   │  repository  tenant-scoped queries, nothing else        │
   │  model    table shape                                   │
   └───────────────────────┬─────────────────────────────────┘
                           │  SQLAlchemy 2.0 async
                           ▼
              ┌────────────────────────┐   ┌──────────────────┐
              │     PostgreSQL 16      │   │  S3-compatible   │
              │  80 tables · Alembic   │   │  object storage  │
              └────────────────────────┘   └──────────────────┘
```

Two applications rather than one with a role switch. That is ADR 0009, and the reason is security
rather than tidiness: the guest bundle is a separate Rollup entry point, so it physically cannot
contain staff code. There are no admin routes in it to discover and no permission strings in it to
enumerate. A build that merely *can* keep the two apart is not the same as one that refuses to put
them together.

Realtime is Server-Sent Events, not WebSockets and not polling from the client. The reasons are in
section 10.

---

## 3 · The seven invariants

These are the rules the whole system is arranged around. Violating one is a bug, never a style
choice. They appear here early because most of the design below is a consequence of them.

**1 · Tenant isolation.** Every tenant-owned table carries `restaurant_id NOT NULL`. Every query
goes through a repository that takes a tenant scope. No raw SQL without an explicit restaurant
filter. This is the product's number one bug class, and section 7 describes the structural defence.

**2 · Stock is a ledger.** The stock movement table is append-only. Current stock is *derived* by
summing movements. Nothing ever updates a quantity in place. A correction is a new movement of type
`adjustment`, which is why an insider cannot quietly erase a shortfall.

**3 · Money is `NUMERIC(12,2)` and Python `Decimal`.** Never a float, never `round()` on a float.
Currency is per restaurant, rupees today. In JSON money travels as a **string**, so no JavaScript
float ever touches a rupee.

**4 · Time is `timestamptz` stored in UTC.** Display and aggregate in the restaurant's timezone. A
restaurant's business day is not midnight to midnight: it starts at `restaurant.business_day_start`,
typically 05:00 local. Today's sales for a place that closes at 2am must include that 2am.

**5 · Units are canonical.** Every ingredient has one base unit, gram, millilitre or unit. Convert
at the boundary and store base units only.

**6 · Settled orders are immutable.** No edits after settlement. Voids and refunds are new rows.
Everything that affects price, recipe or stock writes an audit entry.

**7 · Theoretical is not actual.** Recipes give theoretical usage. Physical counts give actual
usage. Both are stored, separately, and neither ever overwrites the other. The variance between
them is the product.

---

## 4 · Technology, and why each piece

| Layer | Choice | Reason |
|---|---|---|
| Language | Python 3.13 | Team fluency, and the async ORM story is mature |
| Web framework | FastAPI | Typed request and response models, dependency injection that makes authorisation declarative |
| ORM | SQLAlchemy 2.0, async | Real Postgres features without hand-writing every query |
| Migrations | Alembic | Reviewed, reversible, run in continuous integration |
| Validation | Pydantic v2 | The API contract is a type, and unknown fields are rejected |
| Database | PostgreSQL 16 | `timestamptz`, `NUMERIC`, partial indexes, `jsonb`, `FOR UPDATE`, CHECK constraints — all load-bearing |
| Frontend | React 18, TypeScript, Vite | Two entry points from one toolchain |
| Styling | Tailwind with shadcn/ui | Tokens, not ad-hoc CSS |
| Server state | TanStack Query | Caching and invalidation the app would otherwise reinvent badly |
| Realtime | Server-Sent Events | Section 10 argues it |
| Mobile | The React app as a PWA | Waiter and kitchen screens are the same codebase at mobile breakpoints |
| Deploy | Docker, managed Postgres, S3-compatible storage | Nothing cloud-proprietary, so the cloud is a deploy-time choice |

The architecture decision records live in `docs/decisions/`. The eleven that matter:

| ADR | Subject | The decision in one line |
|---|---|---|
| 0002 | Stack | The table above |
| 0003 | Multi-tenancy | Shared database, `restaurant_id` on every row, repository-enforced |
| 0004 | Money, time, units | Invariants 3, 4 and 5, with the business day defined |
| 0005 | Deployment target | Container plus Postgres plus object storage, nothing else; Cloud Run first |
| 0006 | Preparations and sub-recipes | Recipes nest to depth 3 |
| 0007 | Identity and access | Authentication split from employment; permissions, never role names |
| 0008 | Persistence conventions | UUIDv7 keys, deactivation tiers, enums as strings, numeric scales |
| 0009 | Two personas, two applications | Separate route trees, separate tokens, separate bundles |
| 0010 | Idempotency and concurrency | Client keys on money writes, optimistic locking, `FOR UPDATE` on batches |
| 0011 | Performance measurement | Everyone can see their own score; no bottom ranking exists |

---

## 5 · Repository layout

```
backend/
  app/
    api/
      deps.py            authentication and permission dependencies
      guest_deps.py      the guest token's equivalent
      idempotency.py     the Idempotency-Key dependency
      v1/
        auth.py
        staff/           21 routers: orders, menu, stock, kot, reports, …
        guest/            5 routers: session, menu, order, feedback, consent
    core/                enums, errors, issues, money, tax, business_day, permissions,
                         security, tenancy, audit, logging, config, media, consent
    models/              20 modules of SQLAlchemy models — the 80 tables
    schemas/             Pydantic request and response contracts
    services/            39 modules — all business rules
    repositories/        23 modules — all queries, all tenant-scoped
  alembic/               migrations
  tests/                 unit, integration, and the four generic suites
frontend/
  src/
    shared/              api client, theme, ui primitives, enums, money, businessDay
    staff/               App.tsx, navigation.ts, screens/, components/, api/
    guest/               App.tsx, screens/
docs/
  decisions/             the ADRs
  modules/               one spec per module, M00 to M19
  product/               vision, competitor and market research
  ui/                    conventions and design system
  plan/                  build logs
seed/                    YAML fixtures for the demo restaurant
library/                 223 dish recipes with confidence tiers
```

Two rules about this tree are worth stating. Enums live in `app/core/enums.py` and are mirrored in
`frontend/src/shared/enums.ts`, with a test asserting the two cannot drift. And the frontend's
`shared/` folder is what both applications may import; `staff/` and `guest/` may not import each
other, enforced by an eslint rule rather than by good intentions.

---

## 6 · The layering rule

```
route  →  service  →  repository  →  model
```

| Layer | Does | Never does |
|---|---|---|
| route | parse the request, call one service, shape the response | business logic, database access, permission logic |
| service | business rules, permission checks, transactions, orchestration | build SQL, know about HTTP |
| repository | queries, always tenant-scoped | business rules, decide what is allowed |
| model | table shape | anything else |

Skipping a layer is allowed in exactly one direction. A service may call another service. A
repository may never call a service, and nothing may call a route.

This single rule is why tenant isolation and permission checks can be tested generically, by
walking the application's own routing table, instead of endpoint by endpoint. A route that touches
the ORM is a review rejection. A repository containing an `if` about business policy is a review
rejection.

### A worked example: adding a line to an order

```
POST /api/v1/staff/orders/{id}/lines
   │
   ├─ FastAPI resolves Depends(require_permission("order.modify"))
   │     → decodes the bearer token
   │     → re-reads the employee and their permissions from the database
   │     → builds an Actor, or raises 401/403
   │
   ├─ Pydantic validates the body against AddLineRequest
   │     extra="forbid", so an unknown field is rejected outright
   │     the body names the variant, the quantity and the modifiers — never a price
   │
   ├─ the route calls OrderService.add_line(actor, order_id, request) and nothing else
   │
   ├─ the service
   │     → loads the order FOR UPDATE and checks order.version (optimistic lock)
   │     → refuses if the order is settled (invariant 6)
   │     → reads the variant's current price and tax group from the menu repository
   │     → recomputes the line total and the CGST/SGST halves through app/core/tax.py
   │     → writes the line, and bumps order.version
   │     → the @record audit decorator writes the before/after to audit_log
   │
   ├─ repositories issue every query through scoped(), which is
   │     select(Model).where(Model.restaurant_id == scope.restaurant_id)
   │
   └─ the route returns an OrderResponse built from the model, never the model itself
```

Read the third box again. **The client sent what was ordered and never what it costs.** The server
recomputes every price, tax and total from the menu. That is a security control, not a style
preference, and there is a test that sends a tampered price and asserts it is ignored.

---

## 7 · Identity, tenancy and access control

### Authentication is split from employment

A `user_account` holds credentials. An `employee` holds the employment profile. The link is
optional in one direction: an employee with no login is entirely normal, because a cleaner does not
need one, and a customer can authenticate without being an employee at all.

Passwords are hashed with argon2id. Refresh tokens are stored hashed. An unknown email and a wrong
password produce the identical error, so the login form cannot be used to enumerate accounts.
Deactivating an employee revokes every one of their sessions immediately, and so does a password
change and a role change.

### The tenant scope

```python
@dataclass(frozen=True, slots=True)
class TenantScope:
    organization_id: uuid.UUID
    restaurant_id: uuid.UUID
```

Two levels, because the threat model has two attackers. The organization is the hard boundary:
another organization's rows must be unreachable, full stop. The restaurant is the boundary inside
one organization, because "a manager reads another branch's staff" is its own line in the threat
table.

The scope is derived from the verified access token and never from anything the client can choose.
A `restaurant_id` accepted from a query parameter would make the whole mechanism decorative.

Every repository takes a scope as a **required positional argument with no default**. So the
failure mode "somebody forgot to scope this query" is a `TypeError` at construction time, not a
customer reading another customer's data. That is the structural half of invariant 1, the half that
does not depend on anyone remembering.

Two base classes, deliberately named differently:

- `OrgScopedRepository` filters on `organization_id`. Employees, accounts, roles.
- `RestaurantScopedRepository` filters on `restaurant_id`. Everything operational.

A reviewer can see which boundary a repository enforces from its declaration line rather than by
reading the query.

### Permissions, never role names

There are 55 permissions and 9 role templates. A role is a bundle of permissions; the code never
compares against a role name. Grants by role:

| Role | Rank | Permissions |
|---|---|---|
| Owner | 0 | 55 |
| Administrator | 10 | 22 |
| Manager | 20 | 47 |
| Chef | 30 | 15 |
| Store Manager | 30 | 17 |
| Accountant | 30 | 13 |
| Kitchen Staff | 40 | 10 |
| Waiter | 40 | 13 |
| Cleaner | 40 | 5 |

Lower rank is more senior. Rank exists because permissions alone cannot stop privilege escalation:
a manager and an owner can hold overlapping permissions, so a rule of "you may not grant what you do
not hold" would let a manager make themselves an owner. Two rules use rank instead.

- **Appointment** is sideways and downward, never upward. A manager may appoint another manager.
- **Password reset** is *strictly* more senior, with one exception for two owners. Appointing a peer
  is not escalation; acting as a peer is, because a password is the ability to *be* that person, and
  every order, void and audit row afterwards names the victim. The exception exists because a rule
  of strictly-more-senior would lock an owner out of their own restaurant with no recovery path.

### The permission split is the interesting design

Several lines were drawn deliberately and are worth understanding, because they are what makes the
model more than a checkbox grid.

- A **chef** holds `recipe.manage` and does not hold `cost.view`. A chef sees grams, not rupees.
- A **chef** holds `stock.produce` and not `stock.receive`. A kitchen turns ingredients into gravy;
  it does not sign for the sack at the door.
- An **accountant** holds `purchase.manage` and not `stock.receive`. The person who reconciles
  invoices can raise an order and can never book one in. That is separation of duties, for free.
- A **waiter** holds `order.settle` and not `order.void` or `order.discount`. The person at the
  table takes the money; cancelling a paid cash bill and comping a table are the classic leakage
  vectors.
- A **waiter** holds `kot.view` and not `kot.update`. The floor watches the kitchen and does not
  drive it.
- A **manager** does not hold `audit.view` or `report.financial.view`. The person who runs the floor
  is frequently the subject of the record, and a record its subject curates is not a record. The
  money screens are screens a manager does not have, rather than screens with blanks in them,
  because a disabled figure is an invitation to go looking for the endpoint.
- **Everyone** holds `performance.view.own`, and it is not removable by configuration. A score an
  employee cannot see is surveillance. The same score, visible with its inputs, is feedback.

### Declaration is enforcement

```python
def require_permission(permission: PermissionCode | str) -> Callable[..., Awaitable[Actor]]:
    code = str(permission)

    async def dependency(actor: ActorDep) -> Actor:
        if not actor.holds(code):
            raise PermissionDeniedError("permission.denied", "You do not have access to this.")
        return actor

    setattr(dependency, PERMISSION_MARKER, code)
    return dependency
```

Three things are happening here that matter.

The dependency **returns the actor it just authorised**, so the route writes
`actor: Annotated[Actor, Depends(require_permission(...))]` and there is no second lookup and no
chance of authorising one actor and then acting as another.

It **stamps a marker attribute**. A test walks the application's routing table and fails the build
if any route was registered without one. A check written inside a handler body would enforce just
as well and be invisible to that test, which is exactly how the one route that forgot gets shipped.

The refusal **does not name the missing permission**. Telling a waiter the exact string that would
unlock a screen is a map of the permission model.

### The token is not trusted as the final word

`current_actor` decodes the bearer token, then re-reads the employee and re-resolves their
permissions from the database on every request. A token minted before a role change would otherwise
keep working until it expired, and "revoked immediately" would quietly mean "revoked within fifteen
minutes".

---

## 8 · The data model

Eighty tables in fourteen domains. Conventions applied to every table and therefore never repeated:
`id` is a UUIDv7 primary key generated in the application, so keys are time-ordered without a
database round trip; `created_at` and `updated_at` are `timestamptz NOT NULL DEFAULT now()`;
tenant-owned tables carry `restaurant_id NOT NULL` and every index on them leads with it.

`restaurant_id` is carried even where a parent could supply it — an order line could reach it
through its order. That denormalisation is deliberate. It keeps every tenant filter a single index
seek and makes row-level security a one-line policy per table when it is switched on.

| Domain | Tables | What lives there |
|---|---|---|
| Tenancy & identity | 11 | Organisations, restaurants, accounts, employees, roles, assignments, login attempts |
| Restaurant setup | 5 | Dining areas, tables with their guest QR slugs, stations, tax groups and rates |
| Menu | 6 | Categories, items, variants, modifier groups, modifiers |
| Stock items & recipes | 5 | Ingredient and preparation masters, recipes, recipe lines |
| Inventory | 4 | Batches, the movement ledger, count sheets and their lines |
| Procurement | 5 | Suppliers, supplier items, purchase orders and lines, goods receipts |
| Orders | 16 | Orders, lines, modifiers, discounts, charges, invoices, credit notes, payments, the till |
| Waste | 2 | Reasons as a table, wastage events |
| Customers & feedback | 6 | Customers, preferences, consents, feedback, feedback lines, complaints |
| Communication & tasks | 7 | Conversations, participants, messages, attachments, tasks, task events, stream cursor |
| Shifts | 2 | Shift definitions, assignments with clock times |
| Performance & recognition | 5 | Score periods, scores, incentive weights, awards |
| Compliance | 2 | Findings, suppressions |
| System | 4 | Audit log, notifications, idempotency keys, the KOT stream cursor |

### The relationships that carry the product

```
organization ──< restaurant ──< everything operational

menu_category ──< menu_item ──< menu_item_variant
                       │              │  price and tax live HERE, never on the item
                       │              │  a half plate is a different price, recipe and cost
                       └──< modifier_group ──< modifier

stock_item ──< recipe ──< recipe_line >── stock_item      (nesting, depth ≤ 3)
                  │
                  └── versioned: a change is a NEW version, never an edit

stock_batch ──< stock_movement        APPEND-ONLY
                     type ∈ receipt | production | consumption | wastage |
                            staff_meal | complimentary | transfer | adjustment | count
                     basis ∈ theoretical | actual          ← invariant 7 lives on this column

order ──< order_line ──< order_line_modifier
  ├──< payment          append-only; a refund is a negative row, never a status change
  ├──< order_discount
  ├──< order_charge
  ├──< invoice ──< credit_note ──< credit_note_line
  └──< kot_ticket ──< kot_ticket_line
```

### Three modelling choices worth copying

**`staff_meal` and `complimentary` are separate movement types**, split out from `consumption`.
Both are real, both are large in Indian restaurants, and both look like theft when lumped in with
ordinary consumption. Separating them is what makes the variance number trustworthy.

**Unread state is a watermark, not a receipt row.** A conversation participant carries
`last_read_message_id`. The alternative, one row per message per person, multiplies rows by
participants for a fact nobody reads individually.

**Wastage reasons are a table, not an enum.** Their rows carry policy — whether a photo is required,
whether approval is required, which of the four waste stages they belong to. An enum cannot hold
policy.

### Recipes are versioned, and that is load-bearing

Changing a recipe creates a new version. Historical orders keep pointing at the version that was
live when they were placed. Without this, editing a recipe would rewrite food-cost history
retroactively, and last month's margin would change because somebody fixed a typo today.

---

## 9 · End-to-end data flows

This is the section to read if you only read one. Each flow traces a real act from a tap on a
screen to rows on disk.

### 9.1 · Sign in

```
LoginScreen
  → POST /api/v1/auth/login  { identifier, password }
      identifier is an email or a phone number
  → AuthService
      finds the account, verifies the argon2id hash
      on failure: records a login_attempt row and returns the SAME error
                  whether the account exists or the password was wrong
      after 5 failures: locked, and the next attempt is made to wait
  → if the employee is assigned to more than one restaurant:
      returns a sign_in_choice, and the client calls /auth/login/choose
  → mints an access token and a refresh token
      the access token carries employee_id, organization_id, restaurant_id, sid
      the refresh token is stored hashed, never in plain text
  → the client holds the access token in memory and refreshes on 401
```

On every subsequent request `current_actor` rebuilds the actor from the token and re-verifies it
against the database, as described in section 7.

### 9.2 · Loading the menu

```
MenuScreen mounts
  → TanStack Query calls GET /api/v1/staff/menu
  → MenuTreeService builds the whole tree in a BOUNDED number of queries
      categories, items, variants, modifier groups and modifiers
      a three-level tree is the classic N+1 trap, so a test asserts the query count
      regardless of menu size
  → the response is cached client-side; the budget is 200 ms
```

Price and tax come back on the **variant**. A waiter taking an order never sees a cost or a margin,
because `cost.view` is a separate permission and the response schema for a waiter does not carry the
field.

### 9.3 · Opening a table and taking an order

```
TableMapScreen  (/floor, behind order.view)
  → GET /api/v1/staff/floor
      every table with its status: free · occupied · reserved · cleaning · out_of_service
  → tap a free table
  → POST /api/v1/staff/orders  { type: dine_in, table_id, covers, waiter_id? }
      waiter_id needs order.assign; without it you may only open for yourself
  → OrderService
      computes business_date from the restaurant's timezone and business_day_start
        ← this is the denormalised column every report later groups on
      sets status = open, version = 1
      sets the table to occupied
  → the client navigates to /orders/{id}  (behind order.modify)

OrderScreen
  → POST /orders/{id}/lines  { variant_id, quantity, modifiers[], note? }
      the body never contains a price
  → OrderService.add_line
      loads the order FOR UPDATE, checks version
      reads the variant's current price and tax group
      computes cgst = round(value × rate / 2) and sgst likewise, PER LINE
        ← the halves are equal by construction; computing a total and halving it
          leaves an odd paisa somebody has to be given
      writes order_line and order_line_modifier rows, status = pending
      bumps order.version
```

An order is saved whole. Reordering a list a person arranged is one `POST .../reorder` naming every
active row once, inside one locked transaction, never two requests swapping two rows — which
half-fails silently.

### 9.4 · Sending to the kitchen, and the display

```
  → POST /orders/{id}/send
  → OrderService.send
      groups the pending lines by the STATION their variant routes to
      creates one kot_ticket per order per station, status = new
      creates kot_ticket_line rows carrying the modifiers and any allergy note
        ← the allergy was copied from the customer when they were attached;
          the kitchen never reads the customer table
      moves the order lines to sent
      bumps the restaurant's kot_stream_cursor revision

KitchenScreen  (/kitchen, behind kot.view)
  → GET /api/v1/staff/kot/tickets?station=tandoor
      budget: 50 ms with 200 open tickets, because a chef stares at this all night
  → GET /api/v1/staff/kot/stream          Server-Sent Events
      the connection opens and stays open
      every 500 ms the server runs ONE indexed query against the cursor
      a heartbeat every 15 s keeps proxies from closing an idle kitchen
      on reconnect the client sends Last-Event-ID and replay is INCLUSIVE (>=)
        ← several tickets can share a revision; an exclusive cursor would
          permanently lose the rest of a batch whose first event already arrived
      the session is re-checked EVERY TICK, because a stream opened at 9pm on a
      token revoked at 10pm must not still be running at 3am

  → the rail's buttons need kot.update:
      new → acknowledged → preparing → ready          one-way, never backwards
      a mistake is a remake with a reason, which is a row, not an edit
```

**`served` is not the kitchen's transition**, even though the timestamp lives on the ticket. A dish
is served when it reaches a table, which the kitchen cannot see. It is written from the order screen
by whoever carried it, behind permissions a waiter holds, and refused on every kitchen route. That
separation is the control against a rail being cleared of food that never left the pass: marking
everything ready settles nothing and hides nothing, it only makes the gap to `served_at` visible.

Those five timestamps — printed, acknowledged, started, ready, served — are the entire
kitchen-performance module and half of the customer-experience module. They are captured from day
one even though nothing reads them until the reports module.

### 9.5 · Settling the bill — the most important transaction in the system

Everything below happens in one transaction or not at all, and **the order matters**.

```
BillScreen  (/orders/{id}/bill, behind order.settle)
  → POST /orders/{id}/settle
      header:  Idempotency-Key: <uuid made when the person TAPPED>
      body:    payments[] with method and amount
  ┌──────────────────────── one transaction ────────────────────────┐
  │                                                                 │
  │ 1. CLAIM THE IDEMPOTENCY KEY                                    │
  │      written in the same transaction as the effect              │
  │      a duplicate arriving while the first runs waits on the     │
  │      unique index, then replays the finished response           │
  │                                                                 │
  │ 2. LOCK THE ORDER, check its version, and refuse a restaurant    │
  │      that cannot issue the document its GST scheme requires      │
  │      — before anything at all is written                        │
  │                                                                 │
  │ 3. RE-FREEZE TAX at the rate in force on the rate date, which   │
  │      is the MEDIAN of served, invoiced and paid                 │
  │      (CGST Act s.14 puts a supply on whichever side of a rate   │
  │       change two of those three events fall)                    │
  │      lines and charges are repriced while the order is still    │
  │      live, because a migration CHECK refuses to touch them one  │
  │      statement after it settles                                 │
  │                                                                 │
  │ 4. FREEZE THE THEORETICAL FOOD COST from the CURRENT recipe at  │
  │      today's unit costs, with the costing snapshot loaded once  │
  │      for the whole bill                                          │
  │                                                                 │
  │ 5. POST THEORETICAL CONSUMPTION                                 │
  │      each dish recipe's DIRECT components, and each modifier    │
  │      recipe's, times quantity, summed per stock item            │
  │      a preparation is consumed as itself — its onions were      │
  │      consumed when the preparation was produced                 │
  │      basis = theoretical                    ← invariant 7        │
  │      NEVER refused for want of stock: a bill must not fail      │
  │      because the book disagrees with the shelf                  │
  │                                                                 │
  │ 6. THE PAYMENTS MUST COVER THE BILL EXACTLY                     │
  │      checked against the figure AFTER the re-freeze             │
  │                                                                 │
  │ 7. NUMBER THE INVOICE under a lock                              │
  │      sequential per financial year, NO GAPS — GST law           │
  │      snapshot the restaurant's identity onto the invoice        │
  │      (name, address, GSTIN, FSSAI) so a later settings edit     │
  │      cannot rewrite a document already issued                   │
  │      write the payment rows against it                          │
  │                                                                 │
  │ 8. SETTLE THE ORDER LAST                                        │
  │      status = settled, settled_at set                           │
  │      send its tables to cleaning — or straight to free in busy  │
  │      hours, which is a floor.manage switch that turns itself    │
  │      off at the next business day                               │
  │      the audit decorator writes the row                         │
  │                                                                 │
  │ 9. RECORD THE IDEMPOTENCY RESPONSE                              │
  └─────────────────────────────────────────────────────────────────┘
```

A failure anywhere rolls back everything **including the idempotency claim**, so an honest retry
after a dropped connection runs again rather than replaying a failure. An error is never stored.

After settlement the order is immutable.

- Cancelling the invoice **on its day of issue** is a void. The order moves to `voided` and the
  invoice keeps its number, because a gap in the series is a GST problem.
- Anything after that day is a **credit note**. The order stays `settled` and a credit note with its
  own lines is issued against the invoice.
- A refund is a **negative payment row**, never a status on the original. Payments are append-only
  for the same reason stock is.

### 9.6 · Receiving stock, and where a batch comes from

```
Purchase order path (accountant or manager raises, store manager receives)
  → POST /staff/purchase-orders            supplier, lines, expected costs
  → the order is sent; it stays partially open on a partial delivery

Goods receipt  (/purchasing/orders/{id}/receive, behind stock.receive)
  → POST /staff/purchase-orders/{id}/receive
      header: Idempotency-Key
      body:   per line, TWO numbers, deliberately
                what the bill says
                what the scale says
  → ProcurementService
      ordered / invoiced / received are THREE separate numbers, never collapsed
      creates a stock_batch per line
          batch number, quantity received, expiry date, UNIT COST FROZEN, supplier, location
      writes a stock_movement of type receipt, basis = actual
      leaves the purchase order partially open if the delivery was short
```

Whether a real store manager types two different numbers into those two fields is what decides
whether the procurement module is worth anything. That is why the manual test script labels them in
plain words rather than as "quantity" and "variance".

A receipt without a purchase order is supported, because an ad-hoc market purchase is how a lot of
Indian restaurants actually buy vegetables. It still creates batches.

### 9.7 · Producing a preparation

```
StockProduceScreen  (/stock/produce, behind stock.produce — the chef's)
  → POST /staff/stock/production   { preparation, batch quantity }
  → InventoryService, in one transaction
      for each input in the preparation's recipe:
          select batches FEFO — ORDER BY expiry_date ... FOR UPDATE
            ← in SQL with a LIMIT, never a Python sort over every batch
          write consumption movements, basis = actual
      create ONE new stock_batch for the output
          its unit cost is frozen from what the inputs actually cost, now
          its shelf life is in HOURS, not days — a gravy dies in two
      write a production movement for the output
```

Consuming and producing in one transaction is what stops a half-made batch existing. `FOR UPDATE` on
the batch rows is what stops two concurrent productions overselling the same last sack; there is a
concurrency test written as real concurrent transactions rather than mocked.

### 9.8 · Logging waste

```
WasteScreen  (/waste, behind wastage.log — chef, kitchen staff, manager, store manager)
  → the screen's whole design target is UNDER TEN SECONDS on a phone
      item → preset quantity buttons → reason → photo → done
  → POST /staff/wastage
      header: Idempotency-Key
        ← a double-tapped Log in a kitchen is not a duplicate row, it is a second
          consumption and a food-cost figure that is wrong all month
  → WasteService, in one transaction
      writes the wastage_event
      writes the PAIRED stock_movement of type wastage, basis = actual
        ← never one without the other
      COMPUTES the cost from the batches the stock actually came out of
        ← never asks the person logging. A cook does not know what a kilo of paneer
          cost on the day it arrived, and asking gets a guess or stops them logging
      if the reason requires approval, it waits for somebody holding wastage.approve
        ← the people who log most of the waste do NOT hold that permission, and that
          separation is the control between a reason code and logging theft as waste
  → the rupee value is shown AFTER logging, never before
      showing it first suppresses honest reporting
```

### 9.9 · The guest, with a phone and a QR code

Two entry points, and which screens exist depends on which code was scanned.

```
?t=<table slug>              the sticker on the table
  → POST /api/v1/guest/session   { table_slug }
  → opens a session scoped to the MENU and nothing else
      a photographed sticker is worth the menu, which is on the wall anyway

?b=<bill token>              the QR printed on the bill
  → POST /api/v1/guest/session   { order_token }
  → opens a session scoped to THAT ORDER
      three tabs: the bill, the menu, and three feedback questions
  → POST /api/v1/guest/feedback   needs the bill token
      ← which is why staff cannot rate their own tables
```

The token is exchanged once and kept **in memory only**. Nothing is written to storage, because a
phone that opens this once should carry nothing away afterwards.

Guest responses expose no cost, no margin, no recipe and no employee name. That is not a filter
applied at render time; the guest response schemas do not have the fields, and a test fails the
build if one acquires a cost field. A separate test asserts no guest token reaches any staff route.

### 9.10 · The question the product exists to answer

```
Variance report  (/reports/variance, behind report.financial.view)
  → GET /api/v1/staff/reports/food-cost-variance?from=&to=

  THEORETICAL side                        ACTUAL side
  ────────────────                        ───────────
  stock_movement                          stock_movement
    WHERE basis = 'theoretical'             WHERE basis = 'actual'
      AND type = 'consumption'                AND type IN (consumption, wastage,
    written at settlement from                         staff_meal, complimentary,
    the recipe live at that moment                     adjustment, count)
                                            written by receipts, productions,
                                            waste logs and physical counts

                      variance = actual − theoretical
                      attributed per stock item, per dish, per period

  bounded by business_date on an index-backed path, ALWAYS
  the index leads with restaurant_id
```

The two sides are never summed into one consumption figure. That is invariant 7, and it is the
reason `basis` is a column rather than an inference.

Every metric on every report carries a comparison against yesterday or last week, because a number
with no baseline is not information, and drills through to the rows behind it.

### 9.11 · Audit, written by a decorator

```python
@record(action="order.settle", entity="order", key="order_id")
async def settle(self, actor: Actor, order_id: uuid.UUID, ...) -> Order:
    ...
```

The decorator loads the before state through a tenant-scoped repository, runs the method, loads the
after state, diffs them, and writes one `audit_log` row with the actor, the action, the entity, the
before and the after, and a reason where the act has one.

Four properties it keeps that a hand-written call broke, and did:

- **It is explicit.** The action, entity and key are written at the method. A reviewer reading the
  signature can say what the row will contain. Nothing infers an action from a method name.
- **It reads through a repository.** A decorator doing `session.get(Model, id)` would be the one
  unscoped read in the codebase, and invariant 1 has no exception for convenience.
- **It never records a credential.** Anything whose column name looks like a secret is dropped.
  Redacting at the call site worked until somebody added a column.
- **It ignores `created_at` and `updated_at`.** A timestamp moving is the fact that something was
  written, which the row's existence already says.

The real deliverable is the test that **fails the build when a mutating service method declares
neither an audit nor an exemption**, exactly as the route suite fails the build when a route declares
no permission. An insider's most valuable act is the one nobody recorded, and the call sites most
likely to be missed are the rare ones: the manual price override, the adjustment at the end of a bad
month, the role granted at eleven at night.

---

## 10 · Cross-cutting mechanics

### Idempotency

Required on every write whose effect is money or stock. The frontend refuses to send one of those
requests without a key, before it leaves the browser. Four rules:

1. **The key is the client's, made when the person tapped**, and scoped to the restaurant. It lives
   24 hours. A wrapper that invented a key per request would give every retry a new key, which is
   exactly the double booking the key exists to stop.
2. **The claim is written in the same transaction as the effect.** A duplicate arriving mid-flight
   waits on the unique index, then replays the finished response.
3. **Same key and same request is a replay; same key and a different request is a 409.** The second
   is a client bug, and replaying the first response for it would tell somebody their second
   delivery was booked when it was not.
4. **The request is identified by method, path and exact body.** A retry sends the same bytes.

### Concurrency

Optimistic locking on orders through a `version` column. Pessimistic `FOR UPDATE` on stock batches
and on invoice numbering, because those are genuine contention points where a retry loop would be
worse than a short wait. Concurrency tests are written as real concurrent transactions.

### The business day

```python
business_date_of(moment, timezone, day_starts_at)   # which day is this instant in?  (used at insert)
day_bounds_utc(date, timezone, day_starts_at)       # which instants are in this day? (used by reports)
```

They are inverses and are tested as inverses. If they ever disagreed, a report would count an order
that the order itself does not believe belongs to that day, and the discrepancy would be invisible
from either side alone.

An unknown timezone raises rather than falling back to UTC, because a fallback would silently shift
every date by five and a half hours and nobody would look. A naive datetime raises too.

Two more functions live beside them for the things that follow the **calendar** instead: an
invoice's date of issue and the financial year its number belongs to. The financial year boundary is
midnight and the business day boundary is 05:00, so a bill settled at 01:30 on 1 April belongs to
business day 31 March and to the *new* year's invoice series. They live in the same file as the rule
they differ from, so nobody reaches for the wrong one.

### Errors

One envelope, everywhere:

```json
{ "code": "order.already_settled",
  "message": "Order #1042 was settled at 21:14.",
  "details": { "order_id": "...", "settled_at": "..." },
  "issue": 1042 }
```

`code` is a stable string the frontend switches on and is **never shown to a person**. A person
reads `message` and quotes the issue number, which comes from a catalogue in
`app/core/issues.json`. `message` never contains internal detail — no stack traces, no SQL, no table
names.

A validation error names each field, its rule's code and what to type instead. The sentence comes
from `app/core/validation_messages.py`, never from Pydantic, whose wording for a format rule is the
regular expression itself. A `pattern=` without a sentence there fails the build.

A database refusal is a conflict, not a crash. Services pre-check for the good message, and the
error handler maps the race the pre-check cannot close, by SQLSTATE: unique or exclusion becomes
409, check becomes 422, foreign key becomes 409. The constraint name goes to the log and never to
the body. Any other integrity error is still a 500, because an unknown refusal is a bug to see, not
a message to soften.

### Why Server-Sent Events, and why polled

The kitchen display needs a live feed. The implementation polls a per-restaurant revision cursor,
once every 500 milliseconds, with one indexed query per tick. Three alternatives were rejected for
concrete reasons:

- **An in-process broadcast** is wrong the moment there are two workers, and then it fails silently
  and only under load.
- **Postgres `LISTEN`/`NOTIFY`** needs a connection held outside the pool for the life of the
  process, and pgbouncer in transaction-pooling mode — the likely production shape — drops it
  without erroring.
- **WebSockets** would buy bidirectionality that nothing needs, at the cost of a second protocol to
  operate.

The polled cursor has a property the others do not: **live delivery and reconnect replay are the
same code path**, so the reconnect test exercises the production path rather than a second
implementation of it.

The stream opens a database session per tick and closes it. A dependency-injected session would hold
one pooled connection for the whole life of a service — six screens, six connections, never
returned. It is the only place in the application that takes the session factory rather than a
session.

Each realtime surface has its own cursor table, per restaurant. A global Postgres sequence would
leak how busy every other tenant is.

### Performance budgets

Correctness rules, not aspirations, measured at p95 on staging with seeded data.

| Path | Budget | Why |
|---|---|---|
| Kitchen ticket list | 50 ms | A chef stares at this all night |
| Order create, add line | 150 ms | A waiter is standing at a table |
| Order settle | 400 ms | Writes order, payments, stock and audit atomically |
| Menu load | 200 ms | Cached client-side after the first load |
| Manager dashboard | 800 ms | Tolerable; loads once |
| Any report | 3 s | Beyond this it must become async with a progress state |

Enforced alongside them: no N+1, asserted by query-count tests around list and detail endpoints; no
unbounded result set, default page 50 and maximum 100, clamped rather than rejected; every filter and
sort index-backed; no `SELECT *`; aggregations always bounded by `business_date`.

### Observability

Structured JSON logs with a request id, and a redaction filter installed at the handler so it cannot
be bypassed. Every line carries the tenant and the actor, set in `current_actor` — which is the one
place in the request where both facts become known.

---

## 11 · The frontend

### Two applications from one toolchain

Vite builds two Rollup entry points, `index.html` for staff and `guest.html` for guests. The aliases
are `@shared`, `@staff` and `@guest`, and an eslint rule forbids staff and guest importing each
other.

The API is same-origin in production, and the Vite dev proxy keeps it same-origin in development
too, so no CORS-only code path exists that production never exercises.

### One module may call fetch

`src/shared/api.ts` is the only file exempted from the no-`fetch` eslint rule. Everything else
reaches the API through TanStack Query calling into it. That module owns four things:

- the access token and the refresh-on-401 handshake, with `/auth/login`, `/auth/refresh` and
  `/auth/logout` explicitly excluded from refreshing, since refreshing on refresh's own 401 is a
  loop by construction;
- the error envelope type and the frontend's own issue numbers, asserted against the backend
  catalogue by a test;
- the list of endpoints that **require** an idempotency key, refused client-side if one is missing;
- money as a string all the way to the render, so no float touches a rupee.

Server state lives in Query. UI state lives in local component state. There is no global store,
because nothing has yet genuinely needed one.

### Navigation is one list, built from permissions

There used to be two hand-kept navigation lists, the header's and the home page's. Eight screens
appeared in both and ten appeared only on the home page, and four separate code comments recorded
somebody noticing a gap and patching one side of it. Two lists that must not overlap will overlap
again within two modules.

Now there is one list. A `where` field partitions each screen into the header or the home page,
never both, and a test refuses a duplicate and refuses a route that appears in neither. Entries
carry a permission or `null` for everyone, and are built from permissions rather than role names.

Route guards are **presentation only**. The server authorises every request on its own, so a route
reached by typing its URL refuses with a readable message rather than a blank screen.

### The four surfaces

The design system distinguishes four contexts with genuinely different constraints: the manager's
desktop, the waiter's phone in one hand, the kitchen display read at two metres through steam by
somebody wearing a glove, and the guest's own phone, which is a device we do not own on a network we
do not control, used once by a person who has never seen the product.

The kitchen rules are the strictest and the most concrete: at least 20px base text and 40px order
numbers, no modals, no scrolling, elapsed time always visible and counting, and colour never the
only signal. The manual test for that screen is to stand two metres away and read it, wearing one
glove.

Guest strings are deliberately unlearnable: it works the first time or it does not work.

### Bundle discipline

At most 250 KB gzipped per persona application, with route-level code splitting. Exactly one staff
route is lazily loaded — the analytics screen with its charts — so that a waiter on a three-year-old
Android does not download them. There is no charting library in `package.json` at all; the charts
are hand-drawn SVG, and a discipline test keeps it that way.

---

## 12 · Testing

```
        /\        End-to-end (Playwright)             ~15, critical journeys only
       /  \       Integration (API + real Postgres)   ~60% of the suite
      /____\      Unit (services, pure logic)         ~35% of the suite
```

Integration-heavy on purpose. The risk in this application is in how the pieces connect: settling an
order must write stock movements, freeze a cost and emit an audit row. A unit test of each piece
proves nothing about that.

**Real Postgres through testcontainers, never SQLite.** The code relies on `timestamptz`, `NUMERIC`,
partial indexes, `jsonb`, `FOR UPDATE` and CHECK constraints. SQLite would pass tests that production
fails.

### The four generic suites, which are the highest-value tests here

They enumerate the application rather than being written per feature, so a new endpoint is covered
the moment it is registered and nobody has to remember.

1. **Tenant isolation.** For every registered staff route, restaurant A's token must not read, write
   or even confirm the existence of restaurant B's resources. Expect 403 or 404, never 200.
2. **Permission matrix.** Every route against every role, asserted against a declared table.
3. **Persona separation.** No guest token reaches a staff route. No staff field appears in a guest
   response schema.
4. **Route declaration.** Every route declares a permission, or the build fails. Default deny,
   structurally.

### Where the risk is concentrated

- **Property-based tests on money and units.** Tax splits sum to the total for any price and any
  rate; unit conversions round-trip without losing precision; a discount can never make a total
  negative. Example-based tests miss exactly the inputs that break these.
- **Golden tests on costing.** The dish costs the seed validator computes become fixtures. If a
  refactor moves Butter Chicken by one paisa the build fails. This protects the number the product
  sells.
- **Concurrency tests as real concurrent transactions.** Two settles of one order, two orders
  consuming the last batch, a double-submitted payment with one key.
- **Mutation testing on costing and stock only.** It answers what coverage cannot: do the tests
  actually fail when the logic is wrong? Too slow for everything, exactly right for those two.
- **Migration tests.** Upgrade, downgrade, upgrade, against real Postgres, in continuous
  integration.
- **Contract test.** The backend enums and the frontend enums must match, so they cannot drift.

### One harness detail that matters more than it looks

Every request in the test harness gets **its own session**, closed when the request ends, exactly as
production does. The test's own session is a different one over the same rolled-back transaction.

An earlier harness yielded one long-lived session to every request, which made the suite
structurally unable to observe a rollback: a handler that flushed and then raised left its work
visible to the next request and to the assertions. The account lockout shipped completely
inoperative underneath 262 passing tests for that reason, and so did the refresh-token revocation.

> A test that shares a transaction with the code under test cannot prove durability.

---

## 13 · Build, migrations and seed data

```
make dev            docker compose up: api, db, frontend
make test           pytest + vitest
make lint           ruff + mypy + eslint + tsc          the fast subset while working
make check          THE BLOCKING GATE: lint + test + docs and seed audits + dep audits
make migrate        alembic upgrade head
make revision m="…" alembic autogenerate
make seed           the demo restaurant with menu, recipes, stock and orders
```

Gates: ruff with a security and timezone ruleset, mypy in strict mode, eslint with typescript-eslint
strict plus react-hooks, and `tsc --noEmit`. Zero warnings tolerated. A warning that is acceptable
gets an inline suppression with a reason; an unexplained suppression is a review rejection. Warnings
that accumulate become invisible, and then the real one arrives and nobody sees it.

**Never edit a migration that has been applied on staging.** Write a new one.

### Seed data, and why it is the hardest part of the product

Indian restaurants of this size keep almost no records. There is no historical data to import and
often nothing to import it from. So the demo and every report were built against a deterministic
generator: 120 days of orders, kitchen tickets, stock movements, waste, feedback and ratings from a
fixed seed, producing identical figures every run.

It plants **14 signals** on purpose — a dish whose variance drifts, a supplier whose weights are
consistently short, a shift where waste spikes — and the reports test asserts that each is actually
surfaced. Seeded organisations carry `is_demo = true` and are excluded from all reporting.

The data is plausible rather than perfect. It includes a skipped waste log, two voided orders and
missing feedback, because a data set with no gaps teaches you nothing about how the screens behave
when there are gaps.

There is also a recipe library of 223 dishes with confidence tiers, and a market rate layer of 122
real prices with a city index, so costs start from something real rather than from invented numbers.

---

## 14 · Deployment and operations

The dependency list is deliberately three items long: a Docker container, PostgreSQL, and
S3-compatible object storage. No cloud-proprietary queues, functions, auth or databases. The cloud
is a deploy-time choice, not an architectural one.

First target is GCP Cloud Run, which scales to zero, with managed Postgres and Cloudflare R2 for
media and Pages for the static application. Expected pilot cost is nearly nothing. The Azure
equivalent is Container Apps plus a small Postgres Flexible Server, the same image and the same code.

Consequences that had to be designed in rather than bolted on: background work — nightly rollups,
expiry alerts — runs as a scheduled container invocation rather than a cloud-specific scheduler
binding, and media URLs are pre-signed through a storage abstraction rather than constructed from a
provider's hostname.

Staging went up in week one on purpose, so that deployment was never a week-four surprise. There are
runbooks for staging, for production and for restore.

---

## 15 · How to recreate this from scratch

Build it as vertical slices. Each module ends with something demonstrable on staging. None of them
is "the backend for X with a UI arriving later" — that pattern produces four weeks of invisible
progress and then a bad week.

| # | Module | Delivers | Days |
|---|---|---|---|
| M00 | Foundation | Repo layout, Docker Compose, Makefile, all linters, test harness with real Postgres, CI, Alembic, config that fails boot when wrong, JSON logging with redaction, the error envelope, health endpoints, staging deploy | 1 |
| M01 | Identity, roles, permissions | Accounts, employees, roles, assignments, login with lockout, session revocation, the permission catalogue seeded by migration | 3 |
| M02 | Restaurant setup | Dining areas, tables, stations, tax groups; timezone, currency and `business_day_start` | 2 |
| M03 | Menu | Categories, items, variants, modifiers; price on the variant; the whole tree in bounded queries | 3 |
| M04 | Stock items and recipes | The ingredient and preparation masters, nested versioned recipes, the cost rollup | 4 |
| M05 | Inventory ledger | Batches, the append-only movement ledger, FEFO, counts | 4 |
| M06 | Procurement | Suppliers, purchase orders, goods receipts with the two numbers | 3 |
| M07 | Orders and point of sale | The largest module: orders, lines, tax, invoices, credit notes, payments, the till | 7 |
| M08 | Kitchen display | Tickets per station, the five timestamps, the event stream | 4 |
| M09 | Waste | Reasons with policy, events paired to movements, under ten seconds to log | 2 |
| M10 | Customers, feedback, guest app | The first guest surface; consents, erasure, the QR flows | 4 |
| M11 | Communication and tasks | Conversations, messages, attachments, the task board | 4 |
| M12 | Shifts | Shift definitions, assignments, clock in and out | 2 |
| M13 | Dashboards and reports | Where the product shows its face; the variance report | 5 |
| M14 | Audit and notifications | The audit decorator and its declaration test; the issue catalogue | 3 |
| M15 | Seed generator | 120 deterministic days and the 14 planted signals | 3 |
| M16 | Hardening | Security and performance pass | — |
| M17 | Workload fairness | Performance measurement with its morale guardrails | — |
| M18 | Compliance | Licence-risk findings, each citing its instrument | — |
| M19 | Analytics | Trends, hand-drawn charts, lazily loaded | — |

### Order of operations inside a module

1. Write the spec. Name the decisions and their reasoning before writing code.
2. Write the migration. Get the shape right first; everything downstream inherits it.
3. Write the failing tests, including the regression test for any bug being fixed.
4. Build the service, then the repository, then the route, then the screen.
5. Run the full gate and read its **exit code**.
6. Do the manual pass by hand, on a real device where the screen is meant for one.
7. Update the documentation in the same change as the code.

### What to get right first, because it is expensive later

- **Tenancy in the repository base class**, before there is a second table. Retrofitting it means
  auditing every query ever written.
- **Money as `Decimal` and as a string in JSON**, before there is a second endpoint.
- **The business day**, before there is a first report. A 01:30 order booked to the wrong day looks
  entirely normal and surfaces months later as a month-end total out by one night's takings.
- **The ledger as append-only**, before anything writes stock. Converting a mutable quantity column
  into a ledger after the fact means the history you most want is the history you do not have.
- **The four generic suites**, at M01. They are what makes every later module safe by default.
- **Staging**, in week one.

---

## 16 · Traps that cost real time

Every one of these was paid for once. They are collected here because they are the kind of thing a
second team would pay for again.

**Read the exit code, not the last lines.** `make check | tail` reports `tail`'s status, so a
failing gate looks like a passing one and the error scrolls past. This produced a false "clean"
claim twice. Run `make check > check.log 2>&1; echo $?` and read the number.

**And read the red lines even when the exit code is zero.** The coverage gate printed
`FAIL Required test coverage of 95% not reached` in red and exited 0, for an entire range of
values, because the tool computed its printed verdict and its exit status from differently rounded
numbers. If a red line and an exit code disagree, one of them is a bug and it is worth an hour.

**`ruff format --check` fails on unformatted files, and running `ruff format` rewrites them and
reports nothing.** A "fix" that consists of running the formatter will look like it did nothing.

**Never fill an Indian rate, threshold or commencement date from memory.** Research returned
stale-but-confident law three times in one session. Look it up and cite the instrument. And never
conflate *in force* with *notified but not in force* with *unsettled* with *unverified*. Only the
first is safe to build on, and only the first may block a user.

**A seeded order number can stop the till.** Date-prefixed numbers from the generator 500'd every
table open until a guard was added, and the same bug existed one table over. When you find a bug
from generated data, sweep for its siblings before fixing the one you found.

**00:00 on business date D is the *end* of D, not its start.** Anchor every time fixture to
`business_day_start` rather than to midnight.

**A test sharing a transaction with the code under test cannot prove durability.** Section 12 tells
the full story; two security features shipped inoperative underneath a green suite.

**Two hand-kept lists that must not overlap will overlap.** Whether it is navigation, enums or a
permission table, derive one from the other or assert their relationship in a test.

**Windows and containers do not share file-watching.** Both the API and the Vite dev server need
polling enabled when the source lives on a Windows host and the process runs in a container.
Without it the dev server keeps serving the previous version of a file, hot reload stays silent, and
the only symptom is a browser that disagrees with the editor.

---

## Closing

The through-line of every decision above is the same: **make the wrong thing hard to do, rather than
documenting that it is wrong.**

A repository that cannot be constructed without a tenant scope. A route that fails the build if it
declares no permission. A service method that fails the build if it declares neither an audit nor an
exemption. A guest bundle that cannot contain staff code because it is a different Rollup entry
point. A ledger that has no update path. A validation rule that fails the build if nobody wrote a
sentence a human can read.

Each of those replaces a rule somebody has to remember at 11pm with a rule the machine enforces.
That is the whole method, and it is what makes a codebase this size safe for one person to keep
changing.
