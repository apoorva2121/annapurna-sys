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

WORKDIR /src
# pyproject.toml is the single source of dependency truth (there is no requirements.txt). Only the
# two inputs `pip install .` needs are copied, so editing a doc or a test does not re-resolve deps.
COPY pyproject.toml ./
COPY app ./app
RUN pip install .

# ---------------------------------------------------------------- runtime
FROM python:3.13-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

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
