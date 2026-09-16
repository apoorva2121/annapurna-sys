# Restaurant OS Brand

**Status:** adopted 2026-09-14 by the owner ("warm modern Indian casual dining", guest app and staff
screens under one brand). **Extends, never replaces,** `docs/ui/design-system.md` (what is built) and
`docs/ui/frontend-architecture-and-ux-strategy.md` (direction). The rules any page must follow are in
the `restaurant-ui` skill, which points here.

**Sources, and what was not used.** The structure follows the owner's reference screenshots and the
54 published design systems in `design-md/` (review in the strategy document §1.6) — patterns only,
never their colours, fonts or names. Competitor evidence is from `docs/product/competitor-research/`.
The Indian rules are from `docs/compliance-rules.md`, which cites the instruments; nothing here
restates a rule from memory. Live competitor-app research (menu browsing, customisation, fee display in
Zomato, Swiggy and others) could not be run in the session this was written — the search budget was
exhausted — and is filed in `docs/backlog.md` to revisit the guest-app section when it can be.

---

## 1 · Who it is, in one paragraph

**A good neighbourhood restaurant on a busy evening.** Warm without being twee, quick without being
cold, and exact about money. Staff screens feel like the pass — calm, legible, one thing needing
attention at a time (strategy §0). The guest app feels like the host who seats you: the menu is easy
to read, a dish's type is never in doubt, and the bill has no surprises.

**Key characteristics**
- Warm neutrals — every grey leans a few degrees towards brown — and a warm near-black ink.
- One interaction colour, **jamun**. No second accent.
- Softer corners than a dashboard, never a pill-shaped everything.
- IBM Plex Sans throughout, with its Devanagari companion; tabular figures on every amount.
- Food photos are welcome and never required; the page is complete without them.
- The locked layer never moves: the six alert colours and the veg / non-veg / egg marks.

## 2 · The warmth decision

The owner chose *warm*. The strategy document §0 rejects "a warm-cream-and-terracotta palette (the
current default look of generated software)". Both hold, because warmth does not need either:

- **No cream, no terracotta.** The page stays close to white; cream reads as a template and lowers
  contrast for small text at a dim table.
- **Warmth comes from undertone and shape.** Neutrals carry a low-saturation warm hue (≈ 30°, under
  20% saturation), ink is a warm near-black rather than blue-black, and corners are a step rounder.
- **The accent stays jamun** (deep plum, hue 322). It is an Indian fruit, it is warm, and it is the
  only warm hue not already owned by an alert: saffron sits next to `warning` amber, turmeric next to
  `caution` yellow, chilli is `critical` red. An accent that collides with a status colour makes the
  status colour mean less (design-system §2.1). Its hue is 38° from `critical`, beyond the 25° rule
  the strategy document sets (§3.5).

## 3 · Tokens

Values are bare HSL triples, as `tokens.css` writes them. **Only the baseline (Steel → Warm)
changes;** the dark, Deepavali and Monsoon themes keep their own values, and the contrast guard in
`theme.test.ts` must pass for every one.

| Token | Steel (before) | Warm (after) | Why |
|---|---|---|---|
| `--background` | `210 20% 98%` | `30 20% 98%` | near-white with a warm undertone, not cream |
| `--foreground` | `222 47% 11%` | `24 12% 10%` | warm near-black ink |
| `--card` / `--popover` | `0 0% 100%` | `0 0% 100%` | white stays white, so cards separate by tone |
| `--muted` | `210 24% 96%` | `30 18% 95%` | row hover, sticky bars |
| `--muted-foreground` | `215 16% 38%` | `24 8% 36%` | secondary text, ≥ 4.5:1 on background and muted |
| `--primary` | `222 47% 11%` | `24 12% 10%` | primary stays ink |
| `--primary-foreground` | `210 20% 98%` | `30 20% 98%` | |
| `--secondary` | `210 24% 96%` | `30 18% 95%` | |
| `--border` | `214 32% 91%` | `30 14% 89%` | hairlines, warm |
| `--input` | `214 26% 84%` | `30 12% 80%` | an input must look enterable |
| `--brand` / `--ring` / `--accent` | jamun | jamun, unchanged | the interaction colour |
| `--radius` | `0.5rem` | `0.625rem` | one step softer; cards `lg`, inputs and buttons `md` |

**Locked, and not in this table on purpose:** `critical`, `warning`, `caution`, `info`, `success`,
`neutral` and their `-soft` tints; `--food-veg`, `--food-nonveg`, `--food-egg`; `--scrim`; the z-index
ladder; per-surface targets and density.

## 4 · Type

IBM Plex Sans for everything read; IBM Plex Mono for codes and amounts in tables. Weights stop at 600.
Roles, sizes and the Plex letter-spacing are the table in the strategy document §1.6. Two additions for
the guest app, when it exists:

- **Dish name** — 16 / 24, weight 500. A long Indian dish name wraps to two lines before it truncates;
  it is never cut mid-word.
- **Price on a menu** — 16 / 24, weight 600, tabular, right-aligned in its row. Never smaller than the
  dish name: the price is the second thing a guest reads.

