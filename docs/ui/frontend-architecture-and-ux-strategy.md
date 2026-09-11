# Frontend Architecture & UX Strategy

**Restaurant OS · four surfaces, one design system, a theme file that can change everything except
what keeps a kitchen safe.**

Written 2026-09-11 against the frontend as it stands at `feat/m01-identity`: Tailwind 3.4 with
eleven HSL tokens in `frontend/src/shared/index.css`, a hand-rolled `Button`/`Field`/`Notice` in
`frontend/src/staff/components/`, `cva`/`clsx`/`tailwind-merge` installed but `shadcn/ui` never
initialised (`docs/backlog.md`), `Inter` named in `tailwind.config.ts` but never loaded, every
user-facing string in `frontend/src/staff/strings.ts`, and a `guest/` bundle seam held open. The
rules in `docs/ui/conventions.md` — four surfaces, six alert colours, 48 px targets, colour never
alone, skeletons not spinners, empty states that explain — are correct and are kept. This document
is what sits on top of them.

**No application code is rewritten here.** Everything below is architecture, strategy and the
configuration files the strategy needs. Where a snippet appears it is illustrative of a shape, not a
patch.

---

## 0. The direction in one page

**The metaphor is the pass.** The steel shelf between kitchen and floor where tickets clip, plates
land and the expo reads everything at a glance. It is the most designed object in a restaurant and
nobody decorates it: matte steel, black ink, a single warm lamp. The interface borrows that —
cool steel neutrals, black-ink primary actions, one warm accent used rarely, and colour spent only
on things that need a human now.

**Token plan (the whole personality in six values)**

| Role | Value | Why |
|---|---|---|
| Canvas | `hsl(210 20% 98%)` | steel-cool off-white; not cream, not pure white — pure white is reserved for raised surfaces so tonal layering works without shadows |
| Surface | `hsl(0 0% 100%)` | cards, sheets, table rows sit *on* the canvas |
| Ink | `hsl(222 47% 11%)` | already your `--foreground`; primary buttons are ink, not brand colour — hue is reserved for status |
| Ink, muted | `hsl(215 16% 38%)` | already your `--muted-foreground`; passes AA on canvas |
| Line | `hsl(214 32% 91%)` | already your `--border`; hairlines carry structure, shadows do not |
| Accent, "jamun" | `hsl(322 40% 32%)` | the one warm note: selection, active nav, links, focus. A deep plum is the only warm hue that is *not* one of the six alert colours — red, amber, yellow, green, blue are all spoken for |

**Type:** IBM Plex Sans for everything read; IBM Plex Mono for codes, amounts in tables and ticket
numbers; IBM Plex Sans Devanagari as the Hindi/Marathi companion. Self-hosted. Tabular figures on.

**Layout:** left-aligned, 4 px grid, density set per surface by a token rather than per screen.
One memorable moment: the KOT leaving the waiter's hand (§1.3). Everything else is quiet.

**What was rejected, deliberately:** neumorphism (fails contrast, invisible through steam, no touch
affordance), glassmorphism (blur costs frames on ₹9,000 Android tablets and halves legibility),
gradient dashboards, a warm-cream-and-terracotta palette (the current default look of generated
software), identical rounded cards with one grey shadow, all-caps eyebrow labels, red or gold as a
brand accent (both belong to the alert system — see §3.5).

---

## 1. UI elevation and simplification

### 1.1 Premium without clutter: the six mechanisms

Data-heavy screens look cheap for five reasons — too many borders, too many colours, too many
weights, misaligned numbers, and decoration doing structure's job. Premium is what remains when
those are removed and the little that is left is exact.

**1. Tonal layering instead of shadows.** Three levels: canvas → surface → raised. Each is a tonal
step, separated by a hairline. Shadows appear only on overlays (sheets, menus, dialogs) because
those genuinely float. A table row hover is a tonal step, not a shadow.

**2. One hue budget per screen.** The six alert colours are the *only* saturated colours allowed
on a screen, and each is allowed only where its meaning applies (§1.2). The accent is for
*interaction state* (selected, active, focused), never for emphasis. Everything else is ink on
steel. A manager's dashboard with three reds and two ambers is a broken dashboard, not a busy one.

**3. Numbers as first-class type.** Every number that will be compared down a column is tabular,
right-aligned, same decimal places, `₹` prefixed, Indian-grouped (`₹1,23,456.00`). This alone makes
a table look designed. Format with `Intl.NumberFormat('en-IN', { style: 'currency', currency:
'INR' })` **for display only** — money arrives as a string and is never used in arithmetic on the
client (CLAUDE.md invariant 3).

**4. A type scale with intent.** Two families, five sizes on staff surfaces, four on the KDS.
Weight carries hierarchy (400/500/600), size carries level, colour carries state — never two of
them for the same job.

| Token | Staff / manager / owner | KDS (read at 2 m) |
|---|---|---|
| `--text-xs` | 12 px / 16 | — |
| `--text-sm` | 14 px / 20 | 20 px / 26 |
| `--text-base` | 16 px / 24 | 24 px / 30 |
| `--text-lg` | 20 px / 28 | 32 px / 38 |
| `--text-xl` | 25 px / 32 | 40 px / 46 (order numbers) |
| `--text-2xl` | 32 px / 40 | 56 px / 60 (table/ticket id) |

Ratio ≈ 1.25 (major third) on staff; the KDS scale is not a multiple — it is set from legibility
at two metres, which `docs/ui/conventions.md` already fixes at ≥ 20 px base and ≥ 40 px order
numbers. Line length ≤ 70 characters for prose; table cells do not wrap.

**5. Whitespace by density token, not by hand.** A single `--space-unit` (4 px) multiplied by a
per-surface density factor: waiter 1.25 (thumb room), manager 1.0, owner 1.0, KDS 1.5. Screens use
`gap-3`, `p-4`; the surface decides what that means. Nobody hand-tunes padding per screen, which
is where inconsistency comes from.

