# Tooling — plugins, skills and when to add them

A standing note of what tooling exists, what is installed, and **at which point in the build each
one becomes worth adding**. Installing tools before there is anything for them to act on is noise;
the value is in adding each one at the moment it starts paying.

Checked and recorded 2026-09-08.

## Installed and in use

| Tool | Added | What it does here |
|---|---|---|
| `update-config` skill | M00 prep | Built the docs/seed validation hook below |
| `docx` skill | discovery | Read the original vision document |
| `xlsx` skill | ongoing | Your task tracker, `Apoorva-Tasks.xlsx` |
| **Project hook** (`.claude/settings.json`) | M00 prep | Runs `scripts/audit_docs.py` / `seed/validate.py` on every docs or seed edit — pipe-tested, silent when clean, reports the exact failure when not |

**Plugins installed: none.** Your plugin catalogue is empty — I searched it for python/fastapi/
postgres/security/testing/react and it returned nothing. There is nothing to add, so nothing has
been added.

## Scheduled — add at this point, not before

| When | Tool | Why then, and not now |
|---|---|---|
| **M00, on first commit** | `code-review` skill | Needs a diff. Becomes step 7 of the module loop in `docs/sdlc.md`. |
| **M00** | `run` skill | Launch and screenshot the app once there is an app |
| **M00** | `fewer-permission-prompts` | Run after a few sessions of real command history, so the allowlist reflects actual usage rather than guesses |
| **M01, after auth exists** | `security-review` skill | First module with a real attack surface. Then per phase. |
| **After M01** | `skill-creator` → a project `/module` skill | The 11-step loop is written down but unproven. Encode it once M00–M01 have actually run it twice — a skill written from a theory is fiction. |
| **M03 / M07 / M08** | `design` skill | Waiter and KDS mockups **before** coding them. The KDS especially: it is read at 2m through steam, and getting that wrong in code is expensive. |
| **M13** | `dataviz` skill | Load before the first chart is written, not after |
| **M13 / M17** | `artifact-diagramming` | Visual ERD and the workload-distribution explainer |
| **Phase 3** | `claude-api` skill | The AI advisor (vision doc §26) |
| **Ongoing** | `simplify` skill | After any module that ends up larger than its estimate |

## External tooling to install (you, not me)

Blocking or near-blocking, in order:

1. **Docker Desktop** — hard blocker for M00 (Compose + testcontainers-Postgres). Nothing starts
   without it.
2. **GitHub remote + working auth** — no remote configured, `gh` not installed, and the GitHub MCP
   is currently failing with `Authorization header is badly formatted` (a bad token, not a missing
   feature). Needed for CI.
3. **Cloud accounts, week 1** — GCP or Neon (Postgres), Cloudflare (static hosting + R2), Sentry
   free tier. ~$0–20/month at pilot scale (ADR 0005).
4. `uv` — optional; pip works fine.

Already present and correct: Python 3.13.9, Node 24.19, npm 11.17, git 2.55.

## The rule

Add a tool at the module where it first earns its place, record it in the table above with the date,
and say what it is for. A tool nobody can explain the purpose of gets removed.
