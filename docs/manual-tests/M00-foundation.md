# M00 · Foundation — Manual Test

**Module:** M00 · **Est. time:** 20 min · **Tester:** you · **Environment:** local Docker Compose

> **Why not staging.** You chose to defer the staging deploy to day 2, so acceptance criterion 10
> of the module spec is explicitly *not* covered here. Everything else is. This is the one section
> of the Definition of Done that M00 does not meet, and it is deferred deliberately rather than
> quietly.

M00 has no features, so this script does not test behaviour a restaurant would recognise. It tests
the promises every later module is built on: the stack runs, the gate blocks, errors leak nothing,
and PII does not reach the logs.

---

## Preconditions

- Docker Desktop running (`docker ps` returns without error)
- Repo on branch `feat/m00-foundation`
- `cp .env.example .env` — the file is gitignored and the defaults work as-is for local
- One terminal for `make dev`, a second for the checks

---

## A · Happy path

| # | Step | Expected | P/F |
|---|---|---|---|
| A1 | `make dev` in a fresh terminal | Three containers build and start: `db`, `api`, `web`. `db` reports healthy before `api` starts. | ☐ |
| A2 | Open `http://localhost:5173` | The page loads and shows the version panel — git SHA, build time, env `local`. It is deliberately plain. | ☐ |
| A3 | Look at the page again | It shows **real data fetched from the API**, not a hardcoded string. Confirm by stopping the `api` container and reloading: the page must show its error state, not a blank screen. | ☐ |
| A4 | Restart `api`, reload the page | Recovers to the success state without a hard refresh loop. | ☐ |
| A5 | `curl http://localhost:8000/api/v1/health` | `{"status":"ok"}` | ☐ |
| A6 | `curl -i http://localhost:8000/api/v1/ready` | `200`, and `"ready":true`, `"database":true`, `"migrations_at_head":true`. | ☐ |
| A7 | `curl http://localhost:8000/api/v1/version` | Returns `git_sha`, `built_at`, `env`. | ☐ |
| A8 | Edit any file under `backend/app/`, save | uvicorn reloads within a few seconds without you restarting anything. | ☐ |

---

## B · Validation and the quality gate

| # | Step | Expected | P/F |
|---|---|---|---|
| B1 | `make check` | Passes end to end, **zero warnings**, ending with `make check: clean`. | ☐ |
| B2 | Introduce a deliberate defect: add `import os` to `backend/app/main.py` and save. Run `make lint`. | **Fails** on the unused import. This proves the gate blocks rather than decorates. Undo it afterwards. | ☐ |
| B3 | Stop the `db` container (`docker compose stop db`), then `curl -i .../api/v1/ready` | `503`, with `"database":false`. `/health` still returns `200` — it must not depend on the database. | ☐ |
| B4 | Restart `db`, wait for healthy, re-curl `/ready` | Back to `200`. | ☐ |

---

## C · Permissions

**Not applicable to M00.** There are no roles, no users and no protected routes yet — the staff and
guest route trees exist but are empty. The permission matrix suite starts in M01, and
`docs/manual-tests/M01-identity.md` is already written for it.

The one thing worth confirming now is that the seam is real:

| # | Step | Expected | P/F |
|---|---|---|---|
| C1 | `curl -i http://localhost:8000/api/v1/staff/` and `.../api/v1/guest/` | Both return `404` with the standard envelope. Neither returns a route listing or a server error. | ☐ |

---

## D · Security probes

| # | Step | Expected | P/F |
|---|---|---|---|
| D1 | `curl -i http://localhost:8000/api/v1/nothing-here` | `404` with `{"code":"http.404", ...}` **plus a `request_id`**. No stack trace, no file path, no framework name. | ☐ |
| D2 | Check the response headers on any request | `X-Request-Id` is present. Send your own (`-H "X-Request-Id: mytest123"`) — it comes back unchanged. | ☐ |
| D3 | Send a hostile request id: `-H "X-Request-Id: $(python -c 'print("x"*300)')"` | The response header is **not** your 300-character value — the server replaced it. An unbounded client value must never reach the logs. | ☐ |
| D4 | In the `make dev` terminal, find the log line for one of your requests | It is a single line of JSON containing `request_id`, `route` and `duration_ms`. The `route` shows the **full** path (`GET /api/v1/health`), not a router-relative one. | ☐ |
| D5 | Open `http://localhost:8000/api/docs` | Interactive docs load — this is `ENV=local`. | ☐ |
| D6 | Stop the stack. Set `ENV=staging` and `DEBUG=true` in `.env`, run `make dev` | The api container **fails to start**, with a clear message that DEBUG is forbidden outside local. This is the assertion, not a checklist item. Set it back to `local`/`true` afterwards. | ☐ |
| D7 | With `ENV=staging`, `DEBUG=false`, start again and open `/api/docs` | **404.** Docs are an inventory for an attacker anywhere but local. Restore `.env` to `local` afterwards. | ☐ |
| D8 | Delete the `DATABASE_URL` line from `.env`, run `make dev` | The api **fails to boot loudly** naming the missing setting — it does not start and fail later. Restore the line. | ☐ |

---

## E · Usability

| # | Step | Expected | P/F |
|---|---|---|---|
| E1 | Open `http://localhost:5173` on your phone (same wifi, use your machine's LAN IP) | The page loads and is readable. It is unstyled beyond basics — that is correct for M00. | ☐ |
| E2 | `make help` | Prints the commands you actually need, in plain language. | ☐ |
| E3 | From a clean clone in a scratch folder: `make setup && make check` | Works with no undocumented step. If you had to do anything not in the output, that is a failure — say what. | ☐ |

---

## F · Exploratory charter — 10 minutes

**Goal: make the API leak something it should not, or make a log line contain a phone number.**

Ideas worth trying: send malformed JSON to any endpoint; send a huge header; request
`/api/openapi.json` under `ENV=staging`; put a phone number in a request id or a query string and
then search the container logs for those ten digits; kill Postgres mid-request.

Notes:

```


```

---

## Result

- Steps passed: ____ / 23
- Failures (step number → expected → saw):

```


```
