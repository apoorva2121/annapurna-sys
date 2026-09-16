import type { StockItem } from '@staff/api/stock';

/**
 * The quantity presets on the waste screen, and the unit they are in.
 *
 * Its own module for the reason `purchaseUnits.ts` and `kitchenRail.ts` are: a screen file that
 * exports anything but components loses fast refresh, and `npm run lint` runs at
 * `--max-warnings 0`.
 *
 * **Nothing here converts anything.** The presets are numbers in the item's *purchase* unit — a
 * cook thinks in half a kilo of paneer, not five hundred grams — and the request carries a flag
 * saying so. The server does the one conversion. A quantity divided by a thousand in a browser is
 * the float round-trip CLAUDE.md invariant 3 forbids, and the reason that rule exists is in
 * `docs/backlog.md`: a delivery typed against the wrong unit repriced cabbage to ₹40 per *gram*
 * and made a plate of Veg Manchurian cost ₹5,207.
 */

/**
 * Four buttons, from `docs/waste-model.md`: "quantity (with big preset buttons: ¼, ½, 1, 2)".
 *
 * Four and not six, because the screen is worked one-handed by somebody standing at a bin, and the
 * difference between a quarter and a third of a tray is not worth the second it costs to choose.
 * Strings rather than numbers all the way to the wire, so no float ever touches a quantity.
 */
export const PRESETS = ['0.25', '0.5', '1', '2'] as const;

export type Preset = (typeof PRESETS)[number];

const FRACTIONS: Record<string, string> = {
  '0.25': '¼',
  '0.5': '½',
};

/** "½ kg", "1 kg". The fraction rather than the decimal, because it is read at a glance. */
export function presetLabel(preset: string, unit: string): string {
  return `${FRACTIONS[preset] ?? preset} ${unit}`.trim();
}

/**
 * What this item is bought in — the unit the presets mean.
 *
 * Falls back to the base unit for a preparation, or an ingredient with no purchase profile, in
 * which case the presets are base units and `perPurchaseUnit` must be false. Same rule
 * `purchaseUnits.typedIn` applies to the receiving form.
 */
export function unitFor(item: StockItem): string {
  if (item.ingredient === null || item.ingredient.purchase_unit === item.base_unit) {
    return item.base_unit;
  }
  return item.ingredient.purchase_unit;
}

/** Whether the server has to convert what the presets sent. */
export function isPerPurchaseUnit(item: StockItem): boolean {
  return item.ingredient !== null && item.ingredient.purchase_unit !== item.base_unit;
}
