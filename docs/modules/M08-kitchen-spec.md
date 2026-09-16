# M08 · Kitchen / KOT — Module Spec

**Depends on** M07 (orders, lines, the send path) and M02 (stations).
**Status** — spec written 2026-09-16, before any code, per `docs/sdlc.md` step 1.
Build log: `docs/plan/m08-build-log.md`.

Tables: `kot_ticket`, `kot_ticket_line`, `kot_stream_cursor`.
Endpoints: `GET /kot/tickets`, `PATCH /kot/tickets/{id}/status`,
`PATCH /kot/tickets/{id}/lines/{line_id}/status`, `POST /kot/tickets/{id}/lines/{line_id}/remake`,
`GET /kot/stream`.
Screens: KDS per station, ticket detail, remake request.

---

## Why this module is different from every module before it

Everything built so far answers a request and stops. This one holds a connection open for a whole
service, on a screen nobody touches, read from two metres away by someone wearing a glove. Three
things follow from that, and each is a decision below rather than an implementation detail:

1. **A dropped connection must lose nothing.** A kitchen display that silently stops updating is
   worse than one that is obviously broken, because the chef keeps believing it.
2. **The event loop is now visible.** A 300 ms block nobody noticed in a request/response world
   becomes a stutter on a screen that is watched continuously. This is the module the guardrails
   table named as the trigger for paying down P1-9, and it is paid here.
3. **The UI contract is functional, not cosmetic.** `docs/ui/conventions.md` says base font ≥ 20px,
   order numbers ≥ 40px, no modals, no scrolling, colour never alone. At two metres those stop being
   style preferences and become the difference between a working screen and a decorative one.

---

## Research — what binds this module, checked 2026-09-16

**Nothing in `docs/compliance-rules.md` binds the kitchen display.** It touches no menu text, no
restaurant identity, no tax, no price and no customer data. A KOT is an internal instruction, not a
document anybody may demand. Checked rather than assumed, because CLAUDE.md makes that file bind
every module from here on — the finding is "no rule applies", which is a result and is recorded.

**What the external review already decided for this module**
(`docs/audit/external-review.md`, the deferred-to-M08 row):

| Finding | What it says | Where it lands |
|---|---|---|
| **S2** | `kot_ticket_line` has no timestamps, so per-dish prep time is unmeasurable | migration 0030 adds `started_at`, `ready_at`, `served_at` to the line |
| **M4** | `request_context_middleware` is a `BaseHTTPMiddleware`; contextvars reset before a streaming body runs, and the access line has no status code | chunk A — a pure-ASGI middleware, **a prerequisite for SSE rather than a tidy-up** |
| **X6** | SSE plus scale-to-zero: instances are killed, requests are capped, fan-out does not cross instances | decision 4; `min-instances=1` recorded in the deploy notes |
| **print agent** | a physical KOT printer will exist one day | decision 9 — a design note, no code |
| **P1-9 / G-6** | argon2 runs on the event loop; 8 call sites, ratcheted | chunk A2 — paid here, baseline lowered |

**`docs/schema.md` §7 already sketches both tables.** The sketch is followed except where decisions
1, 3 and 6 amend it, and the file is updated in the same PR — G-7, and CLAUDE.md's rule that a doc
updated later is a doc that is wrong.

**`OrderLineStatus` already carries `preparing` and `ready`** — M07 put them there so this module
needs no enum migration on the order side — and already carries `returned`, which is M09's hook.

---

## The nine decisions that matter

### 1 · A KOT is a *round*, not an order. One ticket per send, per station

`docs/schema.md` §7 sketches `kot_ticket` as "one per order per station". That is wrong, and it is
worth being precise about why, because the wrong version looks tidier.

A table orders starters, then twenty minutes later orders mains. In every real kitchen that is two
pieces of paper. If the second send appends to the first ticket, one of two things has to happen:
either the ticket that was already `ready` is dragged back to `new` — destroying the `ready_at` that
half of M13 and M17 are built on — or the new dishes are added to a ticket the chef has already
cleared off the rail and will never look at again. The first loses the measurement; the second loses
the food.

So: **`send()` creates one ticket per station that has lines in *this* send.** A ticket's membership
is immutable — lines are never added to an existing ticket. `sequence_in_order` records that this is
round 2 of order 42, because "the second KOT for table six" is a thing people say.

The consequence for the display is the point of the design: a station's rail shows rounds, oldest
first, each with its own clock. That is what a kitchen actually works from.

