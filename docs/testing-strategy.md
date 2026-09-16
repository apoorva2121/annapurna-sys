# Testing Strategy

Two testers with different strengths. **I am fast, exhaustive and literal — I verify what the code
was told to do. You are slow, sparse and contextual — you notice when what it does is wrong.** The
strategy assigns each of us the work we are actually good at.

Every module passes both before it is done. No exceptions, including for modules that "obviously
work".

---

## Part 1 — Automated testing (mine)

### The harness opens one session per request

**Guardrail G-2.** The `api` fixture in `backend/tests/conftest.py` gives every request its own
session, closed when the request ends — exactly what `app.core.db.get_session` does in production.
The test's own `db_session` is a *different* session over the same rolled-back transaction.

This is not a detail. The earlier harness yielded one long-lived session to every request, which
made the suite structurally unable to observe a rollback: a handler that flushed and then raised
left its work visible to the next request and to the assertions, because nothing ever closed the
session. The account lockout shipped completely inoperative underneath 262 passing tests for that
reason, and the replayed-refresh-token revocation did too.

Two consequences when writing tests:

- **After a request, re-read through `db_session`** rather than trusting an object loaded before it.
  The two sessions have separate identity maps, and that is the point.
- **A test that must see a real `COMMIT` on disk** — one proving a write survives the process, not
  merely the transaction — takes the `fresh_database` fixture instead. `test_lockout_persistence.py`
  is the worked example.

> A test that shares a transaction with the code under test cannot prove durability.

## The shape

```
        /\        E2E (Playwright)          ~15 total, critical journeys only
       /  \       Integration (API + real Postgres)   ~60% of the suite
      /____\      Unit (services, pure logic)         ~35% of the suite
```

Integration-heavy on purpose. This app's risk is in *how the pieces connect* — an order settling
must write stock movements, freeze a cost, and emit an audit row. A unit test of each piece proves
nothing about that.

**Real Postgres via testcontainers, never SQLite.** We rely on `timestamptz`, `NUMERIC`, partial
indexes, `jsonb`, `FOR UPDATE` and CHECK constraints. SQLite would pass tests that production fails.

### The four generic suites — the highest-value tests in the project

These enumerate the application rather than being written per feature, so **a new endpoint is
covered the moment it is registered.** Nobody has to remember.

1. **Tenant isolation.** For every registered staff route: restaurant A's token must not read, write
   or even confirm the existence of restaurant B's resources. Expect 403/404, never 200.
2. **Permission matrix.** Every route × every role, asserted against a declared table. A waiter
   voiding an order, a cleaner reading financials, a chef changing prices — all explicitly denied.
3. **Persona separation.** No guest token reaches any staff route (ADR 0009). No staff field appears
   in a guest response schema.
4. **Route declaration.** Every route declares a required permission. A route without one fails the
   build — default-deny, enforced.

### Per-module suites

- **Unit** — every service method, including its failure paths. Business rules tested in isolation.
- **Integration** — every endpoint: happy path, validation failure, permission denial, not-found,
  and conflict.
- **Query count** — `assert_max_queries(n)` around list and detail endpoints. This is how N+1 stays
  fixed rather than being fixed once (`docs/engineering-standards.md` §3).
- **Migration** — `upgrade → downgrade → upgrade` against real Postgres.
- **Contract** — `app/core/enums.py` matches `frontend/src/shared/enums.ts`, asserted, so the two cannot
  drift.

### Specialist testing where the risk is concentrated

- **Property-based tests (Hypothesis) on money and units.** Tax splits must sum to the total for any
  price and any rate; unit conversion round-trips must not lose precision; a discount can never make
  a total negative. Example-based tests miss exactly the inputs that break these.
- **Golden tests on the costing engine.** The dish costs computed by `seed/validate.py` become
  fixtures. If a refactor changes Butter Chicken's cost by one paisa, the build fails and we find out
  why. This protects the number the whole product sells.
- **Concurrency tests.** Two simultaneous settles of one order; two orders consuming the last batch;
  a double-submitted payment with the same idempotency key (ADR 0010). These are written as real
  concurrent transactions, not mocked.
- **Mutation testing (`mutmut`) on the costing and stock modules only.** It answers the question
  coverage cannot: *do the tests actually fail when the logic is wrong?* Too slow for the whole
  codebase; exactly right for these two.
