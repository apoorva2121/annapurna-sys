# 0004 — Money, time and units

**Status:** Accepted · 2026-09-08

## Context
Three classic domain traps, each of which silently corrupts exactly the numbers this product sells.

## Decision
**Money** — `NUMERIC(12,2)` in Postgres, `Decimal` in Python, string over JSON. No floats anywhere in
a money path. GST is computed per line and stored per line (CGST/SGST split), never derived at
display time; rates change and historical invoices must not move.

**Time** — `timestamptz`, stored UTC. Every restaurant has an IANA timezone and a
`business_day_start` (default 05:00 local). Orders carry a denormalised `business_date` computed at
insert. Reporting groups on `business_date`, never on `date_trunc('day', created_at)`.

**Units** — every ingredient has one base unit: `g`, `ml`, or `unit`. Purchase and recipe units
convert to base at the write boundary. Per-ingredient density where a recipe says ml and purchasing
says kg. No implicit conversion at read time.

## Consequences
A restaurant closing at 2am sees its late covers on the right day — the single most common complaint
about competing dashboards. Conversions are testable in one place. Money never drifts by paise.