### 2 · Routing is snapshotted at send, never joined at display

`kot_ticket.station_id` is written from `menu_item.station_id` at the moment of the send and never
recomputed. A restaurant that moves biryani from the tandoor to the main kitchen next month must not
rewrite last night's tickets, and a query that joined through to the live menu would do exactly
that. The same reasoning as `order_line.unit_price` being copied rather than joined (M07), applied
to routing instead of money.

A station that has since been deactivated still holds its history and still renders. A ticket is
never orphaned by an edit in settings.

### 3 · Recovery is a revision cursor, and events are idempotent state

This is the decision the "reconnect loses nothing" test is really testing.

Every write to the kitchen — a ticket created, a status moved, a line marked ready — bumps a
**per-restaurant revision counter** and stamps the affected tickets with it. `GET /kot/stream`
delivers, as SSE, every ticket at or after the client's cursor, then keeps delivering as the counter
advances. The SSE `id:` field carries the revision, so a browser resuming a dropped stream sends
`Last-Event-ID` and the server replays from there. Nothing is lost because nothing was ever *only*
in flight: the stream is derived from the table, not from a queue.

**The counter is per restaurant, not a global sequence.** A global sequence is one line of SQL and
leaks the platform's cross-tenant write volume to every kitchen screen — a client watching its own
`id:` values jump by four hundred learns how busy other restaurants are. `kot_stream_cursor` is one
row per restaurant, bumped with `UPDATE … RETURNING`, which also makes the cursor dense and readable
in a log line. One bump per *transaction*, not per row: a send that creates three tickets gives all
three the same revision, because they are one kitchen event.

**Replay is inclusive, and duplicate delivery is by design.** A client resumes at
`revision >= Last-Event-ID`, not `>`. If a connection dies after the first of three events sharing a
revision, an exclusive resume would lose the other two forever. An inclusive one re-sends all three
— which costs nothing, because **every event is a complete ticket state keyed by ticket id**, not a
delta. Applying the same state twice is a no-op by construction. A delta protocol would have needed
exactly-once delivery, which over a network to a wall tablet is not a thing that exists.

### 4 · The stream polls a cursor. Not `LISTEN`/`NOTIFY`, and not an in-memory fan-out

Three candidates, and the reasons the other two lose are worth writing down, because the losing ones
look more sophisticated:

- **An in-process asyncio broadcast** is the fastest and is wrong the moment there are two workers,
  which is the deployment ADR 0005 already describes. A screen connected to worker B would never see
  a ticket written by worker A. It fails silently and only under load — the worst shape of bug.
- **Postgres `LISTEN`/`NOTIFY`** is the textbook answer and needs a dedicated connection held
  outside the pooled async session for the life of the process. Managed Postgres behind pgbouncer in
  transaction-pooling mode — the likely production shape — **drops `LISTEN` registrations without
  erroring**. A correct implementation that quietly receives nothing is precisely the failure this
  module must not have.
- **A polled revision cursor** is one indexed query per connection per tick. It is the same code
  path for live delivery and for reconnect replay, so the reconnect test exercises the production
  path rather than a second implementation of it. It works across workers, across restarts, and
  behind any pooler.

Tick interval **500 ms**, putting worst-case delivery at 500 ms against a 1 s budget, with a **15 s
heartbeat comment** so an idle stream is distinguishable from a dead one, and `retry: 3000` in the
stream so the browser's own backoff is server-controlled.

This is the honest trade: a small, constant amount of database work in exchange for a delivery
mechanism with no invisible failure mode. If a restaurant ever runs enough screens for the polling
to matter, the fix is a shared per-process poller behind the same repository method — a backlog row
with a trigger condition, not an abstraction built before its third occurrence.

### 5 · The kitchen owns `ready`. The floor owns `served`

`seed/organization.yaml` already grants `kot.view` **and** `kot.update` to the chef, the kitchen
staff and the manager, and grants the waiter `kot.view` **only**. That existing design is followed
rather than amended, and it draws the line exactly where it belongs:

- `new → acknowledged → preparing → ready` is the kitchen's, behind `kot.update`.
- `served` is set from the **floor**, by M07's existing serve path, behind the order permissions the
  waiter already holds. A dish is served when it reaches the table, and the kitchen cannot see the
  table.

So `PATCH /kot/tickets/{id}/status` refuses `served` with a message naming the order screen, and
`OrderService.mark_served` writes `served_at` down onto the ticket and its lines. The waiter's KDS
is genuinely read-only, which is also why it can be left open on a phone without being a risk.