**6. Iconography with a label.** One set (Lucide, which ships with shadcn/ui), 20 px inline and
24 px in bars, and a primary action always carries a word. An icon-only button is allowed only for
an action a person performs fifty times a shift (add line, bump ticket) and then it is 48 px and
has a tooltip on pointer devices and an `aria-label` everywhere.

### 1.2 Cognitive load: an attention system, not a colour palette

The question a waiter or a manager brings to a screen is *"what needs me right now?"* The answer
must be pre-computed by the interface, not found by reading. Three tiers, always used together:

| Tier | Carries | Rule |
|---|---|---|
| **Colour** | *urgency* | Only the six alert colours, only on things that need an action, never alone (a word or a shape accompanies it) |
| **Position** | *priority* | Whatever needs attention is first: top of the list, left of the KDS, the first card. Sorting by urgency is a design decision made once, in the query |
| **Motion** | *novelty* | One pulse when something *arrives* (new ticket, new order). Nothing blinks. Nothing pulses continuously — a screen that is always moving trains people to ignore movement |

**Colour meaning is fixed across all four surfaces** (from `docs/ui/conventions.md`, extended):

| Token | Meaning | Restaurant examples |
|---|---|---|
| `critical` (red) | act now, money or safety | ticket past its standard time by > 50 %; stock at zero; payment failed; allergy flag on a line |
| `warning` (amber) | act this shift | ticket approaching standard time; stock below `reorder_level`; a preparation expiring today |
| `caution` (yellow) | watch | variance drifting; a table waiting for its bill > 4 min (`docs/customer-experience.md`) |
| `info` (blue) | state, not a problem | ticket acknowledged; order sent; a filter is applied |
| `success` (green) | resolved | served, settled, received |
| `neutral` (slate) | inert | draft, inactive, historical |

Two rules that keep this honest:

- **Bands are relative, not absolute.** A ticket is *late* relative to the dish's `prep_minutes`,
  not a fixed 15 minutes; a stock item is *low* relative to its `reorder_level`. Fixed thresholds
  make a biryani look late at 12 minutes and a naan look fine at 12 minutes. The band boundaries
  are tokens (`--band-warning: 0.8`, `--band-critical: 1.5` of standard) so they can be tuned per
  restaurant later without touching components.
- **One critical per region.** If a viewport region would show more than one red element, the
  region collapses them into a count — *"3 late tickets"* — with the list one tap away. A screen
  is allowed to have one thing that is on fire.

**The attention rail.** Manager and owner surfaces carry a fixed strip at the top: the count of
things needing action per category (late tickets, low stock, open complaints, unreconciled cash),
each a tap from the list behind it. It is the one place where several alert colours may appear
side by side, because there they are a legend, not competing signals.

### 1.3 Layout per surface

**Waiter (phone, one hand, moving).** The table map is the home screen; a table is the unit of
work. The primary action lives in a bottom bar within thumb reach; the order pad is a list with a
sticky total. Two taps from table map to a sent KOT (`docs/ui/conventions.md`): tap table → tap
*Send to kitchen*. Search is a persistent field, not a modal.

```
┌──────────────────────────┐   ┌──────────────────────────┐
│ Spice Garden      ⌕  ≡   │   │ ‹ Table T4  ·  3 guests  │
│ ┌───┬───┬───┬───┐        │   │ ┌──────────────────────┐ │
│ │T1 │T2 │T3 │T4●│  AC    │   │ │ Butter Chicken  Full │ │
│ ├───┼───┼───┼───┤        │   │ │ ₹470  −  1  +        │ │
│ │T5 │T6●│T7 │T8 │        │   │ │ Jain · less spicy    │ │
│ └───┴───┴───┴───┘        │   │ ├──────────────────────┤ │
│ ┌───┬───┬───┐            │   │ │ Garlic Naan  ×3 ₹225 │ │
│ │P1 │P2●│P3 │  Terrace   │   │ └──────────────────────┘ │
│ └───┴───┴───┘            │   │  ⌕ Add item              │
│  ● occupied  ○ free      │   ├──────────────────────────┤
│                          │   │ Total ₹695     ▶ Send to │
│  [ New takeaway ]        │   │                 kitchen  │
└──────────────────────────┘   └──────────────────────────┘
```

A table cell is a word and a shape, never only a colour: `T4 ●` occupied, `T6 ⏱ 4:10` waiting for
bill (caution), `P2 !` needs attention (critical, with the reason on tap). **The one orchestrated
moment in the product:** on *Send to kitchen*, the order card slides up and out toward the top
bar and the table cell changes state in the same 240 ms — the waiter sees the ticket leave their
hand. Optimistic: the card leaves before the server answers; if the send fails, it slides back
with the error under it. Nothing else on the waiter surface animates on its own.

**Kitchen display (wall tablet, 2 m, gloves, steam).** Columns per station, oldest ticket at the
left, no scrolling — the screen shows what fits and pages the rest with a count. A ticket is a
card with the ticket number at 40 px, the elapsed timer counting up, the lines at 24 px, and
modifiers in a second weight, never a second colour. Bump is the whole card, 64 px tall target
area at the bottom. No modals, no hover, no confirmation for bump (undo instead, 5 s, one tap).

```
┌────────────────────────────────────────────────────────────────┐
│ TANDOOR                      12 open · 2 late          19:42   │
├──────────────┬──────────────┬──────────────┬──────────────┬────┤
│ #1042  T4    │ #1043  P2    │ #1044  TAKE  │ #1045  T7    │ +3 │
│ 14:20 LATE   │ 06:12        │ 03:40        │ 00:55  NEW   │    │
│──────────────│──────────────│──────────────│──────────────│    │
│ 2 Garlic Naan│ 1 Paneer     │ 4 Roti       │ 1 Chicken    │    │
│ 1 Roti       │   Tikka Full │              │   Tikka Half │    │
│              │   less spicy │              │              │    │
│ [   Ready   ]│ [   Ready   ]│ [   Ready   ]│ [   Ready   ]│    │
└──────────────┴──────────────┴──────────────┴──────────────┴────┘
```

