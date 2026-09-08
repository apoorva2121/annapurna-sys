# UI Conventions

We are not designing one app. We are designing **four**, sharing one codebase and one token set.
Each has a different user, posture, distance and lighting. Getting this wrong is the most common
reason restaurant software gets bought and then abandoned.

| Surface | User | Device | Read at | Conditions |
|---|---|---|---|---|
| **Waiter** | Waiter/captain | Phone, one-handed | ~40cm | Moving, dim room, in a hurry |
| **Kitchen (KDS)** | Chef, line cook | Wall tablet/monitor | **2 metres** | Steam, heat, greasy or gloved hands |
| **Manager** | Manager | Tablet/laptop | ~60cm | Office or floor, interrupted constantly |
| **Owner** | Owner | Laptop | ~60cm | Calm, wants density and comparison |

## Rules per surface

**Waiter** — tap targets ≥ 48px. Primary action bottom-right, thumb-reachable. Never more than two
taps from table map to sending a KOT. No hover states; they don't exist on touch. Optimistic UI on
every write — the network in a restaurant basement is bad, and the waiter must not wait.

**Kitchen** — this is the one people get wrong. Base font ≥ 20px, order numbers ≥ 40px. High contrast
only. Colour carries meaning (`new` / `preparing` / `late`) but **never alone** — pair it with text
and position, because commercial kitchens are full of colour-blind men and steamed-up screens.
No scrolling: the screen shows what fits and paginates. No modals — a chef cannot dismiss a dialog
with wet hands. Elapsed time on every ticket, always visible, counting up.

**Manager / Owner** — dense is correct here. Tables over cards. Numbers right-aligned, tabular
figures, consistent decimal places. Every metric shows a comparison (vs yesterday, vs last week) —
a number with no baseline is not information. Every metric is clickable through to the rows behind
it; §36's "what happened?" is worthless if it dead-ends at a total.

## Tokens and system

Tailwind + shadcn/ui. The component library **is** the design system — do not hand-roll a component
that shadcn provides. Colour semantics, fixed across all four surfaces (from vision doc §28):

`critical` red · `warning` amber · `caution` yellow · `info` blue · `success` green · `neutral` slate

These map to alert severity everywhere. Never use red for a decorative accent — in this product red
means *someone must act now*.

## Non-negotiables

- **Money**: `₹` prefix, Indian digit grouping (₹1,23,456), two decimals, tabular numerals.
- **Dates**: business date, not calendar date. Label it "Business day" wherever ambiguity is possible.
- **Empty states** explain what will appear and how to make it appear. Never a bare "No data".
- **Loading**: skeletons matching final layout. No spinners on primary content.
- **Destructive actions** name the thing: "Void order #1042 (₹1,240)?", never "Are you sure?".
- **Offline**: the waiter and kitchen views show a persistent banner and queue writes. Not full
  offline sync (out of scope), but never silent failure.
- **Accessibility**: WCAG AA contrast, keyboard reachable, focus visible. The KDS at 2m makes this
  a functional requirement, not a compliance one.
- Language: English only in month 1; keep all user-facing strings in one place so Hindi and regional
  languages are a later data change, not a refactor.
