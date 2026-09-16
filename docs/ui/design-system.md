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

**The brand** — who the product is, the warm baseline, the guest-app rules, and the checklist every
new page passes before it is finished — is `docs/ui/brand.md` (owner decision, 2026-09-14).

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
- **A state never moves the layout.** Selection, focus, errors and lateness are rings, colour and
  icons, never a thicker border or extra padding: a row that shifts under a thumb gets the wrong tap.

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
| Surfaces | `--background` `--card` `--popover` `--muted` (+ `-foreground`) | `--background` is near-white with a warm undertone (brand §3); pure white is reserved for `--card`, so cards separate by tone |
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

`--radius` 0.625rem (brand §5), with `md`/`sm` derived. Elevation is tonal. Motion: `--duration-fast` 120 ms,
`--duration-base` 180 ms, `--duration-slow` 240 ms, one easing. `prefers-reduced-motion: reduce`
disables all of it, globally, in `index.css`.

**Elevation, as built.** Every level is a tone or a ring; nothing on a page casts a shadow.

| Level | Treatment | Used for |
|---|---|---|
| Page | `bg-background` | the canvas |
| Raised | `bg-card` + `border` hairline | cards, table containers |
| Recessed | `bg-muted` | row hover, sticky bars, active tabs |
| Overlay | sheets and dialogs: `bg-background` with a `border` edge over `bg-scrim/70`; select menus: `bg-popover`; each on its `z-` rung | anything that floats — separated by the scrim and an edge, not a shadow |
| Focus | `ring-2 ring-ring` + `ring-offset-2 ring-offset-background` | keyboard focus. The offset paints a gap in the page colour between control and ring, which keeps the ring visible against a filled `brand` or `primary` button |

### 2.5 Layering

A named z-index ladder — `sticky 10 · dropdown 20 · sheet 30 · dialog 40 · toast 50 · offline 60`.
A raw `z-50` in a component is a bug waiting for a second raw `z-50`. The offline banner is highest
because it must never be covered: a waiter who cannot see they are offline keeps tapping.

## 3. Theming

A theme is an **entry in a config file**, applied at runtime by writing a handful of CSS custom
properties onto `<html>`. It cannot add CSS, target a component, or reach the locked and
per-surface layers. Components never re-render for a theme change — the browser repaints custom
properties — and no component ever learns that a theme exists.

`tokens.css` holds the light baseline and the locked layer, and **nothing else defines a theme**:
choosing the default *clears* the overrides rather than applying a second copy of the same values.

### Adding a theme

**Add an entry to `src/shared/theme/themes.ts`. Nothing else.** It appears in the picker on the
profile screen and applies on click.

A theme is a set of *overrides* on the light baseline, not a full palette — say what makes it feel
different and everything else stays as it was. A value you never give cannot be wrong.

```ts
{
  id: 'monsoon',
  name: 'Monsoon',
  description: 'Cool slate and deep teal, tighter and crisper.',
  appearance: 'light',
  colors: { background: '200 24% 97%', brand: '188 62% 26%', /* … */ },
  radius: '0.25rem',
  density: 0.95,
}
```

| Lever | Effect |
|---|---|
| `colors` | surfaces, text, brand, borders. Bare HSL triples — `"36 45% 97%"` |
| `radius` | corner roundness; after the background, the most visible single lever |
| `density` | page rhythm. Multiplies `p-page`/`gap-page`. **Not** touch targets — those are physical |
| `appearance` | drives `color-scheme`, so scrollbars and form controls follow |

**Shipped: `light` (Warm), `dark`, `deepavali`, `monsoon`.** More than one exists deliberately —
applying a second theme end to end is the only thing that proves the layer works, and a system
with one theme that claims to be themeable is a claim, not an architecture.

### Making a dark theme

The `dark` entry is the worked example; a new dark entry follows the same rules. A dark theme is
not the light one inverted.