- **Load test (k6)** before production: KDS under 200 concurrent tickets, 50 orders/minute settling.

### Coverage

80% lines overall as a signal. **100% on the paths that move money, stock or permissions** — that is
a requirement, not a signal. Coverage is a floor for finding untested code, never a goal in itself;
a 90% suite of assertion-free tests is worth nothing.

### What I do beyond running tests

After the tests pass and before I hand a module to you, I do an **adversarial review pass** on my own
diff, looking for what tests structurally cannot catch:

- Tenant leakage in a hand-written query
- A permission check in the route instead of the service
- An N+1 hidden behind a lazy relationship
- Money touching a float; a naive datetime; a unit assumed rather than converted
- An unbounded query, a missing index for a new filter
- A client-supplied price or total being trusted
- PII in a log line
- An error message leaking internals
- The threat-model question from the module spec: *what would an insider do with this?*

Findings get fixed before you ever see the module. The point of your time is to catch what I cannot,
not to trip over what I could have.

---

## Part 2 — Manual testing (yours)

### Why this exists

Automated tests verify the specification. They cannot tell us the specification was wrong. Only you
can notice that the flow takes six taps when a waiter has two free seconds, that the KDS text is
unreadable from across a room, that "Void" and "Cancel" sitting next to each other will cause a
mistake at 9pm, or that the number on screen is technically correct and practically meaningless.

**You are not double-checking my work. You are testing the thing I cannot test: whether it is any
good.**

### What you get, per module

A file at `docs/manual-tests/MXX-<module>.md` containing:

- **Preconditions** — exactly which login, which data, which URL. Nothing assumed.
- **Numbered steps** — one action each, written so there is no interpretation required.
- **Expected result** per step, stated concretely ("the total reads ₹1,240.00", never "the total is
  correct").
- **A Pass/Fail box** per step.
- **Adversarial steps** — deliberate attempts to break it, including security probes you run
  yourself (see below).
- **An exploratory charter** — 10 minutes of unscripted use with a stated goal, because scripts only
  find what someone thought of.

Format and a worked example: `docs/manual-tests/README.md` and `docs/manual-tests/M01-identity.md`.

### The rules

1. **Follow the steps exactly the first time.** If a step is ambiguous, that is a finding — tell me.
2. **Report failures as: step number + what you expected + what you saw.** A screenshot beats a
   description. The `request_id` in the error message, if there is one, finds everything in the logs.
3. **A failed step stops that section.** Do not work around it; the workaround hides the bug.
4. **Time the exploratory charter.** Ten minutes, honestly. It is where the best findings come from.
5. **Anything that felt awkward is a finding**, even if nothing was broken. "This took too many taps"
   is a real bug in a product used during dinner rush.

### You test security too — by hand

Some security failures are trivially checkable by a human and easy to miss in tests. Every module's
script includes probes like:

- Change an id in the URL to another restaurant's record. → Expect denied.
- Log in as a waiter and try to reach the owner's dashboard URL directly. → Expect denied.
- Log out, press Back. → Expect no cached data visible.
- Open the guest QR link and try a staff URL. → Expect denied.
- Have an admin deactivate your account while you are logged in, then click anything. → Expect
  immediate logout.

These take two minutes and they verify the controls in `docs/security.md` actually work in the real
browser, not just in a test harness.

### Time expected

**20–40 minutes per module.** Seventeen modules, so roughly 8–10 hours of your time across the
project. That is the price of the app not being broken, and it is cheap.

---

## Part 3 — Beyond modules

**Integration testing** at the end of each phase: the cross-module journeys that no single module
owns. Order → KOT → stock consumption → cost → waste → feedback → dashboard, verified end to end
with real numbers checked against `seed/validate.py`.

**Regression suite.** Every bug found — by me, by you, in staging — gets a test that reproduces it
*before* the fix. That test lives forever. This is how the app stays fixed.

**Acceptance testing** before production: a full day of simulated service against seeded data, all
four personas, checked against the 14 planted signals in `docs/seed-data.md`. If the dashboards
surface those fourteen findings, the analytics chain works.

**User acceptance**, if your restaurant contact will give an hour: sit them in front of the waiter
app and say nothing. Watch where they hesitate. Every hesitation is a design defect.
