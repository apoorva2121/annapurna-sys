# Runbook · Database Restore

**Status: stub.** Filled in during P5 (`docs/sdlc.md`) once the production database exists, because a
runbook written against a hypothetical environment is worse than none — it reads as reassurance while
being wrong.

Written to be followed at 9pm by someone stressed. Numbered commands, no judgement calls, no
"investigate the issue".

## To be written in P5

1. Decide: point-in-time recovery, or restore from the daily snapshot?
2. Exact console steps / CLI commands for the chosen provider (ADR 0005)
3. Where to restore to (**always a scratch database first, never over production**)
4. How to verify the restore: row counts per major table, latest order, latest stock movement
5. How to cut traffic over, and how to roll back the cutover
6. Who to tell, and in what words

## Targets (from `docs/observability.md` §7)

- **RPO ≤ 5 minutes** · **RTO ≤ 1 hour**
- Restore tested **monthly**, into a scratch database, result verified. Put it in the calendar.

## Rule that applies now, before this is written

Never restore over a live database. Restore beside it, verify, then switch.
