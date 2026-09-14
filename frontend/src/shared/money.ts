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

/** `123`, `123.4`, `123.45`, optionally signed. Up to ten whole digits, which is more than any
 *  menu price and less than anything that could overflow `numeric(12,2)` on the server. */
const AMOUNT = /^([+-]?)(\d{1,10})(?:\.(\d{1,2}))?$/;

const ZERO = /^0+\.00$/;

/** The three capture groups, defaulted. Optional groups are genuinely `undefined` when they do not
 *  participate, and a successful match does not prove otherwise to TypeScript. */
function groups(match: RegExpExecArray): [string, string, string] {
  return [match[1] ?? '', match[2] ?? '0', match[3] ?? ''];
}

/**
 * What a person typed, turned into the string the API expects — **without a `Number` in between**.
 *
 * `Number(input).toFixed(2)` looks equivalent and is not. It parses a rupee amount into a binary
 * float and formats it back, which is exactly the round-trip CLAUDE.md invariant 3 forbids, on the
 * *write* path where the result is stored rather than merely shown. It is also quietly permissive:
 * `Number` accepts `"1e3"`, `"0x10"`, `" 12 "` and `"Infinity"`, so a typo becomes a price instead
 * of a refusal. Both screens that price something did this until the M03/M04 review.
 *
 * Returns `null` when the input is not an amount, which the caller must treat as "do not send".
 * Padding is string surgery: `"12.5"` → `"12.50"`.
 */
export function parseAmount(
  input: string,
  { allowNegative = false }: { allowNegative?: boolean } = {},
): string | null {
  const match = AMOUNT.exec(input.trim());
  if (match === null) {
    return null;
  }
  const [sign, whole, fraction] = groups(match);
  if (sign === '-' && !allowNegative) {
    return null;
  }
  const padded = `${whole}.${fraction.padEnd(2, '0')}`;
  // The only digit test here, and it is about a sign rather than a value: "-0.00" is zero written
  // oddly, and reading it back as "-0.00" would look like a change nobody made.
  if (sign === '-' && !ZERO.test(padded)) {
    return `-${padded}`;
  }
  return padded;
}

/** A percentage from 0 to 100, with at most two decimals. */
const PERCENT = /^(\d{1,3})(?:\.(\d{1,2}))?$/;

/**
 * `"5"` → `"0.0500"`, `"12.5"` → `"0.1250"`: a typed percentage as the four-decimal fraction the API
 * stores, made by moving the decimal point in the string — never through a float (backlog-issues B6).
 *
 * A tax rate is not money, but it is copied onto every order line and can only be superseded, never
 * edited, so it deserves the same care. Returns `null` for anything that is not a percentage from 0
 * to 100 with at most two decimals — including `"1e1"`, which `Number` reads as ten.
 */
export function percentToFraction(input: string): string | null {
  const match = PERCENT.exec(input.trim());
  if (match === null) {
    return null;
  }
  // Hundredths of a percent, as a digit string: "12.5" → "1250".
  const hundredths = `${match[1] ?? '0'}${(match[2] ?? '').padEnd(2, '0')}`.replace(/^0+(?=\d)/, '');
  if (hundredths.length > 5 || (hundredths.length === 5 && hundredths !== '10000')) {
    return null;
  }
  const padded = hundredths.padStart(5, '0');
  return `${padded.slice(0, 1)}.${padded.slice(1)}`;
}
