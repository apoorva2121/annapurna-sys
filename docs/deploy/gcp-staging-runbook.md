# Staging on GCP — the runbook

**What this is.** The one-time setup for remediation chunk **R7** (and **R4**, "one origin", which
was merged into it because the code cannot be verified without deploying it). Follow it once. After
that, `git push` to `main` deploys, and `.github/workflows/deploy-staging.yml` does every step
automatically.

**Read this first, it changes what you click:** Cloud Run and Neon both scale to zero, and this
runbook keeps them there. Staging costs **₹0 while nobody is using it** if you follow the
`min-instances=0` choice below. The only way to get a bill you did not expect is to set
`min-instances=1`, which exists for a live restaurant's kitchen display and is *wrong for staging* —
see §9.

**Prerequisites.** A Google account with a payment method, a Neon account, and admin rights on the
`apoorva2121/annapurna-sys` repository. Nothing else. `gcloud` is installed for you by the
workflow; on your laptop it is optional, and everything below can be done in a browser.

---

## 0 · What is already done

Built and committed, so your console time is short:

| Piece | Where |
|---|---|
| One origin — the API serves the built SPA | `backend/app/core/spa.py`, 9 tests |
| `python -m app.bootstrap` — the first org, restaurant and owner | `backend/app/bootstrap.py`, 6 tests |
| `make smoke-prod BASE=…` — G-14's smoke test | `scripts/smoke_prod.py` |
| The deploy pipeline itself | `.github/workflows/deploy-staging.yml` |

The workflow is **inert until §7**: its first step checks for the repository variables and stops with
a sentence naming what is missing.

---

## 1 · Neon — the database

Postgres, free tier, per ADR 0005. **100 compute-hours per month**, 0.5 GB storage. That is about
400 hours at the minimum 0.25 CU, so it cannot run continuously for a whole month — which is fine,
because it auto-suspends when idle and staging is idle most of the time.

1. Sign in at **neon.com** → **New Project**.
2. **Name:** `restaurant-os-staging`
3. **Postgres version:** **16** — match `docker-compose.yml`; do not take the newest offered.
4. **Region:** **AWS ap-south-1 (Mumbai)**, or the closest to `asia-south1`. Cross-region adds a
   round trip to every query and M13 has latency budgets.
5. Create it, then open **Connection Details**.
6. **Copy the POOLED connection string.** This is the one choice on this page that matters. It
   contains `-pooler` in the host. Cloud Run scales to several instances and each opens its own
   pool; the direct string exhausts Postgres connections, the pooled one does not.
7. Change the scheme from `postgresql://` to **`postgresql+asyncpg://`** — SQLAlchemy needs the
   driver named. Then **delete `?sslmode=require` if present**: asyncpg rejects that parameter.

You should end up with something shaped like:

```
postgresql+asyncpg://USER:PASSWORD@ep-xxxx-pooler.ap-south-1.aws.neon.tech/neondb
```

8. In **Settings → Backups**, confirm point-in-time restore is on. Free tier gives 6 hours, which
   is enough for staging.

Keep that string on your clipboard for §4. **Do not paste it into a file in the repository.**

---

## 2 · GCP project and billing

1. **console.cloud.google.com** → project picker → **New Project**.
   - **Name:** `restaurant-os`
   - Note the **Project ID** it generates (e.g. `restaurant-os-472913`) — you need it in §7.
2. **Billing** → link a payment method. Required even for free-tier usage.
3. **Billing → Budgets & alerts → Create budget.** This is the step that protects you, so do not
   skip it:
   - **Scope:** this project only
   - **Amount:** ₹3,000/month
   - **Alert thresholds:** **50%, 80%, 100%** — i.e. ₹1,500 / ₹2,400 / ₹3,000, matching
     `docs/observability.md` §9
   - **Email** yourself on each
4. **APIs & Services → Enable APIs.** Enable these four:
   `run.googleapis.com`, `artifactregistry.googleapis.com`, `secretmanager.googleapis.com`,
   `iamcredentials.googleapis.com`

---

## 3 · Artifact Registry — where the image lives

**Artifact Registry → Create repository:**

- **Name:** `restaurant-os`
- **Format:** **Docker**
- **Mode:** Standard
- **Region:** **`asia-south1` (Mumbai)** — must match `REGION` in the workflow
- **Encryption:** Google-managed