Late is a thicker red border **and** the word *LATE* **and** leftmost position. New is one 300 ms
pulse of the card's border **and** the word *NEW* for 30 s. The KDS ignores the restaurant's
theme entirely (§3.5): it always renders its own locked high-contrast palette, light by day and
night-shift by default after `business_day_start + 14h`.

**Manager (tablet or laptop, interrupted).** Dense tables, tabular numbers right-aligned, the
attention rail on top, every metric with a comparison chip (*vs yesterday*, *vs last week*) and a
drill-through. Forms are single-column, 560 px max, labels above fields. Row actions appear on the
row, not in a kebab menu three taps deep.

**Owner (laptop, calm).** The health score and five cards with sparklines, each a question the
owner actually asks (*What did we sell? What did it cost? What did we waste? Who was here? What is
wrong?*). This is the only surface where a chart may use the accent colour, and only one series
per chart may be the accent; comparison series are ink at 40 %.

### 1.4 Micro-interactions that earn their place

| Interaction | Treatment | Duration |
|---|---|---|
| Press (touch) | scale 0.98 + tonal darken | 80 ms in, 120 ms out |
| Optimistic write | the row/card changes immediately; a 2 px accent underline shows "saving"; on failure it reverts and the error appears in place | — |
| Success | inline state change (the button becomes the result: *Sent*, *Settled*) rather than a toast; toasts only for actions whose result is elsewhere | 160 ms |
| New KDS ticket | one border pulse | 300 ms |
| Skeleton → content | crossfade, layout already reserved (conventions.md: skeletons match the final layout) | 120 ms |
| Sheet / dialog | slide from bottom on phone, fade+scale on desktop | 200 ms, `cubic-bezier(.2,.8,.2,1)` |
| Timers | count up every second, no animation | — |

`prefers-reduced-motion: reduce` disables everything except the optimistic state change, which is
information. Hover states exist only under `@media (hover: hover)`; a touch device never shows a
hover-dependent affordance.

### 1.5 Words

The strings file already centralises copy; the rules that keep it premium: sentence case; the
button names the outcome (*Send to kitchen*, *Settle ₹695*, *Deactivate Suresh Patil*); the same
verb through the flow (*Publish* → *Published*); errors say what happened and what to do next
(*"Couldn't reach the kitchen. The order is saved — try Send again."*); empty states name what
will appear and how to make it appear (`docs/ui/conventions.md`), and, per
`docs/onboarding-cold-start.md`, analytics that need history show a countdown, not a blank.

---

## 2. The UI skill file: a design system that survives handover

### 2.1 What it is, in this repository

"Skill file" means two things here and both are needed:

| Artefact | Audience | Where | What it is |
|---|---|---|---|
| **Design system document** | any developer, designer, reviewer | `docs/ui/design-system.md` | the human contract: foundations, components, patterns, content, accessibility, governance |
| **Claude skill** | any AI session working in `frontend/` | `.claude/skills/restaurant-ui/SKILL.md` | the AI contract: a short file that says *when* to apply the design system and *what may never be changed*, and points at the document |
| **Machine contracts** | the build | `frontend/src/shared/theme/tokens.css`, the shadcn components in `frontend/src/shared/ui/`, an eslint rule, a gallery route, screenshot tests | what fails when the contract is broken |

The document is the source of truth; the skill and the machine contracts are how it is enforced.
A design system that lives only in a document is a wish (the same lesson as
`docs/engineering-guardrails.md` G-20).

### 2.2 The decision the backlog is waiting on: adopt shadcn/ui, properly, in M02

`docs/ui/conventions.md` says the component library *is* the design system; the backlog says M00
never ran `shadcn init` and M01 hand-rolled `Button`, `Field`, `Notice` on the tokens. Decide now,
before M03/M07 bring real component volume: **adopt shadcn/ui.** Reasons specific to this project:

- Its components already read CSS variables (`--background`, `--foreground`, `--border`,
  `--muted`) with the same names your `index.css` uses — the theming engine in §3 is the one it
  expects, extended.
- Accessibility (focus management, ARIA, keyboard) comes from Radix, which nobody on a solo
  project has time to hand-roll for Dialog, Sheet, Popover, Combobox, Tabs.
- It is copied into the repo, not a dependency: `frontend/src/shared/ui/*` is yours to edit, so
  the 48 px floor and the density token are set once in the copied source.
