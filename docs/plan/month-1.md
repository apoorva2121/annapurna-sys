# Month 1 — Plan

Scope decision stands: build **all of vision doc §34 Phase 1**. This document says what fits in the
first twenty working days, derived from the module estimates in `docs/modules.md` rather than from
optimism. Process: `docs/sdlc.md`.

## The arithmetic

A month is **20 working days**. Module estimates:

| | | | | | | |
|---|---|---|---|---|---|---|
| M00 Foundation | M01 Identity | M02 Setup | M03 Menu | M04 Recipes | M05 Inventory | **subtotal** |
| 1 | 3 | 2 | 3 | 4 | 4 | **17** |

That leaves 3 days, which start M07 Orders (6 days total). So month 1 delivers **M00–M05 complete,
M07 begun** — and nothing else, honestly.

An earlier draft of this plan claimed month 1 would reach M08. Adding those estimates up gives 30
days. It would not have. Better to know that now.

## Why this order, and not "orders first"

M07 Orders depends on M05 Inventory, because settling an order posts theoretical stock consumption
and freezes a food cost. Building the POS before the ledger means either building it twice, or
shipping a POS that silently does not feed the thing the product actually sells.

One consequence worth noticing: the dependency chain front-loads recipes, costing and the stock
ledger — the differentiated part of the product. At the end of month 1 you can show a restaurateur
their true dish-level food cost, which is the conversation that sells this. The POS follows.

## Week by week

Each week ends with something running on the **staging URL**, not on a branch.

### Week 1 — M00 Foundation, M01 Identity, M02 start
Repo, Docker Compose, lint/type/test harness, CI, structured logging with PII redaction, error
envelope, health endpoints, **staging deploy working on day 1–2**. Then auth, RBAC, employees,
tenant scoping.

**Exit:** two restaurants exist; A's manager cannot read B's data, proven by test **and** by your
manual probe D1. `docs/manual-tests/M01-identity.md`.

### Week 2 — M02 Setup, M03 Menu, M04 start
Restaurant settings (timezone, business day start, GSTIN), dining areas, tables, stations, tax
groups. Then the menu tree with prices on variants and `food_type`.

**Exit:** the seeded Spice Garden menu is visible and editable in the UI.

### Week 3 — M04 Recipes complete, M05 start
Stock items, ingredient and preparation profiles, nested recipes, versioning, recursive cost rollup.
Then the stock ledger begins.

**Exit:** the app computes Butter Chicken (Full) at **₹126.70** and makhani gravy at **₹0.1489/ml**,
matching `seed/validate.py` exactly. This is the golden test and the commercial proof point.

### Week 4 — M05 Inventory complete, M07 Orders begun
Batches, append-only movements, FEFO with row locking, receipts, adjustments, physical counts,
expiry and low-stock alerts. Then order creation and line management.

**Exit:** receiving stock creates batches; a manual consumption draws from the oldest batch first;
on-hand always equals the sum of movements.

## What follows month 1

M07 finish, M08 Kitchen, M09 Waste, M10 Customers, M11 Comms, M12 Shifts, M13 Dashboards,
M14 Audit, M15 Seed generator, M16 Hardening — a further ~40 working days. Full detail and
dependency order in `docs/modules.md`.

## The non-code track — runs in parallel, all month

Code alone does not produce revenue, and we are building without a live test site.

1. **Get a photo of the pilot restaurant's printed menu.** Not a spreadsheet — they do not have one.
   A photo is a two-minute ask and it reveals portion sizes, price points and menu breadth.
2. **Ask them:** *"What do you think your food cost percentage is?"* Then: *"How do you know?"* The
   gap between those two answers is the pitch. Write down exactly what they say.
3. ~~**Start the starter recipe library**~~ **Done 2026-09-12 — `library/`**, 223 dishes and 36
   preparations with confidence tiers (`library/README.md`). What remains is a chef's pass over the
   `estimated` tier, which is the pilot restaurant's job during onboarding, not ours before it.
4. **Draft pricing.** Anchor on savings: our seed data shows a ~6-point gap between theoretical and
   actual food cost — about ₹95,000/month on ₹15.5L revenue. ₹5,000–8,000/outlet/month prices
   comfortably against that.

## Deferred, deliberately

Payment gateway, printers and hardware, offline-first sync, GST e-invoicing filing, CCTV (§22),
React Native, multi-branch rollups, and all of Phase 2/3/4. The architecture must not block them;
month 1 must not contain them.
