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

**Guest** — the only surface on a device we do not own, a network we do not control, for a person
who has never seen this product and will use it once. Nothing here is learnable: it works the first
time or it does not work. Three screens, and a fourth is a proposal that needs an argument.

- **No sign-in, ever.** A QR code is the whole authentication. Anonymous is the default path and is
  complete — a guest can read the menu, read their bill and rate their meal without typing anything
  about themselves.
- **Three taps to done.** The feedback screen is food, service, would-you-return
  (`docs/customer-experience.md`: "every extra question halves completion"). A phone number is
  optional, below the ratings, never above them, and never pre-ticked (`docs/compliance-rules.md`
  §B2).
- **One filter on the menu, and it is veg-only** (`docs/ui/brand.md` §7.1). A vegetarian scrolling a
  long menu is not reading labels, they are looking for what they can eat. A second filter is where
  a three-tap surface turns into an app.
- **The food-type mark is not the filter.** It is beside every dish name, in the locked colours and
  shapes, because §A1 requires it — a photo may repeat it and never replaces it.
- **Single-select is a radio group, multi-select is checkboxes**, and which it is comes from
  `modifier_group.max_select` rather than from whoever wrote the screen. A checkbox that silently
  deselects its neighbour reads as a bug in the restaurant.
- **Every figure is the server's**, rendered. The guest's total and the printed total disagreeing by
  a paisa is an argument at a table.
- **No cost, no margin, no recipe, no employee name, no other guest's anything** — and this is not a
  discipline, it is `app/schemas/guest.py` plus suite 5 (ADR 0009).
- **Budget the bundle and check the budget.** Every kilobyte is a guest who did not wait. The guest
  entry ships none of the staff code, enforced by an eslint import boundary rather than by care.
- **Say nothing that needs a waiter to explain it.** If a screen needs staff to talk somebody
  through it, the screen is the problem — the waiter is carrying plates.

## Tokens and system

Tailwind + shadcn/ui, adopted properly on 2026-09-11 — `docs/ui/design-system.md` is the reference
for what exists, and `frontend/src/shared/theme/tokens.css` is the only place a value is written
down. The component library **is** the design system — do not hand-roll a component that shadcn
provides. Colour semantics, fixed across all four surfaces (from vision doc §28):

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