`cancelled` is nobody's transition: a ticket is cancelled by its order's lines being cancelled
(decision 7), never by a button on the rail.

### 6 · Late is measured against the standard, and the two are never merged

`menu_item_variant.prep_minutes` is the standard. The ticket's own timestamps are the actual. A
ticket is **late** when elapsed since `printed_at` exceeds the **maximum** `prep_minutes` across its
lines — maximum, not sum, because a station cooks a round in parallel and summing would declare
every four-dish ticket late on arrival.

The standard is copied onto `kot_ticket.target_minutes` at creation, for the same reason prices are
copied: re-deriving it later from a menu that has since been edited would rewrite history. The gap
between `target_minutes` and `ready_at − printed_at` is a real operational number and belongs to
M13. Neither value ever overwrites the other — CLAUDE.md invariant 7's shape, applied to time.

### 7 · A cancelled dish cancels its kitchen work, in the same transaction

M07 already cancels an order line with a reason and refuses to delete a line that has been sent.
This module completes that: cancelling a line cancels its `kot_ticket_line`, and a ticket whose
lines are all cancelled becomes `cancelled` itself and leaves the rail. One transaction, because a
kitchen that keeps cooking a cancelled dish is the exact operational failure a KOT system exists to
prevent.

The reverse does **not** hold. A ticket going `ready` settles nothing and cannot cancel an order
line. The kitchen never writes money.

### 8 · A remake is new work, and the original line keeps its history

`kot_ticket_line.status = 'remake'` with `remake_reason` is **terminal on the original line**. The
remade dish arrives as a **new ticket** at the same station, flagged `is_remake`, so it appears on
the rail as fresh work with its own clock rather than reviving a line the chef has already cleared.

A remake is *not* automatically a wastage event. The dish may have been sent back for being cold and
is about to be reheated, not binned. M09 links the two — `wastage_event.order_line_id` exists for
exactly this — but the person logging the waste decides, because a system that silently books waste
teaches people to stop remaking food. Recorded here as M09's hook, built in M09.

### 9 · The print agent is designed now and built never (this month)

A real kitchen wants paper as well as a screen, and printer drivers are explicitly out of scope for
month 1 (CLAUDE.md). The design that keeps that door open costs nothing today: **the stream is the
print queue.** A future local print agent is an SSE client with a cursor of its own, holding
`kot.view`, printing every ticket at or after its cursor and persisting the cursor after the paper
comes out. It needs no new endpoint and no new table — that is the payoff of decision 3's replayable
cursor, and it is written here so nobody later "adds a print queue".

---

## Not in scope

- Physical printers and drivers (above).
- Offline queueing on the KDS. The screen shows a connection banner and recovers on reconnect
  (decision 3); it does not queue writes. Full offline sync is out of scope for month 1.
- Bump-bar and hardware key input.
- Course timing — fire the mains when the starters clear. Real, and a backlog row.
- Per-dish station overrides at order time. Routing comes from the menu item.
- Prep-time analytics screens. The timestamps are captured here; M13 reads them.

---

## Deliverables

### Migrations

- **0030 · `kot_ticket`, `kot_ticket_line`, `kot_stream_cursor`** — including S2's three line
  timestamps and decision 6's `target_minutes`, the composite `(id, restaurant_id)` foreign keys
  every tenant-owned table in this codebase uses, and the two indexes `docs/schema.md` names.
- **0031 · `kot.view` / `kot.update` and their role grants**, seeded by migration as M01 requires.
  Both codes already exist in `seed/organization.yaml`, so the subset test guarding G-9 passes
  without a design amendment.

### Backend

- `app/models/kitchen.py` — `KotTicket`, `KotTicketLine`, `KotStreamCursor`.
- `app/repositories/kitchen.py` — tenant-scoped; ticket-number allocation under the same advisory
  lock pattern as `next_order_number`; the rail query; the cursor bump; the stream query.
- `app/services/kitchen.py` — creation from a send, the transition state machine, remake,
  cancellation propagation.
- `app/api/v1/staff/kot.py` — five routes plus the stream.
- Changes in `app/services/orders.py`: `send()` creates tickets; `mark_served()` stamps them;
  `cancel_line()` propagates.
- **Chunk A**: `request_context_middleware` becomes pure ASGI and logs `status_code` (M4).
- **Chunk A2**: `hash_password` / `verify_password` move to `asyncio.to_thread`; the audit's argon2
  baseline drops (P1-9, G-6).