- **Raised is lighter.** On a dark page a shadow is invisible, so each level steps *lighter*: in
  `dark`, `background` 9 %, `card` and `popover` 13 %, `muted` 18 %.
- **Interaction colours go lighter too.** `brand` and `ring` rise in lightness (in `dark`, 58 % and
  62 % against 32 % and 45 % in light), and `brandForeground` flips to ink so the fill still carries
  its text.
- **Text is near-white, never pure white.** Pure white on near-black glares on a phone in a dim
  room; the contrast guard is still met with room to spare.
- **Borders are quieter, not brighter.** A hairline that reads as structure in light becomes a grid
  of lines in dark.

### What a theme cannot do

`applyTheme` writes only the keys in `THEMEABLE`, so this is structural rather than a convention.
Out of reach: the six alert colours, `--target-min`, the z-index ladder, layout, component
structure and copy. A theme is paint.

### Two guards

- **Contrast.** Every pair that decides whether a screen can be read — text on background, on
  card, on muted, and each foreground on its fill — is computed against WCAG AA (4.5:1). A theme
  below it is **not applied**: it falls back to the default and says why in the console. Without
  this, a config whose values are each reasonable can still render an app nobody can use, and it
  would type-check, lint, build and pass.
- **Inheritance.** Anything a theme omits inherits the baseline, so the contrast check runs over
  the merged result rather than over the config alone.

`theme.test.ts` runs both over every shipped theme, so a bad config fails the build rather than a
shift.

**Not built yet:** scheduling a festive theme by business date and a restaurant-wide default —
both belong with M02's settings screen, and both are an insertion into `resolveTheme` rather than a
redesign. Hue-distance validation (an accent must sit ≥25° from every alert hue) is designed in the
strategy document §3.5 and not implemented; today it is a review question.

## 4. Components

`src/shared/ui/` holds vendored shadcn/ui components, adapted to our tokens.
`src/staff/components/` holds compositions specific to the staff app.

**Seeing them rather than reading about them:** `/design` renders every component below in the
states it ships, in a development build only (backlog-issues B11b, decision D4). Each specimen is
photographed by `npm run test:visual`, so a token change that moves a button by a pixel becomes a
diff a reviewer looks at instead of a surprise on a waiter's phone. The pictures are Linux pixels
and are only ever taken inside the Playwright image `make visual` and CI share — `make
visual-update` re-takes them, and they are committed with whatever change moved them.

| Component | Where | Notes |
|---|---|---|
| `Button` | `shared/ui/button.tsx` | variants `primary` `secondary` `brand` `ghost` `destructive` `link`; sizes `md` `lg` `icon`. **No `sm`** — there is no surface on which a button below the touch target is correct. `asChild` renders a Link with a button's appearance |
| `Select` | `shared/ui/select.tsx` | Radix. Trigger **and items** are `min-h-target` — the items are what is actually aimed at. `z-dropdown` |
| `Dialog` | `shared/ui/dialog.tsx` | Radix. `z-dialog`, `bg-scrim/70`, `p-page`. On phones prefer `Sheet` — a centred dialog on a 5" screen covers the thing being decided about |
| `Sheet` | `shared/ui/sheet.tsx` | The same Radix primitive anchored to an edge, so a screen can switch between the two at a breakpoint without changing its logic. `z-sheet` |
| `Switch` | `shared/ui/switch.tsx` | Enlarged to `h-6 w-11`, still under `--target-min`, so **the label is part of the hit area** — always pair with `Label htmlFor` (asserted in `ui.test.tsx`). Means "takes effect now"; for anything needing a Save, use a checkbox |
| `Table` | `shared/ui/table.tsx` | As generated. **A clickable row needs `min-h-target`** — rows are not tap targets by default, and forcing one would make an owner's dense table unreadable |
| `Label` | `shared/ui/label.tsx` | Radix. Forwards clicks to the control it names, which is what makes the switch's hit area work |
| `Field` | `staff/components/Field.tsx` | label + input + error wired with `aria-describedby` |
| `Notice` | `staff/components/Notice.tsx` | tone `critical` `success` `info`; `role="alert"` for critical |
| `QueryState` | `staff/components/QueryState.tsx` | pending skeleton and error, so a screen describes only success |
| `AppShell` | `staff/components/AppShell.tsx` | header, permission-aware nav, sign out |