---

## 4 · Secret Manager — three secrets

**Security → Secret Manager → Create secret**, three times. **Replication: Automatic** for each.
Names must match exactly; the workflow mounts them by name.

| Name | Value |
|---|---|
| `DATABASE_URL` | The pooled `postgresql+asyncpg://…` string from §1 |
| `JWT_SECRET` | 48 random url-safe bytes — generate it, never invent it (below) |
| `SEED_PASSWORD` | Only if you later seed demo data on staging; skip for now |

Generate `JWT_SECRET` locally and paste the output:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

**Do not create `SENTRY_DSN`.** Remediation R3 (Sentry and redaction) is still deferred, and the
redaction path that keeps customer phone numbers out of an external sink has never run against a
real sink. An unset DSN is the correct interim state.

---

## 5 · The deploy service account

**IAM & Admin → Service Accounts → Create service account:**

- **Name:** `github-deploy`
- **Grant these roles**, and only these:

| Role | Why |
|---|---|
| **Cloud Run Admin** (`roles/run.admin`) | Deploy the service and the migrate job |
| **Artifact Registry Writer** (`roles/artifactregistry.writer`) | Push the image |
| **Secret Manager Secret Accessor** (`roles/secretmanager.secretAccessor`) | Read the three secrets |
| **Service Account User** (`roles/iam.serviceAccountUser`) | Required to deploy *as* the runtime identity |

**Do not create a JSON key.** That is the whole point of §6. If a page offers you "Create key",
close it.

Note the full address — `github-deploy@<PROJECT_ID>.iam.gserviceaccount.com`.

---

## 6 · Workload Identity Federation — keyless auth

This is the fiddliest part and the most valuable: no long-lived credential ever enters the
repository. A JSON key leaks with the repo and works until someone notices; a WIF token is scoped to
this workflow on this branch and lives minutes.

**IAM & Admin → Workload Identity Federation → Create pool:**

1. **Pool name:** `github`
2. **Add a provider:**
   - **Provider type:** **OpenID Connect (OIDC)**
   - **Provider name:** `github-provider`
   - **Issuer URL:** `https://token.actions.githubusercontent.com`
   - **Audience:** Default
3. **Attribute mapping** — map exactly these:
   - `google.subject` → `assertion.sub`
   - `attribute.repository` → `assertion.repository`
   - `attribute.ref` → `assertion.ref`
4. **Attribute condition** — the security boundary. Without it, *any* GitHub repository in the world
   can mint a token for your project:

   ```
   assertion.repository == 'apoorva2121/annapurna-sys'
   ```

5. **Grant access.** Back on the pool page → **Grant access** → select `github-deploy` →
   for "principal", choose **only the repository above** rather than "all identities".

Then copy the provider's **full resource name**, which looks like:

```
projects/<PROJECT_NUMBER>/locations/global/workloadIdentityPools/github/providers/github-provider
```

It uses the project **number**, not the ID. The pool page shows it; copy it verbatim.

> Google takes **1–3 minutes** to propagate the binding. A first deploy that fails with a
> permission error is often just this — wait and re-run before changing anything.

---

## 7 · Tell GitHub about it

**github.com/apoorva2121/annapurna-sys → Settings → Secrets and variables → Actions → Variables**
(the *Variables* tab, not Secrets — none of these are sensitive):

| Variable | Value |
|---|---|
| `GCP_PROJECT_ID` | Your project ID from §2 |
| `GCP_WIF_PROVIDER` | The full provider resource name from §6 |
| `GCP_DEPLOY_SA` | `github-deploy@<PROJECT_ID>.iam.gserviceaccount.com` |
| `GCP_MIN_INSTANCES` | **`0`** — see §9 before changing this |

---

## 8 · The first deploy

`main` is still at M00, so nothing has been deployed yet. Two options:

**Option 1 — deploy the branch without merging** (recommended for the first attempt). Actions →
**Deploy staging** → **Run workflow** → choose `feat/m10-customers`. `workflow_dispatch` exists for
exactly this.

**Option 2 — merge to `main` first**, which then deploys on every push from here on.

Watch the run. The steps, in order, and what each proves:

