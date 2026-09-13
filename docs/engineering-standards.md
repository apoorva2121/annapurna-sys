# Engineering Standards

Rules that apply to every module. The Definition of Done in `docs/sdlc.md` enforces them; CI blocks
on most. The goal throughout: **simple code that a tired person can read at 11pm and change safely.**

## 1 · Layering — the one rule that keeps this simple

```
route  →  service  →  repository  →  model
```

| Layer | Does | Never does |
|---|---|---|
| **route** | parse request, call one service, shape response | business logic, DB access, permission logic |
| **service** | business rules, permission checks, transactions, orchestration | build SQL, know about HTTP |
| **repository** | queries, always tenant-scoped | business rules, decide what is allowed |
| **model** | table shape | anything else |

A route that touches the ORM is a review rejection. A repository with an `if` about business policy
is a review rejection. This single rule is why tenant isolation and permission checks can be tested
generically instead of endpoint by endpoint.

**Skipping layers is allowed in exactly one direction:** a service may call another service. A
repository may never call a service, and nothing may call a route.

## 2 · Simplicity budget

Complexity is a cost paid by whoever reads the code next. Enforced limits:

| Metric | Limit | Enforced by |
|---|---|---|
| Cyclomatic complexity per function | **10** | `ruff C901`, `eslint complexity` |
| Function length | 50 lines | `ruff PLR0915` (soft), review |
| Function parameters | 5 (use a dataclass/schema beyond that) | `ruff PLR0913` |
| File length | 400 lines | review |
| Nesting depth | 4 | `ruff PLR1702` |
| React component | 200 lines | review |
| Module public API | if it needs a diagram to explain, split it | review |

**No abstraction before the third occurrence.** Two similar blocks stay duplicated. The third gets a
shared function. Premature abstraction is the most common way a codebase this size becomes
unreadable, and it is much harder to undo than duplication.

**No design patterns by name.** No factories, no strategies, no registries, unless the concrete
problem demands one and the ADR explains why.

## 3 · Performance budgets — time and space

Correctness rules, not aspirations. Violations fail CI where a test can express them.

**Queries**
- **No N+1.** Integration tests assert query counts (`assert_max_queries(n)`). This is the single
  most common performance defect and it is entirely preventable.
- **No unbounded result set.** Every list query has a `LIMIT`. Default page 50, maximum 100.
- **Every filter and sort is index-backed.** If a new query needs an index, the migration adds it in
  the same PR. `EXPLAIN` output goes in the PR description for any query over three joins.
- **No `SELECT *`** — name columns, so adding a column cannot silently bloat a hot path.
- **Aggregations are bounded by `business_date`,** always, and that index leads with `restaurant_id`.

**Latency budgets** (p95, measured on staging with seeded data)

| Path | Budget | Why |
|---|---|---|
| KDS ticket list | **50 ms** | A chef stares at this screen all night |
| Order create / add line | 150 ms | Waiter is standing at the table |
| Order settle | 400 ms | Writes order + payments + stock + audit atomically |
| Menu load | 200 ms | Cached client-side after first load |
| Manager dashboard | 800 ms | Tolerable; loads once |
| Any report | 3 s | Then it must become async with a progress state |

**Memory / space**
- Never load a full table into memory. Stream or paginate.
- Report exports stream to the response, never build a list of 50,000 dicts.
- The seed generator writes in batches of 1,000, not one 38,000-row insert.
- Frontend: no unbounded client-side arrays. Virtualise any list over 200 rows.
- Initial JS bundle ≤ 250 KB gzipped per persona app; route-level code splitting.

**Algorithmic**
- Recipe cost rollup is recursive but memoised per request — a preparation used by six dishes is
  computed once, not six times. Depth is capped at 3 (ADR 0006).
- FEFO batch selection is `ORDER BY expiry_date LIMIT n` in SQL, never a Python sort over all batches.

## 4 · API conventions

```
/api/v1/staff/...      employee surface  (ADR 0009)
/api/v1/guest/...      customer surface
```

- **Resources are plural nouns.** `/orders`, `/orders/{id}/lines`. Actions that are not CRUD become
  sub-resources: `POST /orders/{id}/settle`, not `POST /settleOrder`.
- **Errors use one envelope, always:**
  ```json
  { "code": "order.already_settled", "message": "Order #1042 was settled at 21:14.",
    "details": { "order_id": "...", "settled_at": "..." } }
  ```
  `code` is a stable string the frontend switches on. `message` is human-readable English, safe to
  show a user, and **never contains internal detail** — no stack traces, no SQL, no table names.
