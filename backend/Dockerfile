# syntax=docker/dockerfile:1
# Backend image. Multi-stage so the runtime carries the interpreter, the venv and the source —
# no compiler, no pip cache, no build metadata. ADR 0005: this image is the whole deploy unit,
# it must run unchanged on Cloud Run, Container Apps or a VM.

# ---------------------------------------------------------------- builder
FROM python:3.13-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

# The venv lives outside /app on purpose: docker-compose.yml bind-mounts the host's backend/ over
# /app for live reload, and a venv inside /app would be shadowed by the host's Windows-built one.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# uv installs from the lockfile. `pip install .` resolved fresh on every build, which meant two
# builds of the same commit could ship different dependency versions — and this project has already
# been bitten by that: FastAPI 0.141 changed router flattening and made all four generic suites
# iterate an empty list, passing while testing nothing (M9, G-10).
RUN pip install uv==0.12.13

WORKDIR /src
# pyproject.toml and uv.lock are the dependency inputs. Copied alone, before the source, so editing
# a module or a doc does not invalidate the dependency layer.
COPY pyproject.toml uv.lock ./
# --frozen refuses to update the lockfile: if it disagrees with pyproject.toml the build fails here
# rather than silently resolving something new. --no-dev keeps pytest and ruff out of the image.
# UV_PROJECT_ENVIRONMENT puts the packages in the venv the runtime stage copies.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
# The project itself, without touching dependencies again.
RUN uv sync --frozen --no-dev

# ---------------------------------------------------------------- runtime
FROM python:3.13-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# Empty on purpose: it clears zoneinfo's system search path, so every ZoneInfo lookup resolves from
# the `tzdata` package pinned in uv.lock rather than from the base image's /usr/share/zoneinfo.
#
# Without it the image reads Debian's copy of the IANA database while a developer on Windows — which
# has no system copy — reads the locked one, so one commit can apply two different versions of a
# timezone rule. `business_date_of` decides which day each order's takings land in; that is not a
# calculation allowed to vary by host.
#
# It also makes a missing dependency loud rather than silent: drop `tzdata` from pyproject.toml and
# ZoneInfo raises here instead of quietly falling back to whatever the OS happens to ship. The same
# choice app/core/business_day.py makes when it refuses an unknown zone rather than assuming UTC.
ENV PYTHONTZPATH=""

# Stamped by the build so GET /api/v1/version can answer without a .git directory in the image.
# See docs/observability.md; pass with `docker build --build-arg GIT_SHA=$(git rev-parse HEAD)`.
ARG GIT_SHA=unknown
ARG BUILT_AT=unknown
ENV GIT_SHA=${GIT_SHA} \
    BUILT_AT=${BUILT_AT}

# Non-root. A container that can write its own code is a container an attacker can rewrite.
RUN useradd --create-home --uid 1000 appuser

COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv

WORKDIR /app
# Whole context minus .dockerignore: app/, alembic/, tests/, pyproject.toml. alembic/ has to be
# here — `alembic upgrade head` runs from this image on deploy, not from a developer's laptop.
COPY --chown=appuser:appuser . .

USER appuser
EXPOSE 8000

# python, not curl: the slim image has no curl and adding one for a healthcheck is 10MB of attack
# surface. Any non-200 raises, which is the failure we want.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).read()"]

# Production command. docker-compose.yml overrides it with --reload for local development.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
