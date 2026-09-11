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

3. **Every theme declares every colour.** A theme that omits one inherits the light value, which on
   a dark background is somewhere between wrong and unreadable — and nothing else catches it: it
   type-checks, lints, builds and passes.
   *Enforced:* the parity test in `theme.test.ts`.

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

10. **Before finishing:** `npm run lint`, `npm run typecheck`, `npx vitest run`. All three clean,
    zero warnings.

## What is not built yet

Do not cite these as if they exist, and do not add a rule that depends on them:

- the `/design` gallery route and its screenshot tests — planned with M07
- the theme *engine*: festive themes, scheduling by business date, contrast and hue-distance
  validation, the settings picker — planned with M02's settings screen. The token layer they need
  is done, so each is a config file rather than a refactor.
- per-surface type scales — only `--target-min` and `--density` vary by surface today