- **A validation error names each field, its rule's code, and what to type instead:**
  ```json
  { "code": "request.invalid", "message": "Please fix the 2 highlighted fields.",
    "details": { "fields": [
      { "field": "gstin", "code": "field.format",
        "message": "Use the 15-character GSTIN, for example 27AAPFU0939F1ZV." } ] } }
  ```
  The sentence comes from `app/core/validation_messages.py`, never from Pydantic, whose wording for
  a format rule is the regular expression itself. A `pattern=` without a sentence there fails the
  build (`tests/test_validation_messages.py`). On screen, `fieldErrors` puts each sentence under its
  field and `errorProps` lists them all in the notice, so no problem is ever dropped.
- **A database refusal is a conflict, not a crash.** Services pre-check (`name_exists`) for the good
  message; `register_error_handlers` maps the race the pre-check cannot close by SQLSTATE — unique
  or exclusion → 409 `conflict.duplicate`, check → 422 `request.rejected`, foreign key → 409
  `conflict.missing`. The constraint name goes to the log, never the body. Any other
  `IntegrityError` is still a 500: an unknown refusal is a bug to see, not a message to soften.
- **An order is saved whole.** A list a person arranges (`seq`) is reordered by one `POST
  .../reorder` naming every active row once, in one locked transaction — never by swapping two rows
  in two requests, which half-fails silently. Rules in `app/services/reorder.py`.
- **Pagination is cursor-based** (`?cursor=&limit=`) on anything that grows without bound. Offset
  pagination is allowed only on fixed-size master data.
- **Idempotency-Key required** on money- and stock-affecting POSTs (ADR 0010).
- **Validation is Pydantic, explicit, allow-list.** `model_config = {"extra": "forbid"}` everywhere —
  mass assignment is not possible if unknown fields are rejected.
- **The server never trusts a client-supplied price, total, tax or cost.** It recomputes from the
  menu and recipe. A client sends *what* was ordered, never *what it costs*. This is a security
  control, not a style choice.
- **Timestamps are ISO-8601 with offset.** Money is a **string** in JSON (`"1240.00"`), never a
  number, so no JavaScript float ever touches a rupee.

## 5 · Frontend

- Data access is **TanStack Query only**. No `fetch` in a component, ever.
- Server state lives in Query; UI state in local component state. No global store until something
  genuinely needs it.
- Components are presentational; a `features/<module>/` folder owns hooks, API calls and types.
- No prop drilling beyond two levels — colocate or use context for that subtree.
- Every mutation has explicit `pending` / `error` / `success` handling. No silent failures.
- Follow `docs/ui/conventions.md` for the four surfaces. Simple, dense, legible — never clever.
- Forms: one library (`react-hook-form` + `zod`), schema mirrored from the API contract.

## 6 · Naming

- Tables and columns `snake_case`, singular table names (`order`, not `orders`).
- Python `snake_case`; TypeScript `camelCase` for variables, `PascalCase` for components/types.
- Booleans read as assertions: `is_active`, `has_expired`, `can_void`.
- Timestamps end in `_at`; dates end in `_date` or `_on`; durations carry the unit (`prep_minutes`,
  `shelf_life_hours`).
- Money columns end in `_amount`, `_total`, `_cost`, or `_price` — never a bare `value`.
- No abbreviations except the domain's own: `kot`, `po`, `gst`, `fefo`.

## 7 · Tooling gates

**Python** — `ruff` (lint + format), `mypy --strict`, `pytest`. Ruff rulesets: `E,F,W,I,N,UP,B,C4,SIM,ARG,PTH,RUF,S` (`S` = bandit security rules).
**TypeScript** — `eslint` (typescript-eslint strict + react-hooks), `prettier`, `tsc --noEmit`, `vitest`.
**Both** — `pre-commit` runs the fast subset locally; CI runs everything.

```
make lint     # ruff + mypy + eslint + tsc, zero warnings tolerated
make test     # pytest + vitest
make check    # lint + test + migration up/down + query-count assertions
```

**Zero warnings.** A warning that is acceptable gets an inline suppression with a reason comment; an
unexplained suppression is a review rejection. Warnings that accumulate become invisible, and then
the real one arrives and nobody sees it.

## 8 · Comments and docs

- Comment **why**, never **what**. The code says what.
- Every non-obvious business rule cites its source: `# GST is per line, not derived at display time (ADR 0004)`.
- Public service methods get a one-line docstring stating the invariant they uphold.
- No commented-out code. Git remembers.
