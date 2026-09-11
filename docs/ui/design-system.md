# Restaurant OS Design System

**Status:** foundation laid, 2026-09-11 · **Owner:** the repository · **Surfaces:** see
`docs/ui/conventions.md`

**This file describes what exists.** It is deliberately short, and it grows one section per module
as components land. The full structure this is growing into — nine sections, a page per component,
a state matrix, governance — is designed in
`docs/ui/frontend-architecture-and-ux-strategy.md` §2.3–2.4. Writing those nine sections today, for
six components, would be documentation describing software that does not exist, which is finding D5
of the 2026-09-11 audit repeated on purpose.

Strategy and direction live in that document. Rules for anyone (or anything) changing the UI live
in `.claude/skills/restaurant-ui/SKILL.md`. This is the reference for what is actually here.

---

## 1. Principles

**The metaphor is the pass** — the steel shelf between kitchen and floor. Matte steel, black ink,
one warm lamp. Nobody decorates a pass; it is the most designed object in a restaurant.

- **Hue budget.** The six alert colours are the only saturated colours on a screen, and each only
  where its meaning applies. A manager's dashboard with three reds is broken, not busy.
- **Primary is ink, not brand.** Hue is reserved for status, so the one primary button on a page
  never competes with a red that means someone must act now.
- **Tonal layering, not shadows.** background → card → muted. Shadows belong to things that
  genuinely float; a table row does not.
- **Colour never alone.** Always with a word or a shape.
- **Words are design.** The button names the outcome — *Send to kitchen*, *Settle ₹695* — never
  *Submit*.

## 2. Foundations

### 2.1 Colour

All values live in `frontend/src/shared/theme/tokens.css`. Nothing else declares a colour.

**Vocabulary is shadcn/ui's** (`--background`, `--primary`, `--ring`, …) rather than a prettier set
of our own. The strategy document proposed `--canvas` / `--ink` / `--line`; that reads better and
costs more than it is worth, because shadcn components are copied into this repository and read
these exact names — a rename means editing every component on arrival and again on every upgrade.
Two vocabularies for one set of values is also the "two catalogues" problem of finding M12.

| Group | Tokens | Notes |
|---|---|---|
| Surfaces | `--background` `--card` `--popover` `--muted` (+ `-foreground`) | `--background` is steel-cool off-white; pure white is reserved for `--card`, so cards separate by tone |
| Actions | `--primary` `--secondary` (+ `-foreground`) | primary is ink |
| Jamun | `--brand` `--accent` `--ring` (+ `-foreground`) | see below |
| Lines | `--border` `--input` | `--input` is stronger — an input must look enterable |
| Alerts **(locked)** | `--critical` `--warning` `--caution` `--info` `--success` `--neutral`, each with `-soft` | fixed meanings on every surface |

**Jamun — the interaction colour.** A deep plum, and the one warm hue not already owned by an
alert colour: red, amber, yellow, blue and green are all spoken for, and an accent that collides
with a status colour makes the status colour mean less.

It is declared at **two lightnesses on purpose**:

| Token | Light | Used for |
|---|---|---|
| `--brand` | `322 40% 32%` | fills: active nav, links, selected state. Dark enough to carry white text |
| `--ring` | `322 48% 45%` | the focus ring — *lighter*, because a ring at the fill's lightness is nearly invisible on a phone in a dim dining room, and focus that cannot be seen is not focus |
| `--accent` | `322 45% 95%` | the soft tint: hover and selection on interactive lists |

### 2.2 Typography

**IBM Plex Sans** for everything read, **IBM Plex Mono** for codes and amounts in tables. Self-hosted
via `@fontsource`, not a CDN: restaurant WiFi is unreliable, a third-party font host is a privacy
and CSP question (`docs/security.md` A05), and a blocked font request means a blank first paint.

Plex carries **Devanagari as a designed companion**, which is the actual reason for it — Hindi and
Marathi become a data change later rather than a redesign.

