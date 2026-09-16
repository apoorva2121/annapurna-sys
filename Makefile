# Restaurant OS — developer entry points.
# `make check` is the blocking gate (docs/sdlc.md step 6); `make lint` is the fast subset.

VENV := backend/.venv
ifeq ($(OS),Windows_NT)
	VENV_BIN := $(VENV)/Scripts
else
	VENV_BIN := $(VENV)/bin
endif
PY  := $(CURDIR)/$(VENV_BIN)/python
NPM := npm --prefix frontend

.DEFAULT_GOAL := help
.PHONY: help setup dev down logs test test-api test-web lint lint-api lint-web fmt check \
	    migrate revision seed audit-docs audit-guardrails audit-deps lock clean \
	    visual visual-update

help:
	@echo "setup    install backend venv + frontend deps"
	@echo "dev      docker compose up: api, db, frontend"
	@echo "test     pytest + vitest"
	@echo "lint     ruff + mypy + eslint + tsc, zero warnings"
	@echo "check    the blocking gate: lint + test + audits"
	@echo "smoke    check a running stack end to end (needs make dev)"
	@echo "migrate  alembic upgrade head"
	@echo "seed     demo restaurant with menu, recipes, stock, orders"

# uv installs from backend/uv.lock, so every machine and every CI run gets the same versions.
# `uv sync` creates backend/.venv itself; the pip bootstrap exists only to obtain uv.
setup:
	python -m pip install --quiet --upgrade uv
	uv sync --project backend
	$(NPM) ci

# Re-resolve dependencies after editing backend/pyproject.toml. The lockfile is committed, so this
# is a deliberate act with a diff to review, not something a build does silently.
lock:
	uv lock --project backend

dev:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f api

# ---------------------------------------------------------------- tests
test: test-api test-web

test-api:
	cd backend && "$(PY)" -m pytest -q

test-web:
	$(NPM) run test -- --run

# ---------------------------------------------------------------- lint
lint: lint-api lint-web

lint-api:
	cd backend && "$(PY)" -m ruff check .
	cd backend && "$(PY)" -m ruff format --check .
	cd backend && "$(PY)" -m mypy app tests

lint-web:
	$(NPM) run lint
	$(NPM) run typecheck

fmt:
	cd backend && "$(PY)" -m ruff format .
	cd backend && "$(PY)" -m ruff check --fix .
	$(NPM) run format

# ---------------------------------------------------------------- gate
# Everything CI runs. Zero warnings tolerated (docs/engineering-standards.md §7).
check: lint test audit-docs audit-guardrails audit-deps
	@echo ""
	@echo "make check: clean"

# Against a running stack, not test doubles. Unit tests cannot see the composed system.
smoke:
	python scripts/smoke.py

audit-docs:
	python scripts/audit_docs.py
	python seed/validate.py
	python library/validate.py
	python library/validate_rates.py
	python seed/validate_tandoor_house.py

# R9 / G-20: the guardrails stop being a document and become a gate. Fails when a rule in
# docs/engineering-guardrails.md has quietly stopped being true, or when the table's own status
# column disagrees with docs/audit/remediation-plan.md.
audit-guardrails:
	python scripts/audit_guardrails.py

audit-deps:
	cd backend && "$(PY)" -m pip_audit --skip-editable
	$(NPM) audit --audit-level=high

# ---------------------------------------------------------------- database
# These run inside the container: the compose network is where `db` resolves, and .env lives at
# the repo root rather than in backend/. Requires the stack to be up (`make dev`).
migrate:
	docker compose run --rm migrate

revision:
	docker compose run --rm api python -m alembic revision --autogenerate -m "$(m)"

seed:
	docker compose run --rm api python -m app.seed

# ADR 0010: expired idempotency keys. Run nightly by the host until the project has a scheduler.
sweep-keys:
	docker compose run --rm api python -m app.jobs.sweep_idempotency_keys

# The image CI's visual job runs in, pinned to the version in package.json (backlog-issues
# B11b, decision D4). Screenshots are Linux pixels: a Windows or macOS run differs in font
# hinting alone, so baselines are only ever taken in here. A named volume shadows node_modules,
# because the host's are built for the host and a bind mount would drop Linux binaries into a
# developer's tree.
PLAYWRIGHT_IMAGE := mcr.microsoft.com/playwright:v1.63.0-noble
# MSYS_NO_PATHCONV: on Windows, Git Bash rewrites a leading "/" in an argument into its own
# installation path, so `-w /work` reached the daemon as "C:/Program Files/Git/work" and the
# run died with an unhelpful "invalid working directory". The variable is meaningless on
# Linux and macOS, where it is simply an unread environment variable.
VISUAL_RUN := MSYS_NO_PATHCONV=1 docker run --rm -v "$(CURDIR)/frontend:/work" -w /work \
	    -v restaurant-os-visual-modules:/work/node_modules $(PLAYWRIGHT_IMAGE) sh -c

# Deliberately not part of `check`: it needs a browser, and `check` must stay runnable on a
# machine with nothing installed but Node.
visual:
	$(VISUAL_RUN) "npm ci && npm run test:visual"

# Re-take the baselines, then commit the pictures with the change that moved them.
visual-update:
	$(VISUAL_RUN) "npm ci && npm run test:visual:update"

clean:
	rm -rf $(VENV) frontend/node_modules frontend/dist backend/.pytest_cache backend/.mypy_cache backend/.ruff_cache
