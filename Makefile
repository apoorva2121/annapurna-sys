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
	    migrate revision seed audit-docs audit-deps lock clean

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
check: lint test audit-docs audit-deps
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

clean:
	rm -rf $(VENV) frontend/node_modules frontend/dist backend/.pytest_cache backend/.mypy_cache backend/.ruff_cache
