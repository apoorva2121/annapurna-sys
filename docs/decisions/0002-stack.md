# 0002 — Python backend, React SPA frontend

**Status:** Accepted · 2026-09-08

## Context
Owner is stronger in Python. The roadmap's later phases (§27 predictive analytics, §26 AI advisor)
lean on the Python data ecosystem. The frontend needs to serve both a dense desktop analytics
dashboard and touch-first waiter/kitchen screens.

## Decision
- Backend: FastAPI + SQLAlchemy 2.0 async + Alembic + Pydantic v2 on PostgreSQL 16.
- Frontend: React + TypeScript on **Vite** (SPA), Tailwind + shadcn/ui, TanStack Query.
- The SPA is a **PWA**; waiter and kitchen apps are the same codebase at mobile breakpoints.
- Realtime via SSE.

## Alternatives rejected
- **TypeScript end-to-end** — fewer moving parts, but works against the owner's strengths and the
  eventual forecasting work.
- **Next.js** — would add a Node server to run and pay for. A Vite SPA builds to static files that
  host free on any CDN, which matters for the cost target in ADR 0005.
- **React Native in month 1** — app-store review cycles and a second codebase, to reach devices that
  a PWA already reaches. Revisit when a native capability (offline KOT, printer, barcode) forces it.
- **WebSockets** — bidirectional, so more infrastructure than the kitchen display needs. The KDS is
  server→client only. Reconsider when in-app chat (§19) needs typing indicators.

## Consequences
Two languages, two lint/test toolchains, one Makefile hiding both. Shared enums must be kept in sync
between `app/core/enums.py` and `frontend/src/shared/enums.ts` — a test asserts they match.
