# 0005 — Portable container deploy; GCP Cloud Run first

**Status:** Accepted · 2026-09-08

## Context
Cost optimisation is an explicit goal, and the eventual cloud (Azure / GCP / other) is undecided.
Committing early to managed proprietary services would make that choice irreversible.

## Decision
Depend only on: **a Docker container**, **PostgreSQL**, and **S3-compatible object storage**.
No cloud-proprietary queues, functions, auth or databases in month 1. Cloud becomes a deploy-time
choice, not an architectural one.

First target: **GCP Cloud Run** (scales to zero) + **Neon** or Cloud SQL Postgres + **Cloudflare R2**
for media + **Cloudflare Pages** for the static SPA. Expected pilot cost ~$0–20/month.

Azure equivalent, if credits or a customer require it: Container Apps + PostgreSQL Flexible Server
B1ms + Blob Storage, ~$25–45/month. Same image, same code.

## Consequences
Background jobs (nightly rollups, expiry alerts) run as a scheduled container invocation, not a
cloud-specific scheduler binding. Media URLs are pre-signed through a storage abstraction, never
constructed from a provider-specific host. Staging deploys in week 1 so deployment is never a
week-4 surprise.