### Endpoints — every one declares a permission

| Method | Path | Permission | Notes |
|---|---|---|---|
| `GET` | `/staff/kot/tickets` | `kot.view` | by station, by status; the 50 ms budget lives here |
| `GET` | `/staff/kot/tickets/{ticket_id}` | `kot.view` | detail, with lines and modifiers |
| `PATCH` | `/staff/kot/tickets/{ticket_id}/status` | `kot.update` | `acknowledged` / `preparing` / `ready` |
| `PATCH` | `/staff/kot/tickets/{ticket_id}/lines/{line_id}/status` | `kot.update` | one dish ready before the rest |
| `POST` | `/staff/kot/tickets/{ticket_id}/lines/{line_id}/remake` | `kot.update` | reason required |
| `GET` | `/staff/kot/stream` | `kot.view` | SSE; `Last-Event-ID`; heartbeat |

Every path parameter gets a victim row in the tenant-isolation suite — a ticket belonging to
restaurant B, fetched with restaurant A's token, is a 404 and not a 403.

### Frontend

- `staff/screens/KitchenScreen.tsx` — the rail. One station, chosen and remembered per device.
- `staff/screens/KitchenTicketScreen.tsx` — ticket detail and the remake form. A route, **not a
  modal**: a chef cannot dismiss a dialog with wet hands.
- `staff/api/kitchen.ts` — queries, mutations, and the stream hook.
- `shared/sse.ts` — a `fetch`-based SSE reader. The browser's own `EventSource` cannot carry an
  `Authorization` header, and this application's access token lives in memory, never in a cookie
  (`frontend/src/shared/api.ts`). Putting a token in the query string would write it into every
  proxy log, so the stream is read from a `fetch` body with the same header, the same
  refresh-on-401 path, and explicit backoff.
- A **mechanical readability test**, in the shape of the existing `brandChecklist.test.ts`: the KDS
  screens use only type-scale steps at or above 20px, order numbers at or above 40px, no `Dialog`,
  and no status conveyed by colour alone.

### Seed

`make seed` gains open tickets across stations at plausible ages — one fresh, one mid-prep, one
already late — so the rail is not empty on first look and so the late threshold is visible without
waiting twenty minutes. Two seeded orders keep a second round, exercising decision 1.

---

## Threat question — *what would an insider do with this?*

**Clear a dish that never arrived.** `ready` on the rail is cheap and satisfying. The control is that
`ready` is not `served`: money and service completion both hang off the floor's action, not the
kitchen's, and the two are stamped by different people holding different permissions (decision 5). A
cook marking everything ready inflates nothing and hides nothing — it makes the gap between
`ready_at` and `served_at` visible instead.

**Erase a bad night.** Every transition is one-way through the state machine: `ready` does not go
back to `preparing`, and a ticket already `served` does not move at all. Correcting a genuine mistake
means a remake with a reason, which is a row, not an edit. There is no delete.

**Watch another restaurant.** The stream is the only long-lived connection in the product and the
only place a cursor is handed to a client. It is per restaurant (decision 3), scoped by the same
repository scope as every other read, and a cursor taken from another tenant's stream selects nothing
rather than something. The tenant-isolation suite gets a streaming case, not only a
request/response one — G-3's rule that every security assertion has an HTTP-level test.

**Hold the door open.** An authenticated client could open many streams and hold them. A per-token
concurrent-stream cap, and the stream ends when its access token expires rather than outliving it: a
connection opened at 9pm must not still be authorised at 3am on a token revoked at 10pm. **This is
the one place in the product where revocation and a long-lived connection meet**, and the answer is
that the stream re-checks the session on each tick rather than trusting the handshake.

---

## Schema review checklist (G-13)

1. **What cannot be reconstructed later?** The five ticket timestamps and, after S2, the three line
   timestamps. They are captured from the first day; when a dish started cooking is recoverable from
   no other row.
2. **Where did it come from?** `is_remake` and `sequence_in_order` distinguish fresh work from
   repeated work, and first round from second. Without them, M13's "how long do mains take" silently
   averages remakes into standards.
3. **Who did it?** `acknowledged_by` and `ready_by` attribute the kitchen's actions, because M17's
   workload fairness is built on who actually did the work and cannot be backfilled.
4. **Money?** None. The kitchen never writes money. Asserted by a test, not by intention.
5. **Tenant?** `restaurant_id NOT NULL` on all three tables, with composite foreign keys to
   `(order.id, restaurant_id)`, `(order_line.id, restaurant_id)` and `(station.id, restaurant_id)`.