Hindi and Marathi arrive as a data change (design-system §2.2): nothing in a component may assume Latin
glyph widths — no fixed-width text boxes for names.

## 5 · Shape, depth, motion

- **Radius:** `--radius` 10px; inputs and buttons `md` (8px); cards and sheets `lg` (10px); badges and
  the stepper `full`. Nothing else is pill-shaped.
- **Depth:** tonal, as built (design-system §2.4). The guest app's dish card may take the one soft
  shadow the system allows on a raised surface a guest taps; staff surfaces never do.
- **Motion:** the existing durations and single easing. One orchestrated moment per surface — for
  staff, the order leaving for the kitchen (strategy §1.3); for guests, the dish landing in the order.
  `prefers-reduced-motion` disables both.

## 6 · Staff screens

Everything in `docs/ui/conventions.md` and the `restaurant-ui` skill, plus:

- **Money never wraps.** A signed amount keeps its sign with it (`white-space: nowrap` on the cell),
  and a loss is written with the real minus sign (`formatDelta`), never a hyphen on its own line — the
  Dish costs screen did this (owner defect sheet, B12).
- **Row actions sit on one line**, secondary buttons of equal height, in the order a person uses them.
- **A status badge keeps its words together** — `whitespace-nowrap` — so "Unconfirmed recipe" never
  breaks into two lines beside a dish name.
- **A number that cannot be true is flagged, not just shown.** A food cost over 100% or a price far
  outside its market rate gets a `warning` badge with a word, because a screen that quietly prints
  ₹5,207 for a ₹250 dish teaches nobody anything (B12).
- **Every page names where the person came from** with a Back link, so no screen needs a Save or a
  closed tab to leave it (B12).

The competitor evidence for spending effort here: reviewers name order-taking screens that are "not
User friendly" and rate a competitor below another specifically on UI simplicity
(`docs/product/competitor-research/01-platforms.md`, Petpooja section).

## 7 · The guest app (M10), ahead of time

Written now so M10 starts from it. Every rule that touches money or food type is a compliance rule
first and a design rule second.

- **The food-type mark beside every dish name**, in the locked colours and three shapes
  (`docs/compliance-rules.md` §A1). A photo may repeat it; a photo never replaces it.
- **Allergens in words or clear symbols on the menu** once modelled (§A2, B8); a symbol always has a
  text equivalent.
- **Calories only where the restaurant's tier requires them** (§B1) — modelled as a condition, never
  shown as a promise nobody checked.
- **No pre-selected tip and no service charge by default** (§A7, §C). A charge is a line the guest
  can read before paying, never folded into a total.
- **The bill shows every line before payment**: dishes, discounts, charges, tax split, round-off,
  total — the same server-computed figures the staff bill shows.
- **Choosing options is a bottom sheet** with required questions first and Add disabled until they are
  answered, exactly as the waiter surface already does (design-system §4, waiter patterns).
- **No photo is the normal case** (strategy §1.6): the row is complete without one, and a stock photo
  of another kitchen's food is never used.

## 8 · Every new page — the checklist

A page is not finished until every line is true. The `restaurant-ui` skill requires this list.

1. Surface named first (waiter, kitchen, manager, owner, guest); sizes from `data-surface`.
2. Tokens only — no hex, no raw z-index, no inline style; warm neutrals come from the tokens, never
   typed.
3. One primary action, named for its outcome.
4. Status as a soft badge with a word; colour never alone.
5. Money through `formatINR` / `formatDelta`, tabular, right-aligned, never wrapped, never added up.
6. Pending, error, empty and success states all rendered; errors in plain language with no code.
7. A Back link to where the person came from; nothing forces Save to leave. On a screen reached
   by an id, mark it `data-back` — the label is named for its destination ("Tables", "Bills",
   an order's own number), so the marker is what `brandChecklist.test.ts` can hold.
8. Food-type mark wherever a dish is named to a guest or a cook.
9. Phone width checked: headings may step down, controls and amounts never shrink.
10. A test for the page's one important rule, and — once B11's gallery exists — a gallery entry with
    its screenshot.

## 9 · Rollout

1. **Tokens** (this change): the Warm baseline in `tokens.css`, `themes.ts`'s `light` entry renamed
   and described, contrast guard green.
2. **Per screen, when a backlog chunk touches it** (B6–B12), against §6 and §8.
3. ~~**The rest after B11**, when the `/design` gallery and its screenshot tests can show a
   regression.~~ **Done 2026-09-16.** The mechanical lines of §8 are now a test —
   `frontend/src/staff/brandChecklist.test.ts` — rather than a sweep somebody repeats: tokens
   over hex and inline style, no error code on a screen, and a way back out of every screen
   reached by an id. The audit found the screens already clean on tokens and money; what it
   found missing was the way back (three screens) and the food-type mark on the invoice.
   Lines 1, 3 and 9 stay human judgements and are still checked by eye at review.
4. **Every new page from M08 on** is built to §8 from its first commit.