`font-variant-numeric: tabular-nums` is set on `body`. Every number compared down a column is the
same width, or a table of rupee amounts reads as ragged however it is aligned.

### 2.3 Surfaces and touch targets

`data-surface` on `<body>`, orthogonal to the theme and not themeable.

| Surface | `--target-min` | `--density` | Reading distance |
|---|---|---|---|
| manager / owner (default) | 44 px | 1 | ~60 cm |
| waiter | 48 px | 1.25 | ~40 cm, one hand, moving |
| kds | 64 px | 1.5 | 2 m, gloves, steam |

Components use `min-h-target`, never a fixed height. That is what makes one Button correct on a
laptop, a phone and a wall tablet.

### 2.4 Shape, elevation, motion

`--radius` 0.5rem, with `md`/`sm` derived. Elevation is tonal. Motion: `--duration-fast` 120 ms,
`--duration-base` 180 ms, `--duration-slow` 240 ms, one easing. `prefers-reduced-motion: reduce`
disables all of it, globally, in `index.css`.

### 2.5 Layering

A named z-index ladder — `sticky 10 · dropdown 20 · sheet 30 · dialog 40 · toast 50 · offline 60`.
A raw `z-50` in a component is a bug waiting for a second raw `z-50`. The offline banner is highest
because it must never be covered: a waiter who cannot see they are offline keeps tapping.

## 3. Theming

A theme is a `[data-theme="…"]` block that re-declares the semantic colours. It cannot add CSS,
cannot target a component, and cannot reach the locked or per-surface layers.

**Shipped: `light` and `dark`.** Dark exists now rather than later on purpose — applying a second
theme end to end is the only thing that proves the token layer works, and a single-theme system
that claims to be themeable is a claim, not an architecture. It is also what people want first: a
manager reconciling cash at 1am.

`src/shared/theme/theme.ts` resolves (device choice → OS preference) and applies. Components never
re-render for a theme change; the browser repaints custom properties.

**Guarded by `theme.test.ts`:** every colour the light theme declares must be re-declared by every
other theme. A theme that omits one inherits the light value, which nothing else catches — it type
checks, lints, builds and passes. Shape, type and motion tokens are deliberately *shared*, so the
test checks colours only.

**Not built yet:** festive themes, scheduling by business date, contrast and hue-distance
validation, the settings picker. Each is a config file on top of this layer rather than a refactor;
the design is in the strategy document §3.

## 4. Components

`src/shared/ui/` holds vendored shadcn/ui components, adapted to our tokens.
`src/staff/components/` holds compositions specific to the staff app.

| Component | Where | Notes |
|---|---|---|
| `Button` | `shared/ui/button.tsx` | variants `primary` `secondary` `brand` `ghost` `destructive` `link`; sizes `md` `lg` `icon`. **No `sm`** — there is no surface on which a button below the touch target is correct. `asChild` renders a Link with a button's appearance |
| `Field` | `staff/components/Field.tsx` | label + input + error wired with `aria-describedby` |
| `Notice` | `staff/components/Notice.tsx` | tone `critical` `success` `info`; `role="alert"` for critical |
| `QueryState` | `staff/components/QueryState.tsx` | pending skeleton and error, so a screen describes only success |
| `AppShell` | `staff/components/AppShell.tsx` | header, permission-aware nav, sign out |

**Adding one:** `npx shadcn@latest add <name>`, then adapt it — our tokens, `min-h-target`, no
shadow. Do not reimplement what Radix already solves.

## 5. What this document does not cover yet

Per-component pages with the full state matrix, patterns (data table, form, sheet, KDS ticket),
content and voice rules, accessibility per pattern, performance budgets, and governance. Each
arrives with the module that first needs it — M02 adds the form and settings patterns, M03 the data
table, M07 the waiter patterns, M08 the KDS ticket. The structure they will follow is in
`docs/ui/frontend-architecture-and-ux-strategy.md` §2.3.
