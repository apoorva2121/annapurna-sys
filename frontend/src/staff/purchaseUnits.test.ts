// The unit a delivery is typed in. The ₹40-a-gram cabbage came from a price per kilo typed into a
// box that meant per gram; these pin the rule that decides what the box says.

import { describe, expect, it } from 'vitest';

import { priceLabel, quantityLabel, typedIn } from './purchaseUnits';

const ITEMS = [
  { id: 'cabbage', base_unit: 'g', ingredient: { purchase_unit: 'kg' } },
  { id: 'eggs', base_unit: 'unit', ingredient: { purchase_unit: 'unit' } },
  { id: 'gravy', base_unit: 'ml', ingredient: null },
];

describe('the unit a line is typed in', () => {
  it('is the purchase unit when the item is bought in one', () => {
    expect(typedIn(ITEMS, 'cabbage')).toEqual({ unit: 'kg', perPurchaseUnit: true });
  });

  it('needs no conversion when the purchase unit is the base unit', () => {
    expect(typedIn(ITEMS, 'eggs')).toEqual({ unit: 'unit', perPurchaseUnit: false });
  });

  it('falls back to the base unit for an item with no purchase profile', () => {
    expect(typedIn(ITEMS, 'gravy')).toEqual({ unit: 'ml', perPurchaseUnit: false });
  });

  it('has no unit until an item is chosen', () => {
    expect(typedIn(ITEMS, '')).toEqual({ unit: '', perPurchaseUnit: false });
  });
});

describe('the labels', () => {
  it('name the unit beside the number, so 12 kg cannot be typed as 12 g', () => {
    expect(quantityLabel('kg')).toBe('Quantity (kg)');
    expect(priceLabel('kg')).toBe('Price per kg');
  });

  it('are plain until there is a unit to name', () => {
    expect(quantityLabel('')).toBe('Quantity');
    expect(priceLabel('')).toBe('Price per unit');
  });
});