**Adding one:** `npx shadcn@latest add <name>`, then adapt it — our tokens, `min-h-target`, no
shadow. Do not reimplement what Radix already solves.

Three things the generator gets wrong here, all of which it got wrong in M02 and will get wrong
again:

- **the import alias** — it writes `@shared/shared/cn`; the correct path is `@shared/cn`;
- **`lucide-react`** — three of the six components import it and the generator does not install it;
- **raw `z-50`, `shadow-*` and `bg-black/80`** — replace with the ladder (`z-dropdown`, `z-sheet`,
  `z-dialog`), nothing, and `bg-scrim/70`.

Each adaptation is written down in the component's own docstring, because `shadcn add` overwrites
the file: an undocumented adaptation returns to the generated default silently on the next upgrade.
Anything asserted in those docstrings that the code could stop doing belongs in
`src/shared/ui/ui.test.tsx`.

### Waiter patterns (M07)

The waiter surface is a phone held in one hand, in a dim room, mid-service. `WaiterSurface`
(`staff/components/WaiterSurface.tsx`) switches `data-surface` to `waiter` while a waiter screen is
mounted, which gives 48 px targets, and restores what was there when the screen is left. The surface
belongs to the screen in the hand, not to the person signed in: a manager seating a table is doing a
waiter's job for those thirty seconds.

| Pattern | Where | Rules |
|---|---|---|
| Table map cell | `TableMapScreen` | The table code is large. **Status is a word** ("Free", "Occupied", "Bill asked for"), never only a border colour. A free table is a `button` that opens an order in one tap; an occupied one is a link to its order. A table that is out of service is disabled, not hidden, so the floor keeps its shape |
| Order line row | `OrderScreen` | `quantity × dish`, options beneath, and the line's status as a word. **A change shows at once** (B11): a tapped dish appears as "Adding…" and a new count as "Saving…", with no price until the server prices it, and a refusal puts back what was there. The line total is right-aligned in tabular numerals. An unsent line comes off in one tap; a sent one asks why first. A cancelled or returned line stays on screen, struck through |
| Money display | every screen | `formatINR` on the server's string, in tabular numerals, right-aligned. A reduction (discount, refund) uses `formatDelta`'s real minus sign. Show or hide a row by comparing to `"0.00"`; **never add two amounts on the client** (CLAUDE.md invariant 3) |
| Quantity stepper | `staff/components/QuantityStepper.tsx` | Two buttons and the number, never a text box. Each button is named for what it changes ("One more Dal Makhani"). A button at its limit is disabled rather than hidden, so the row does not move under a thumb. The count is `aria-live="polite"` |

Two layout rules hold on every waiter screen. **The primary action is bottom-right** in a sticky bar:
Send to kitchen, Settle. **Choices open from the bottom** (`Sheet side="bottom"`) within thumb
reach, and the sheet's Add stays disabled until every required question has an answer.

## 5. What this document does not cover yet

Per-component pages with the full state matrix, patterns (data table, form, sheet, KDS ticket),
content and voice rules, accessibility per pattern, performance budgets, and governance. Each
arrives with the module that first needs it — M02 adds the form and settings patterns, M03 the data
table, M08 the KDS ticket. M07's waiter patterns are in §4. The structure they will follow is in
`docs/ui/frontend-architecture-and-ux-strategy.md` §2.3.

Proposed but not built — a type scale by role with Plex letter-spacing, how each pattern collapses
on a phone, dish photos, badges — is in the strategy document §1.6, from the 2026-09-14 review of 54
published design systems.
