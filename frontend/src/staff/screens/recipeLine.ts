// The rule for adding a line to a recipe, kept out of the screen.
//
// Its own module for two reasons. A React file that exports anything but components loses fast
// refresh, and this rule is the part of the editor most worth testing directly — Radix's Select
// needs a real pointer and jsdom has none, so driving the picker in a test is not an option.

import { strings } from '@staff/strings';

export type Draft = { component_id: string; quantity: string };

/** A quantity: up to four decimals, because 0.05 g of saffron is a real recipe line. */
const QUANTITY = /^\d{1,8}(\.\d{1,4})?$/;

/**
 * A measurement greater than zero.
 *
 * Exported because quantities are editable in place, so a line that was valid when it was added
 * can be blank or zero by the time Save is pressed. Checking only on add would send the whole
 * version to the server and have it refused by a CHECK constraint after the round trip.
 */
export function isQuantity(quantity: string): boolean {
  return QUANTITY.test(quantity.trim()) && Number(quantity) > 0;
}

/**
 * The lines as one comparable string, for "has this draft diverged from what was saved?".
 *
 * Order is preserved rather than sorted: reordering a recipe is a change a chef may mean to save,
 * and `seq` is what the line order becomes.
 */
export function serialise(lines: Draft[]): string {
  return lines.map((line) => `${line.component_id}:${line.quantity.trim()}`).join('|');
}

/**
 * What is wrong with a line somebody is about to add, or `null` if nothing is.
 *
 * Each of these is a refusal the server would also make, and making it here is the difference
 * between a sentence and a round trip. The duplicate matters most: `recipe_line`'s primary key is
 * the pair, so a repeat reaches the database as an `IntegrityError` and — that exception being
 * unmapped — comes back as a 500 with nothing a person can act on.
 */
export function problemWith(
  componentId: string,
  quantity: string,
  existing: Draft[],
): string | null {
  if (componentId === '') {
    return strings.recipe.pickOne;
  }
  if (existing.some((line) => line.component_id === componentId)) {
    return strings.recipe.duplicate;
  }
  // A quantity is a measurement and not money, so a number is honest here — but zero is not a
  // quantity, and the server's CHECK would refuse it after the round trip.
  if (!isQuantity(quantity)) {
    return strings.recipe.noQuantity;
  }
  return null;
}
