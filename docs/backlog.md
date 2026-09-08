# Backlog

Ideas that arrived mid-module. **Nothing here is scope** until it is promoted into
`docs/modules.md` deliberately, between modules — never during one.

This file exists because the vision document has 36 sections and the single most reliable way to
finish nothing is to act on all of them.

| Idea | Source | Notes |
|---|---|---|
| Upgrade vitest 3 → 5 for GHSA-82fw-gwwq-j7x9 | M00, 2026-09-09 | Path traversal in `@vitest/mocker`. **Dev dependency only — never in the production bundle**, and the gate is `npm audit --audit-level=high`, which this moderate does not trip. Deferred because vitest 5 is two majors up and would re-open the vite/vitest peer alignment settled in M00. Revisit when vitest 5 has a Vite 6/7 story, or immediately if it is ever reclassified high. |