1. **Check the one-time setup** — the four variables exist
2. **Build the frontend** → `backend/static`, asserting both `index.html` and `guest.html` are there
3. **Auth via WIF** — no key involved
4. **Build and push** the image with `GIT_SHA` and `BUILT_AT` stamped in
5. **Migrate** — a Cloud Run *Job*, run to completion **before** the service deploys, so new code
   never queries a column that does not exist yet
6. **Deploy** the service
7. **Smoke test** with `--expect-sha`, which is what makes it a check: without it, a previous
   revision still serving traffic would pass every assertion

### Then create the owner account

The deployment has a database and no way in. Run this once — Cloud Run → Jobs, or:

```bash
gcloud run jobs deploy bootstrap \
  --image asia-south1-docker.pkg.dev/<PROJECT_ID>/restaurant-os/restaurant-os-api:<SHA> \
  --region asia-south1 \
  --command python \
  --args=-m,app.bootstrap,--org,"Your Company",--slug,your-company,--restaurant,"Your Branch",--code,BR_ONE,--owner-name,"Your Name",--owner-email,you@example.com \
  --set-secrets DATABASE_URL=DATABASE_URL:latest --max-retries 0

gcloud run jobs execute bootstrap --region asia-south1 --wait
```

**The generated password is printed once, to the job's logs, and is not recoverable** — it is
deliberately absent from the audit row. Open the execution's logs, copy it into a password manager,
and change it after signing in.

---

## 9 · `min-instances` — the one cost decision

Leave `GCP_MIN_INSTANCES` at **`0`** for staging.

- **`0`** — the service scales to zero. Inside Cloud Run's free tier (2M requests, 180K vCPU-s,
  360K GiB-s per month), so **effectively ₹0**. The cost is a cold start of a few seconds on the
  first request after idle, which nobody cares about during a manual pass.
- **`1`** — an instance always runs. Roughly **$10–12/month**. It exists for one real reason, and
  it is not staging: the kitchen display holds an SSE stream open for a whole service, and
  scale-to-zero kills the instance holding every open stream. Clients reconnect and replay from a
  revision cursor so no ticket is lost, but a display that blanks between rounds gets turned off.

So: `0` now; `1` the day a real restaurant runs the kitchen display on it.

---

## 10 · What to test that a laptop cannot tell you

This is why deploying early was worth it. Four things are true only in the cloud, and all four are
written down in this repository as assumptions nobody has checked:

1. **SSE through a real proxy.** Open the kitchen display, leave it for an hour. Cloud Run caps a
   request at 60 minutes; the client should reconnect with `Last-Event-ID` and carry on.
   `X-Accel-Buffering: no` and `Cache-Control: no-cache` are asserted by tests, but no test has
   watched a real proxy honour them.
2. **The rate limiter counts per process.** `docs/backlog.md` says so. With `max-instances=3` an
   attacker gets three times the budget. Hit a guest endpoint hard and watch whether 429 arrives
   when it should.
3. **Concurrency 40 counts a held stream as a live request.** Six kitchen screens is six of the
   forty before a single order is taken.
4. **Timezones.** The container runs UTC and the restaurant does not. Place an order after midnight
   IST and check it books to the correct business day (invariant 4, `business_day_start` 05:00).

Record what you find in `docs/plan/` or as backlog rows — these are the findings the deploy exists
to produce.

---

## 11 · Turning it off

Nothing here bills when idle, so you can leave it. If you want it gone:

```bash
gcloud run services delete restaurant-os-api --region asia-south1
gcloud run jobs delete migrate --region asia-south1
```

Neon: **Settings → Delete project**, or leave it suspended — a suspended project consumes no
compute hours.

The GCP project, Artifact Registry and WIF pool cost nothing while empty, so leave them: redeploying
later is then just §8 again.

---

## 12 · When it is finished

R7's "done when", from `docs/audit/remediation-plan.md`:

- [ ] `GET /api/v1/version` on the staging URL shows the deployed commit
- [ ] The M01 manual script's precondition names the staging URL
- [ ] `docs/checklist.md` blocker rows for cloud accounts are ticked
- [ ] ADR 0005 gains "Deployed 2026-xx-xx: Cloud Run + Neon"
- [ ] `make smoke-prod BASE=<url>` is clean

Then R4 and R7 can both be ticked in the remediation plan, and the staging-dependent Definition of
Done lines — the manual pass on staging, and M13's latency budgets with seeded data — become
reachable for every module.