- The three existing components keep their prop shapes (the backlog notes they already follow
  shadcn's), so the swap is mechanical, and `Notice` maps onto `Alert`.

Configure it with `cssVariables: true`, base colour `slate` (matches your steel neutrals), and
then replace the generated palette with the two-layer tokens in §3.2.

### 2.3 What goes into the design system document — every element

**A. Foundations**

| Element | Must specify |
|---|---|
| Colour | primitive palette (steel 50–950, jamun 50–950, the six alert hues in light and dark); semantic tokens (§3.2) and which primitive each maps to per theme; the "hue budget" rule; contrast floors (4.5:1 text, 3:1 large text and UI, **7:1 on the KDS**) |
| Typography | families and where they are hosted; the two scales (§1.1); weights allowed (400/500/600 only); `font-variant-numeric: tabular-nums` on every number; Devanagari fallback order; line-length limit |
| Spacing | `--space-unit` 4 px; the density factor per surface; the allowed scale (1, 2, 3, 4, 6, 8, 12, 16 units); no arbitrary values (`p-[13px]` is an eslint error) |
| Shape | `--radius-sm/md/lg/full` (4/8/12 px, pill); which component uses which (inputs and buttons `md`, cards `lg`, chips `full`); `--border-width` 1 px |
| Elevation | the three tonal levels; shadows only for overlays; `--shadow-1/2/3` values per theme |
| Motion | the five durations and two easings; what may animate on its own (one thing per surface); reduced-motion behaviour |
| Z-index ladder | a named ladder, never a raw number: `--z-base 0 · --z-sticky 10 · --z-dropdown 20 · --z-sheet 30 · --z-dialog 40 · --z-toast 50 · --z-offline 60`. The offline banner is highest because it must never be covered (`docs/ui/conventions.md`) |
| Surfaces and breakpoints | the four surfaces as `data-surface` values with their target sizes, base type size, density; breakpoints `sm 640 · md 768 · lg 1024 · xl 1280`; which surface renders at which |
| Iconography | Lucide; sizes 16/20/24; stroke 1.75; always with a label on primary actions |
| Formatting | money (`en-IN`, `₹`, two decimals, tabular, negative in parentheses on financial reports); quantities with unit (`1.250 kg`, never base units on screen); dates as business day; times 24 h; relative times only under 1 h |
| Localisation | strings in one file per persona; string keys never contain the English; Devanagari font loaded lazily when the locale changes; numerals stay Latin |

**B. Components** — one page each, same headings every time:

*Purpose · Anatomy (labelled diagram) · Variants · Sizes (with the 48 px floor) · States ·
Content rules · Keyboard and screen reader · Do / Don't (two of each, real examples) · Tokens
used · Code reference (`shared/ui/button.tsx`)*

The **state matrix** is the part people skip and the part that makes a UI feel finished. Every
interactive component defines all of these, even if two look the same:

| State | Definition |
|---|---|
| default | at rest |
| hover | pointer devices only (`@media (hover: hover)`); tonal step |
| focus-visible | 2 px accent ring, 2 px offset; never removed |
| active / pressed | scale 0.98 + tonal darken |
| disabled | 60 % opacity, `cursor: not-allowed`, still readable (AA on disabled text is 3:1) |
| loading / pending | the label stays, a spinner replaces the icon slot, the width does not change |
| error / invalid | `critical` border + message wired with `aria-describedby` (as `Field` already does) |
| selected / checked | accent background at 10 % + accent border; a check icon for colour-blind users |
| destructive | `critical` on the *action*, never on the container |

**C. Patterns** — compositions the screens are built from: page header with attention rail;
data table (sortable header, right-aligned numerics, sticky first column on phones, row actions,
empty state, 50-row cursor paging); form (single column, inline validation on blur, server errors
in place, the primary button disabled only while pending — never for validation); confirmation
(names the thing and the amount; two-step only for money and deletion); sheet vs dialog (sheet on
phone, dialog on desktop, same component); toast; offline banner; **KDS ticket**; **table map
cell**; **order line row**; **money display**; **quantity stepper**; skeleton per pattern.

**D. Content** — voice (§1.5), the strings file conventions, error-code to message mapping, the
"countdown empty state".

**E. Accessibility** — WCAG AA everywhere, AAA contrast on the KDS; keyboard reachability of every
action; focus order equals visual order; touch targets 48 px (64 px on the KDS); no colour-only
meaning; reduced motion; screen-reader names for every icon button; a testing note per pattern.

**F. Performance budgets** (from `docs/engineering-standards.md` §3, restated so designers own
them too): ≤ 250 KB gzipped initial JS per persona bundle; route-level splitting; images with
fixed aspect ratio and a blurred placeholder; no web font over 120 KB per face, `font-display:
swap`, subset to Latin + Devanagari.

**G. Governance** — how a component is added (the third occurrence rule from
`docs/engineering-standards.md` §2, applied to UI); the PR checklist (tokens only, all states
implemented, gallery entry added, screenshot updated, strings in the strings file); who may change
a locked token (nobody without an ADR); versioning of `tokens.css`.

### 2.4 Template: `docs/ui/design-system.md`

```
# Restaurant OS Design System
Status · version · owner · last reviewed

1  Principles                 the pass; hue budget; one moment per surface; words are design
2  Foundations
   2.1 Colour                 primitives · semantic tokens · alert hues · contrast floors
   2.2 Typography             families · hosting · scales · weights · numerals · Devanagari
   2.3 Spacing and density    unit · scale · density per surface
   2.4 Shape and elevation    radii · borders · tonal levels · shadows
   2.5 Motion                 durations · easings · what may move on its own · reduced motion
   2.6 Layering               the z-index ladder
   2.7 Surfaces               waiter · kitchen · manager · owner (targets, type, density, layout)
   2.8 Iconography
   2.9 Formatting             money · quantity · date · time
   2.10 Localisation
3  Components                 one page each, fixed headings (§2.3 B)
4  Patterns                   one page each, with the states they own (§2.3 C)
5  Content                    voice · strings · errors · empty states
6  Accessibility
7  Performance budgets
8  Theming                    what a theme may change · what is locked · how to add a theme (§3)
9  Governance                 adding a component · PR checklist · changing a token · versioning
Appendix A  Token reference   generated from tokens.css
Appendix B  Gallery           the /design route, one screenshot per component state
```

**A filled example — Button (abridged):**

> **Purpose.** Triggers an action. Never navigates (that is a Link, styled to match).
> **Variants.** `primary` (ink on steel; one per view), `secondary` (hairline), `danger`
> (critical; only for money and deletion), `ghost` (toolbars).
> **Sizes.** `md` 48 px (default, the floor), `lg` 56 px (waiter primary), `kds` 64 px. There is
> no `sm` on touch surfaces.
> **States.** All nine from §2.3 B. Loading keeps the label and the width.
> **Content.** Verb + object. *Send to kitchen*, not *Submit*. Money in the label when the action
> moves it: *Settle ₹695*.
> **Keyboard.** Space/Enter activate; focus ring always visible.
> **Do.** One primary per view. **Don't.** Two primaries side by side; icon-only primary.

**A filled example — KDS ticket pattern (abridged):**

> **Owns.** Ticket number (`--text-xl`, mono), destination (table code or *TAKEAWAY*), elapsed
> timer, lines (`--text-base`), modifiers (weight 400, ink-muted, same size), the bump target.
> **Bands.** `new` (info word, one pulse), `preparing` (neutral), `warning` at 0.8× standard,
> `critical` at 1.5× standard; band = colour + word + border weight + position.
> **Never.** Scrolls inside; opens a modal; relies on hover; changes size when the timer ticks.
> **Theme.** Ignores the restaurant theme; uses the locked KDS palette (§3.5).

### 2.5 Template: `.claude/skills/restaurant-ui/SKILL.md`

```markdown
---
name: restaurant-ui
description: Use when creating or changing anything under frontend/src — screens, components,
  styles, tokens, themes, strings. Applies docs/ui/design-system.md and docs/ui/conventions.md
  and refuses changes that break the locked tokens.
---

# Restaurant OS UI

Read `docs/ui/design-system.md` (the contract) and `docs/ui/conventions.md` (the surfaces)
before touching the UI. Then:

1. **Tokens only.** Colour, spacing, radius, shadow, z-index and font come from
   `frontend/src/shared/theme/tokens.css` through Tailwind classes. No hex, no `p-[13px]`,
   no raw `z-50`. If a token is missing, add it to tokens.css in the same change.
2. **Locked tokens are locked.** The six alert hues, the 48 px target floor (64 px KDS), the
   KDS palette and scale, and the z-index ladder change only with an ADR.
3. **Every interactive element implements the nine states** in design-system.md §2.3 B.
4. **Colour never carries meaning alone.** A word or a shape goes with it.
5. **One primary action per view. One self-triggered motion per surface.**
6. **Strings live in the persona's strings file.** No English literals in components.
7. **Numbers are tabular and right-aligned; money is formatted for en-IN and never computed.**
8. **Surface-aware.** Read `data-surface` (waiter / kds / manager / owner) for size and density;
   never hard-code a size for one screen.
9. **Add the component to the /design gallery and its screenshot** in the same change.
10. **Before finishing:** `npm run lint`, the gallery renders every state, and the theme test
    passes for all three shipped themes.

When asked for a new screen: name the surface, name the one primary action, name what needs
attention and how it is shown (colour + word + position), and only then write components.
```

Put the file under `.claude/skills/restaurant-ui/` and it is offered to every session that
touches the frontend. The kickoff prompt for UI work is one line: *"Use the restaurant-ui skill.
Build the M03 menu manager for the manager surface."*

### 2.6 Machine contracts that make the document real

- **`/design` gallery route** (dev builds only): renders every component in every state and every
  theme, from a single registry. It is the visual test surface and the onboarding tour.
- **Screenshot tests** (Playwright, from M07): one image per gallery entry per theme; a diff is a
  review conversation, not a surprise.
- **eslint:** `eslint-plugin-tailwindcss` with `no-arbitrary-value` on colours and spacing;
  a rule banning `style={{ color:` and hex literals in `.tsx`.
- **Theme test** (vitest): every shipped theme file passes the validator in §3.6.

---

## 3. Dynamic theming engine

### 3.1 Architecture in one diagram

```
theme file (JSON, ~60 lines)            restaurant.settings.theme  (jsonb, exists today)
  standard-premium.json                          │  chosen + scheduled in M02 settings screen
  night-shift.json                               ▼
  deepavali.json  ──────────────►  ThemeProvider (React)
                                     · resolves: scheduled festive → device dark/light →
                                       restaurant default → standard
                                     · validates (contrast, hue distance, locked keys)
                                     · writes CSS custom properties on <html data-theme=…>
                                                 │
                                                 ▼
                              tokens.css  (semantic vars, defaults = standard theme)
                                                 │
                                                 ▼
                       tailwind.config.ts  (utilities read the vars: bg-surface, text-ink, …)
                                                 │
                                                 ▼
                              components (shadcn/ui + patterns) — never know a theme exists
```

Three properties make this dramatic-but-safe:

1. **Components read semantic tokens only.** `bg-surface`, `text-ink-muted`, `border-line`,
   `ring-focus`. They never read a primitive (`slate-200`) and never a theme name. A theme can
   therefore change every surface, every radius and every font without a component changing.
2. **A theme is data, not code.** It is a JSON file (or a CSS block — same keys) that sets the
   *exposed* tokens. It cannot add CSS, cannot target components, cannot change layout.
3. **Some tokens are locked.** The engine ignores any key it does not expose, and it validates the
   ones it does.

### 3.2 The token contract (what `tokens.css` declares)

Two layers. **Primitives** are the raw palettes — they exist so themes can be authored quickly by
pointing at them, but no component may use one. **Semantic tokens** are the only thing components
touch. Your current eleven variables map onto the semantic layer with aliases kept during
migration so nothing breaks:

| Semantic token | Meaning | Today's alias |
|---|---|---|
| `--canvas` | page background | `--background` |
| `--surface` | cards, rows, inputs | — |
| `--surface-raised` | hover rows, active tabs, sticky bars | `--muted` |
| `--overlay` | sheets, dialogs, menus | — |
| `--ink` | primary text, primary buttons | `--foreground` |
| `--ink-muted` | secondary text | `--muted-foreground` |
| `--ink-subtle` | placeholders, disabled | — |
| `--line` | hairlines | `--border` |
| `--line-strong` | input borders, table header rule | — |
| `--accent` / `--accent-ink` / `--accent-hover` / `--accent-soft` | interaction colour and its text, hover, and 10 % tint | — |
| `--focus` | focus ring | — |
| `--selection` | text selection, selected row | — |
| `--critical` `--warning` `--caution` `--info` `--success` `--neutral` (+ `-soft`, `-ink` each) | **locked** alert set; two variants (light / dark appearance) chosen by the engine | same names |
| `--radius-sm/md/lg/full`, `--border-width` | shape | — |
| `--shadow-1/2/3`, `--elevation-style` | elevation | — |
| `--font-sans`, `--font-mono`, `--font-display`, `--weight-body`, `--weight-heading`, `--tracking-heading` | type | — |
| `--duration-fast/base/slow`, `--easing`, `--motion-celebrate` | motion | — |
| `--space-unit`, `--density` | spacing | — |
| `--z-*` | **locked** ladder | — |
| `--target-min`, `--text-*` per `data-surface` | **locked** per surface | — |
| `--decor-header`, `--decor-card`, `--decor-glyph` | festive decoration slots (an SVG data URI, a border treatment name, an icon name) | — |

Tailwind reads them with an alpha slot so opacity utilities keep working:

```ts
// tailwind.config.ts — the shape of the mapping, not a rewrite
colors: {
  canvas:  'hsl(var(--canvas) / <alpha-value>)',
  surface: { DEFAULT: 'hsl(var(--surface) / <alpha-value>)', raised: 'hsl(var(--surface-raised) / <alpha-value>)' },
  ink:     { DEFAULT: 'hsl(var(--ink) / <alpha-value>)', muted: 'hsl(var(--ink-muted) / <alpha-value>)', subtle: '…' },
  line:    { DEFAULT: 'hsl(var(--line) / <alpha-value>)', strong: '…' },
  accent:  { DEFAULT: 'hsl(var(--accent) / <alpha-value>)', ink: '…', hover: '…', soft: '…' },
  critical: { DEFAULT: 'hsl(var(--critical) / <alpha-value>)', soft: '…', ink: '…' }, // ×6
  // keep during migration so existing classes still resolve:
  background: 'hsl(var(--canvas) / <alpha-value>)', foreground: 'hsl(var(--ink) / <alpha-value>)',
  border: 'hsl(var(--line) / <alpha-value>)', muted: 'hsl(var(--surface-raised) / <alpha-value>)',
  'muted-foreground': 'hsl(var(--ink-muted) / <alpha-value>)',
},
borderRadius: { sm: 'var(--radius-sm)', md: 'var(--radius-md)', lg: 'var(--radius-lg)', full: 'var(--radius-full)' },
boxShadow:    { 1: 'var(--shadow-1)', 2: 'var(--shadow-2)', 3: 'var(--shadow-3)' },
fontFamily:   { sans: 'var(--font-sans)', mono: 'var(--font-mono)', display: 'var(--font-display)' },
transitionDuration: { fast: 'var(--duration-fast)', DEFAULT: 'var(--duration-base)', slow: 'var(--duration-slow)' },
zIndex: { sticky: 'var(--z-sticky)', dropdown: 'var(--z-dropdown)', sheet: 'var(--z-sheet)', dialog: 'var(--z-dialog)', toast: 'var(--z-toast)', offline: 'var(--z-offline)' },
```

Surfaces are a second attribute, orthogonal to the theme: `<body data-surface="waiter">` sets
`--target-min`, the `--text-*` scale and `--density`. A theme file cannot touch these.

### 3.3 The theme file: exactly what is exposed

```ts
type ThemeFile = {
  $schema: 'restaurant-os/theme/v1';
  id: string;                 // 'standard-premium'
  name: string;               // shown in Settings
  appearance: 'light' | 'dark';         // selects the locked alert set and color-scheme
  schedule?: { from: string; to: string };   // inclusive business dates, restaurant timezone
  surfaces?: ('waiter' | 'manager' | 'owner')[];  // default all three; 'kds' is never accepted
  color: {                    // HSL triples, "H S% L%"
    canvas: string; surface: string; surfaceRaised: string; overlay: string;
    ink: string; inkMuted: string; inkSubtle: string;
    line: string; lineStrong: string;
    accent: string; accentInk: string; accentHover: string; accentSoft: string;
    focus: string; selection: string;
  };
  shape: { radiusSm: string; radiusMd: string; radiusLg: string; radiusFull: string; borderWidth: string };
  elevation: { style: 'tonal' | 'shadow'; shadow1: string; shadow2: string; shadow3: string };
  type: { sans: string; mono: string; display?: string; weightBody: 400 | 500; weightHeading: 500 | 600 | 700; trackingHeading: string };
  motion: { fast: string; base: string; slow: string; easing: string; celebrate?: boolean };
  density?: { unit: string };            // '4px' default; themes may nudge ±1px, no more
  decoration?: {
    headerTexture?: string;              // SVG data URI, ≤ 4 KB, rendered at ≤ 8 % opacity
    cardOrnament?: 'none' | 'hairline-accent' | 'hairline-gold';
    accentGlyph?: string;                // a Lucide icon name shown beside the restaurant name
  };
};
```

**What is deliberately not in the file:** the six alert colours; `--z-*`; target sizes; the
per-surface type scales; the KDS palette; layout of any kind; component overrides. If a key
outside the contract appears, the loader logs it and drops it.

### 3.4 Three theme files

**1. Standard Premium — "Steel & Jamun"** (`frontend/src/shared/theme/themes/standard-premium.json`)

```json
{
  "$schema": "restaurant-os/theme/v1",
  "id": "standard-premium",
  "name": "Standard",
  "appearance": "light",
  "color": {
    "canvas": "210 20% 98%",
    "surface": "0 0% 100%",
    "surfaceRaised": "210 24% 96%",
    "overlay": "0 0% 100%",
    "ink": "222 47% 11%",
    "inkMuted": "215 16% 38%",
    "inkSubtle": "215 14% 58%",
    "line": "214 32% 91%",
    "lineStrong": "215 20% 78%",
    "accent": "322 40% 32%",
    "accentInk": "0 0% 100%",
    "accentHover": "322 42% 26%",
    "accentSoft": "322 40% 95%",
    "focus": "322 55% 42%",
    "selection": "322 40% 92%"
  },
  "shape": { "radiusSm": "4px", "radiusMd": "8px", "radiusLg": "12px", "radiusFull": "999px", "borderWidth": "1px" },
  "elevation": {
    "style": "tonal",
    "shadow1": "0 1px 2px hsl(222 47% 11% / 0.06)",
    "shadow2": "0 4px 12px hsl(222 47% 11% / 0.08)",
    "shadow3": "0 16px 40px hsl(222 47% 11% / 0.14)"
  },
  "type": {
    "sans": "'IBM Plex Sans', 'IBM Plex Sans Devanagari', system-ui, sans-serif",
    "mono": "'IBM Plex Mono', ui-monospace, monospace",
    "weightBody": 400,
    "weightHeading": 600,
    "trackingHeading": "-0.01em"
  },
  "motion": { "fast": "120ms", "base": "180ms", "slow": "240ms", "easing": "cubic-bezier(0.2, 0.8, 0.2, 1)" },
  "density": { "unit": "4px" },
  "decoration": { "cardOrnament": "none" }
}
```

**2. Night Shift** (`night-shift.json`) — for the 7 pm to 2 am floor and for phones in a dim
dining room; note the accent lifts in lightness so it still clears 4.5:1, and shadows gain a
little weight because tonal steps alone are hard to read on dark.

```json
{
  "$schema": "restaurant-os/theme/v1",
  "id": "night-shift",
  "name": "Night shift",
  "appearance": "dark",
  "color": {
    "canvas": "222 30% 8%",
    "surface": "222 26% 12%",
    "surfaceRaised": "222 24% 16%",
    "overlay": "222 24% 14%",
    "ink": "210 20% 96%",
    "inkMuted": "215 15% 70%",
    "inkSubtle": "215 12% 52%",
    "line": "220 15% 22%",
    "lineStrong": "220 15% 32%",
    "accent": "322 45% 64%",
    "accentInk": "222 30% 8%",
    "accentHover": "322 48% 70%",
    "accentSoft": "322 30% 18%",
    "focus": "322 55% 68%",
    "selection": "322 30% 22%"
  },
  "shape": { "radiusSm": "4px", "radiusMd": "8px", "radiusLg": "12px", "radiusFull": "999px", "borderWidth": "1px" },
  "elevation": {
    "style": "shadow",
    "shadow1": "0 1px 2px hsl(0 0% 0% / 0.4)",
    "shadow2": "0 6px 16px hsl(0 0% 0% / 0.45)",
    "shadow3": "0 20px 48px hsl(0 0% 0% / 0.6)"
  },
  "type": {
    "sans": "'IBM Plex Sans', 'IBM Plex Sans Devanagari', system-ui, sans-serif",
    "mono": "'IBM Plex Mono', ui-monospace, monospace",
    "weightBody": 400,
    "weightHeading": 600,
    "trackingHeading": "-0.01em"
  },
  "motion": { "fast": "120ms", "base": "180ms", "slow": "240ms", "easing": "cubic-bezier(0.2, 0.8, 0.2, 1)" },
  "density": { "unit": "4px" },
  "decoration": { "cardOrnament": "none" }
}
```

**3. Festive — "Deepavali"** (`deepavali.json`) — warm ivory canvas, a richer wine accent that is
still 40° of hue away from `critical`, gold as a *hairline ornament* only (gold is next to
`caution` and may never be an interactive colour), a diya glyph beside the restaurant name, a
low-opacity rangoli texture in the header, and a celebratory confirmation on settle. Scheduled by
business date so it appears and disappears on its own.

```json
{
  "$schema": "restaurant-os/theme/v1",
  "id": "deepavali",
  "name": "Deepavali",
  "appearance": "light",
  "schedule": { "from": "2026-11-05", "to": "2026-11-12" },
  "surfaces": ["waiter", "manager", "owner"],
  "color": {
    "canvas": "36 45% 97%",
    "surface": "0 0% 100%",
    "surfaceRaised": "36 40% 94%",
    "overlay": "0 0% 100%",
    "ink": "24 30% 12%",
    "inkMuted": "24 14% 38%",
    "inkSubtle": "24 12% 58%",
    "line": "36 30% 88%",
    "lineStrong": "36 22% 72%",
    "accent": "335 58% 30%",
    "accentInk": "0 0% 100%",
    "accentHover": "335 60% 24%",
    "accentSoft": "335 50% 95%",
    "focus": "335 60% 42%",
    "selection": "335 45% 92%"
  },
  "shape": { "radiusSm": "4px", "radiusMd": "10px", "radiusLg": "16px", "radiusFull": "999px", "borderWidth": "1px" },
  "elevation": {
    "style": "tonal",
    "shadow1": "0 1px 2px hsl(24 30% 12% / 0.06)",
    "shadow2": "0 4px 14px hsl(24 30% 12% / 0.10)",
    "shadow3": "0 16px 40px hsl(24 30% 12% / 0.16)"
  },
  "type": {
    "sans": "'IBM Plex Sans', 'IBM Plex Sans Devanagari', system-ui, sans-serif",
    "mono": "'IBM Plex Mono', ui-monospace, monospace",
    "display": "'IBM Plex Serif', Georgia, serif",
    "weightBody": 400,
    "weightHeading": 600,
    "trackingHeading": "0"
  },
  "motion": { "fast": "120ms", "base": "200ms", "slow": "280ms", "easing": "cubic-bezier(0.2, 0.8, 0.2, 1)", "celebrate": true },
  "density": { "unit": "4px" },
  "decoration": {
    "cardOrnament": "hairline-gold",
    "accentGlyph": "flame",
    "headerTexture": "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 80 80'><g fill='none' stroke='%23b8860b' stroke-width='1'><circle cx='40' cy='40' r='30'/><circle cx='40' cy='40' r='18'/><path d='M40 10v60M10 40h60M19 19l42 42M61 19L19 61'/></g></svg>"
  }
}
```

Christmas is the same file with `canvas` toward a cool white, `accent` a deep pine
(`160 40% 24%` — 18° from `success`, which the validator flags; use `170 35% 22%` instead),
`cardOrnament: "hairline-accent"`, `accentGlyph: "snowflake"`. Valentine's: `accent` `340 55% 36%`,
`headerTexture` a heart lattice. None of them touch a status colour, a target size or the KDS.

**CSS form.** The same contract can be authored as CSS for people who prefer it; the loader
accepts either and converts JSON to exactly this:

```css
[data-theme="deepavali"] {
  color-scheme: light;
  --canvas: 36 45% 97%;  --surface: 0 0% 100%;  --surface-raised: 36 40% 94%;
  --ink: 24 30% 12%;     --ink-muted: 24 14% 38%;
  --accent: 335 58% 30%; --accent-ink: 0 0% 100%; --accent-soft: 335 50% 95%;
  --radius-md: 10px;     --radius-lg: 16px;
  --font-display: 'IBM Plex Serif', Georgia, serif;
  --decor-card: hairline-gold;
  /* alert tokens, z-index, targets: not settable here — the engine writes them */
}
```

### 3.5 What a theme can never do (the locked layer)

| Locked | Why |
|---|---|
| The six alert hues and their meanings | red is *act now* in every restaurant, every season; a festive theme that makes red decorative breaks the one promise the KDS makes |
| The KDS palette and scale | the kitchen display always renders its own high-contrast set (light by day; night-shift after `business_day_start + 14h`, switchable on the device). It ignores `data-theme` entirely — `surfaces` cannot include `kds` |
| Contrast floors | 4.5:1 text, 3:1 UI, 7:1 KDS; a theme that fails is not applied |
| Hue distance | the accent must be ≥ 25° of hue from every alert hue at similar lightness, or the validator refuses it — this is what stops "festive gold" colliding with `caution` and "festive red" with `critical` |
| Targets, z-index ladder, per-surface type scales, density beyond ±1 px | the physical contract with a thumb, a glove and two metres of steam |
| Layout, component structure, copy | a theme is paint |

### 3.6 Resolution, validation, persistence

**Resolution order** (first match wins): a *scheduled* theme whose window contains today's
business date (restaurant timezone, `business_day_start` — ADR 0004) → the device's manual
override (a person chose dark on this phone) → `prefers-color-scheme` if the restaurant allows
auto-dark → the restaurant's default theme from `restaurant.settings.theme` → `standard-premium`.

**Validation** runs at load and in a vitest test over every shipped theme: all exposed keys
present; every `ink*`-on-`canvas`/`surface`/`surface-raised` pair and `accent-ink`-on-`accent`
pair meets the floor; accent hue distance; `headerTexture` ≤ 4 KB and `data:image/svg+xml` only;
no key outside the contract. A failing theme falls back to `standard-premium` with one
`console.warn` — the app never renders unreadable.

**Persistence.** The restaurant's choice and schedule live in `restaurant.settings.theme`
(already `jsonb`), edited on the M02 settings screen with a live preview (the gallery route in
miniature). The per-device override lives in `localStorage` — it is a convenience, it may vanish,
and the resolver copes when it does. Nothing about a theme is ever sent to the server from a
device.

**Applying** is the whole engine — illustrative shape, ~20 lines in `applyTheme.ts`:

```ts
export function applyTheme(theme: ThemeFile, root = document.documentElement): void {
  const problems = validate(theme);            // contrast, hue distance, contract keys
  if (problems.length) { console.warn('theme rejected', theme.id, problems); theme = STANDARD; }
  root.dataset.theme = theme.id;
  root.style.colorScheme = theme.appearance;
  for (const [key, value] of Object.entries(flatten(theme))) {   // color.inkMuted → --ink-muted
    root.style.setProperty(key, value);
  }
  applyAlertSet(root, theme.appearance);       // the locked six, light or dark variant
}
```

`ThemeProvider` calls it once on mount and again on schedule change (a timer at the next business
day boundary), on `prefers-color-scheme` change, and on settings change. Components never
re-render for a theme change — the browser repaints custom properties.

### 3.7 Fonts, hosted

`@fontsource-variable/ibm-plex-sans`, `@fontsource/ibm-plex-mono`, `@fontsource/ibm-plex-sans-devanagari`,
`@fontsource/ibm-plex-serif` (festive display only, loaded lazily with the theme). Self-hosted
because restaurant WiFi is bad, third-party font hosts are a privacy and CSP question
(`docs/security.md` A05), and `font-display: swap` with a metric-compatible fallback
(`system-ui`) means the first paint is never blocked. Subset Latin + Devanagari; each face
≤ 120 KB.

---

## 4. Rollout, mapped to the module plan

| When | Do | Why then |
|---|---|---|
| **M02 (now)** | `shadcn init`; two-layer `tokens.css` with the migration aliases; load Plex; `ThemeProvider` + `applyTheme` + the three theme files + the validator test; the theme picker and schedule on the restaurant settings screen (`PATCH /restaurant`, `settings.theme`); `data-surface` on `<body>`; the `/design` gallery route; `docs/ui/design-system.md` and `.claude/skills/restaurant-ui/SKILL.md` | M02 owns restaurant settings and is the last module before component volume |
| **M03** | first dense screen (menu manager) built only from tokens and shadcn; the data-table pattern; dish image aspect ratio + placeholder | proves the system on real density |
| **M07** | waiter surface: table map cell, order line row, bottom bar, the send-to-kitchen moment; Playwright screenshots start | the surface with the most physical constraints |
| **M08** | KDS: locked palette, night switch, ticket pattern, 64 px bump | the surface that ignores themes |
| **M13** | owner charts with the `dataviz` skill; one accent series rule | first charts |

**This week, without waiting for M02:** decide shadcn (yes), pick the family (Plex), and copy
§2.4 and §2.5 into their files. Those three decisions remove most of the future arguments.

---

## Appendix — hand-over checklist for a new developer or a new AI session

1. Read `docs/ui/conventions.md`, then `docs/ui/design-system.md`, then open `/design`.
2. Build only from `frontend/src/shared/ui/*` and tokens; if a token is missing, add it.
3. Name the surface, the one primary action, and what needs attention, before writing JSX.
4. Implement all nine states; add the gallery entry; run the theme test.
5. Money is a string; numbers are tabular; colour is never alone; one thing moves on its own.
