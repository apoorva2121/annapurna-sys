/**
 * Money, formatted the way India writes it.
 *
 * `docs/ui/conventions.md` lists this under Non-negotiables: "`₹` prefix, Indian digit grouping
 * (₹1,23,456), two decimals, tabular numerals". M03 is the first module to display a price, so it
 * is the first that needs this.
 *
 * **The grouping is the part people get wrong.** Indian digit grouping is not every three digits —
 * it is three, then two, then two: 1,23,456 and not 123,456. `Intl.NumberFormat('en-IN')` knows
 * this and hand-rolled `toLocaleString` calls with the wrong locale do not.
 *
 * **Nothing here does arithmetic.** Every amount arrives from the server as a decimal *string*
 * (`"470.00"`) precisely so that no JavaScript number ever touches a rupee figure — `0.1 + 0.2`
 * is the reason, and a bill that does not reconcile is the consequence (CLAUDE.md invariant 3).
 * These functions parse for display and throw the number away. If you find yourself wanting to add
 * two of these, the sum belongs on the server.
 */

const RUPEES = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/**
 * `"470"` → `"₹470.00"`, `"123456.5"` → `"₹1,23,456.50"`.
 *
 * A value that is not a number renders as an em dash rather than as `₹NaN`. A price is always
 * present in this product — the column is NOT NULL — so this path means something upstream is
 * wrong, and showing a dash is the version of that which does not look like a real amount.
 */
export function formatINR(amount: string | number | null | undefined): string {
  if (amount === null || amount === undefined || amount === '') {
    return '—';
  }
  const value = Number(amount);
  if (!Number.isFinite(value)) {
    return '—';
  }
  return RUPEES.format(value);
}

/**
 * A price *change*, signed: `"+₹40.00"`, `"−₹20.00"`, or `"Free"` at zero.
 *
 * Used for `modifier.price_delta`, which may legitimately be negative — "no rice" can be a
 * discount. The minus is U+2212, the real minus sign, not a hyphen: at the sizes a waiter reads
 * a modifier list, a hyphen is easy to miss entirely.
 */
export function formatDelta(amount: string | number | null | undefined): string {
  if (amount === null || amount === undefined || amount === '') {
    return '';
  }
  const value = Number(amount);
  if (!Number.isFinite(value) || value === 0) {
    return '';
  }
  const sign = value > 0 ? '+' : '−';
  return `${sign}${RUPEES.format(Math.abs(value))}`;
}
