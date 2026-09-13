---
name: restaurant-ui
description: Use when creating or changing anything under frontend/src — screens, components, styles, tokens, themes or user-facing strings. Carries the design system's rules and the surface constraints they come from.
---

# Restaurant OS UI

Read `docs/ui/conventions.md` (the four surfaces) and `docs/ui/design-system.md` (what exists
today) before touching the frontend.

This file is instructions, not enforcement. What actually fails a build is eslint, `tsc`, and the
theme parity test — named against each rule below, so you can tell a rule that bites from a rule
that is a wish.

## Before writing any JSX

Answer three questions, in this order. They decide the layout; guessing them and fixing it
afterwards is how a screen ends up with four competing primary actions.

1. **Which surface?** waiter (phone, one hand, moving) · kitchen (2 m, gloves, steam) ·
   manager (tablet, interrupted) · owner (laptop, calm). Sizes and density come from
   `data-surface`, never from a hard-coded height.
2. **What is the one primary action?** One per view.
3. **What needs the person's attention, and how is it shown?** Colour *and* a word *and* position —
   never colour alone.

## The rules

1. **Tokens only.** Every colour, radius, duration and z-index comes from
   `frontend/src/shared/theme/tokens.css` through a Tailwind class. No hex, no `rgb()`, no inline
   `style`, no raw `z-50`. If a token is missing, add it to `tokens.css` in the same change.
   *Enforced:* eslint `no-restricted-syntax` on `className` colour literals and on `style`.

2. **The locked layer is locked.** The six alert colours and their meanings, the per-surface touch
   targets, and the z-index ladder are not themeable and do not change without an ADR. A theme is
   paint: it may repaint surfaces and the brand colour and nothing else.
   *Enforced:* `src/shared/theme/theme.test.ts`.

3. **Add a theme by adding an entry to `src/shared/theme/themes.ts`, and nothing else.** It is a
   set of overrides on the light baseline; whatever it omits it inherits. Never add a
   `[data-theme]` block to CSS — that would put themes in two places.
   *Enforced:* `theme.test.ts` computes contrast over every shipped theme's merged result and
   refuses any pair below 4.5:1.

4. **Do not hand-roll what shadcn/ui provides.** `npx shadcn@latest add <component>` puts the
   source in `src/shared/ui/`, where it is yours to edit. Adapt it to our tokens and the touch
   target; do not reimplement Dialog, Select, Popover or Combobox — Radix has solved focus
   management, ARIA and keyboard behaviour and a solo project will not.
   *This rule exists because it was already broken once:* M01 hand-rolled three components while
   `conventions.md` said the library is the design system.

5. **Colour never carries meaning alone.** Pair it with a word or a shape. Commercial kitchens are
   full of colour-blind men and steamed-up screens.

6. **Every mutation renders pending, error and success explicitly.** No state may be silent
   (`docs/engineering-standards.md` §5). M01 produced two real defects from getting this wrong: a
   staff list that silently truncated at 50, and a role editor that wiped every role while
   reporting success.

7. **Strings live in the persona's strings file.** No English literal in a component. Hindi and
   Marathi then become a data change rather than a sweep through every screen.

8. **Numbers are tabular and right-aligned; money is a string.** Format for display with
   `Intl.NumberFormat('en-IN', …)`; never do arithmetic on a rupee amount on the client
   (CLAUDE.md invariant 3).

9. **One primary action per view. One thing per surface may move on its own**, and only to say
   something arrived. A screen that is always moving teaches people to ignore movement.

10. **A state never moves the layout.** Selected, focused, invalid, late: show it with a ring
    (`ring-2`, which is a box-shadow), colour or an icon — never a thicker border, extra padding or
    a bolder weight that re-flows the text. A row that shifts under a thumb gets the wrong tap.
    Where a spec says "thicker border" (the late KDS ticket), build it as an inset ring.

11. **A status badge is soft fill, strong ink, and a word.** Background `bg-<alert>-soft`, text and
    icon `text-<alert>`, `rounded-full`, `text-xs font-medium`. Its contrast is text-on-soft, not
    text-on-page — check that pair, because the page pair passing proves nothing about it.