6. **Time?** All `timestamptz`; `business_date` on the ticket, taken from the order, so a 01:30
   ticket counts to the previous business day like everything else.
7. **Append-only?** No. A ticket is a live working row; its immutability is the state machine. The
   *order* side's trigger already refuses everything except the kitchen columns on a settled order —
   which is precisely what this module writes.

---

## Acceptance criteria

**Function**

1. Sending an order creates exactly one ticket per station represented in that send, containing only
   the lines of that send.
2. A second send creates a second ticket with `sequence_in_order = 2`; the first is unchanged,
   including its timestamps.
3. Ticket numbers restart each business day and are unique per restaurant per business day.
4. `new → acknowledged → preparing → ready` each stamp their timestamp and their actor; each
   transition is refused out of order with a readable message.
5. A line may be marked ready individually; the ticket goes `ready` when its last uncancelled line
   does, and not before.
6. `served` is refused on the KOT routes and set only by the order's serve path, which stamps
   `served_at` on the ticket and its lines.
7. Cancelling an order line cancels its ticket line in the same transaction; a ticket with no
   uncancelled lines becomes `cancelled`.
8. A remake marks the original line `remake` with its reason and creates a new ticket flagged
   `is_remake` at the same station.
9. A ticket is late when elapsed exceeds `target_minutes`, which was copied at creation and does not
   move when the menu is edited.

**Realtime**

10. A ticket created by a send appears on an open stream **within 1 second**.
11. A client that disconnects, misses three kitchen events, and reconnects with `Last-Event-ID`
    receives all three — asserted by dropping the connection mid-service, not by unit-testing the
    query.
12. The stream sends a heartbeat within 15 s of silence, and declares `retry: 3000`.
13. A stream whose session is revoked closes within one tick.

**Performance**

14. `GET /kot/tickets` for a station returns **under 50 ms** with **200 open tickets** in the
    restaurant, measured against seeded data, with a query-count assertion proving it is not an N+1.

**Security**

15. Every route declares a permission; a waiter token is accepted on the reads and refused on every
    write.
16. Restaurant A cannot read, transition or stream restaurant B's tickets — including with a
    `Last-Event-ID` taken from B's stream.

**Quality**

17. `make check` clean, zero warnings, the argon2 baseline lowered, and the KDS readability test
    green.

---

## Chunks — three PRs, as `docs/modules.md` requires

| PR | Chunk | What |
|---|---|---|
| 1 | A | Pure-ASGI request context middleware, `status_code` on the access line (M4) |
| 1 | A2 | argon2 off the event loop; audit baseline lowered (P1-9, G-6) |
| 1 | B | Migration 0030 + models + `docs/schema.md` §7 rewritten + enums |
| 1 | C | Migration 0031: `kot.view` / `kot.update` and their grants |
| 1 | D | Repository + ticket creation from `send()`, numbering, routing snapshot |
| 2 | E | The transition state machine, the timestamps, per-line ready, remake |
| 2 | F | The revision cursor, `GET /kot/stream`, heartbeat, `Last-Event-ID` replay |
| 2 | G | Reconciliation with M07: serve stamps down, cancel propagates, late derivation |
| 3 | H | KDS rail, ticket detail, remake, the `fetch`-based SSE hook, readability test |
| 3 | I | Seed, adversarial review, second reader, manual script, deploy + print-agent notes |

Full `make check` at the end of each PR, not after every chunk — the reason is in
`docs/plan/m07-build-log.md` and has not changed.

---

## Risks, recorded before they are discovered

| Risk | Why it is real here | What is done about it |
|---|---|---|
| The stream works locally and not behind a proxy | Buffering proxies hold `text/event-stream` until a buffer fills | `X-Accel-Buffering: no` and `Cache-Control: no-store` on the response; checked in `make smoke-prod` |
| Polling load grows with screens | One query per connection per 500 ms | Measured against the 50 ms budget with 200 tickets; a shared poller is a backlog row with a trigger condition, not a guess |
| Test flakiness around timing | Every assertion here is about elapsed time | Time is injected, never slept on; the one genuine timing test (heartbeat) gets a generous bound |
| The readability rules decay | They are the easiest thing to break in a hurry | The mechanical test, in the shape of the brand checklist that already works |
| A long stream outlives its session | New in this module; nothing else stays connected | Re-check per tick (threat question), with a test that revokes mid-stream |
