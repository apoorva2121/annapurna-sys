import { strings } from '@staff/strings';

/**
 * Which unit a delivery or an order line is typed in (backlog-issues B12e).
 *
 * A supplier sells cabbage by the kilo; the ledger holds grams. The person at the gate types what
 * the invoice says, so the form labels its boxes in the item's **purchase unit** and tells the
 * server so (`per_purchase_unit`), and the server does the one conversion. No arithmetic happens
 * here — a price divided by a thousand in the browser is the float round-trip CLAUDE.md invariant 3
 * forbids, and the ₹40-a-gram cabbage is what a unit mix-up on this form costs.
 *
 * Pure, and its own module, because the Radix Select that chooses the item cannot be driven in
 * jsdom: the rule is tested here and the screens only apply it.
 */

export type UnitAwareItem = {
  id: string;
  base_unit: string;
  ingredient: { purchase_unit: string } | null;
};

export type TypedIn = {
  /** What the boxes are labelled in: the purchase unit when the item has one, else its base unit. */
  unit: string;
  /** Whether the server must convert. `false` for a preparation or an item with no profile. */
  perPurchaseUnit: boolean;
};

export function typedIn(items: readonly UnitAwareItem[], stockItemId: string): TypedIn {
  const item = items.find((candidate) => candidate.id === stockItemId);
  if (item === undefined) {
    return { unit: '', perPurchaseUnit: false };
  }
  if (item.ingredient === null || item.ingredient.purchase_unit === item.base_unit) {
    return { unit: item.base_unit, perPurchaseUnit: false };
  }
  return { unit: item.ingredient.purchase_unit, perPurchaseUnit: true };
}

/** "Quantity (kg)", or plain "Quantity" until an item is chosen. */
export function quantityLabel(unit: string): string {
  return unit === '' ? strings.units.quantity : strings.units.quantityIn(unit);
}

/** "Price per kg", or "Price per unit" until an item is chosen. */
export function priceLabel(unit: string): string {
  return unit === '' ? strings.units.pricePerUnit : strings.units.pricePer(unit);
}