12. **Text scales down on a phone; controls do not.** Page and section headings may step down one
    size below `md`. Body text, button labels, amounts and inputs stay at 16 px or larger — below
    16 px, iOS Safari zooms the page when an input takes focus.

13. **A photo is decoration, never information** (when dish photos arrive). The slot has a fixed
    aspect ratio so nothing moves when it loads; a dish with no photo renders the same row without
    the slot — never a grey box and never a stock photo of somebody else's food; no text on a photo
    without the `scrim` token behind it; the veg / non-veg / egg mark sits beside the dish name,
    so a photo can never hide or replace it.

14. **Before finishing:** `npm run lint`, `npm run typecheck`, `npx vitest run`. All three clean,
    zero warnings.

## Do and don't

Real cases from this product, not general advice. Check a finished screen against both lists.

**Do**
- One ink `primary` button per view, named for the outcome: *Send to kitchen*, *Settle ₹695*.
- Status as a soft badge with a word: *Occupied*, *Bill asked for*, *Late*.
- Amounts through `formatINR`, right-aligned, tabular; compare to `"0.00"` to show or hide a row.
- `min-h-target` on everything a finger aims at, including select items and clickable rows.
- A skeleton in the shape of the finished layout; an empty state that says what will appear and
  how to make it appear.
- Name the thing and the amount in a destructive confirmation: *Cancel order #1042 (₹1,240)?*
- Disable a control at its limit instead of hiding it, so nothing shifts.

**Don't**
- Use jamun (`brand`) for emphasis or decoration — it means *interactive or selected*.
- Use red for anything that is not *someone must act now*; never two reds in one region — collapse
  them into a count.
- Put a shadow on a row or a card. Shadows belong to things that float.
- Rely on hover: the waiter and kitchen surfaces have none. Hover styling goes under
  `@media (hover: hover)`.
- Ship an icon-only button, except for an action done fifty times a shift — then 48 px with an
  `aria-label`.
- Write a hex value, a fixed height, a raw `z-50`, or English inside a component.
- Add, subtract or round two rupee amounts on the client.

## Asking for a screen (AI sessions)

Describe a component with **the surface first, then token and component names, then every state**.
"A light grey box" is an adjective; `bg-muted` is a decision. Examples in this product's terms:

- *"Waiter surface. Order line row: `min-h-target`; `quantity × dish` in `text-base font-medium`;
  options beneath in `text-sm text-muted-foreground`; line total right-aligned through `formatINR`;
  status as a soft badge with a word. States: unsent (removable in one tap), sent (asks why before
  removing), cancelled (struck through, stays visible). No shadow. Strings from `strings.ts`."*
- *"Manager surface. Suppliers list: `shared/ui/table`; numbers right-aligned and tabular; the whole
  row is a link with `min-h-target`; `QueryState` for pending and error; an empty state naming how
  to add the first supplier; cursor paging with a visible 'Load more'."*
- *"Waiter surface. Cancel-order confirmation: `Sheet side="bottom"`; the title names the order and
  its amount; a required reason field with its rule under it; the destructive button reads
  'Yes, cancel it' and is disabled only while pending; the server's error appears in place."*

Then iterate **one component at a time**: build it, check it against *Do and don't* and the state
matrix (`docs/ui/frontend-architecture-and-ux-strategy.md` §2.3 B), then move on.

## What is not built yet

Do not cite these as if they exist, and do not add a rule that depends on them:

- the `/design` gallery route and its screenshot tests — planned with M07
- scheduling a festive theme by business date, and a restaurant-wide default — planned with M02's
  settings screen. Themes themselves, the per-device picker and contrast validation exist.
- hue-distance validation (an accent ≥25° from every alert hue) — designed, not implemented; today
  it is a review question rather than a check.
- per-surface type scales — only `--target-min` and `--density` vary by surface today; the proposed
  role table (with Plex letter-spacing and phone scaling) is in the strategy document §1.6
- a `Badge` component and a contrast test for text on each `-soft` fill — rule 11 is followed by
  hand until then
- dish photos and an image slot component — rule 13 is ready for when they arrive (M03 revisit,
  M10 guest app)
