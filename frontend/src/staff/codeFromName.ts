/**
 * The stable code behind a menu object, derived from its name.
 *
 * Codes used to be typed by hand and shown beside every name, so a browse list read
 * *"Veg Starters STARTER_VEG"* — the same thing said twice, once for a person and once for the
 * database. The owner's decision of 2026-09-19 removed them from the screens entirely; this is
 * what fills the gap, so nobody is asked to invent a value they will never see again.
 *
 * **Derived once, at creation, and never again.** A code is a join key: `library/dishes.yaml` and
 * every M04 recipe find a dish by it. If the code followed the name, the first time somebody fixed
 * a spelling — "Garlic Nan" to "Garlic Naan" — the dish would silently detach from its recipe.
 * Renaming must not call this.
 *
 * **Transliterated rather than dropped.** `docs/ui/conventions.md` puts Hindi and Marathi in scope,
 * and a generator that returned an empty string for a Devanagari name would collide on every such
 * dish. Anything outside A–Z and 0–9 that has no ASCII form becomes a separator, and a name with
 * no usable characters at all falls back to a readable prefix rather than to nothing.
 */

/** Non-ASCII letters that carry an obvious ASCII form; everything else falls through to stripping. */
const FOLDED = new Map<string, string>([
  ['₹', 'RS'],
  ['&', 'AND'],
  ['%', 'PCT'],
]);

/** What a name becomes when it yields no usable characters — a Devanagari-only dish, say. */
const FALLBACK = 'ITEM';

/** Postgres and every screen that has ever shown one; long enough to stay readable. */
const MAX_LENGTH = 32;

/**
 * `"Veg Starters"` → `"VEG_STARTERS"`. Deterministic, so a re-seed reproduces the same code.
 *
 * Deterministic matters: `suffixed` below resolves a collision by counting, not by randomness, so
 * the same menu loaded twice produces the same codes both times.
 */
export function codeFromName(name: string): string {
  // `replace` with a callback rather than spreading the string: spreading splits by code point,
  // which eslint flags because it mishandles surrogate pairs — and this function is explicitly
  // meant to survive scripts outside the BMP.
  const folded = name.replace(/[₹&%]/g, (character) => FOLDED.get(character) ?? character)
    // Decompose accents and drop the combining marks, so "Café" gives CAFE rather than CAF.
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '');

  const code = folded
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, MAX_LENGTH)
    // A trailing separator can survive the slice.
    .replace(/_+$/g, '');

  return code === '' ? FALLBACK : code;
}

/**
 * The same code, made unique against the ones already in use.
 *
 * Two dishes may legitimately share a name — "Special" on two menus, a variant called "Full" under
 * every dish — and a code is unique per restaurant. Counting keeps it deterministic and keeps the
 * readable stem: `FULL`, then `FULL_2`, then `FULL_3`.
 */
export function suffixedCode(name: string, taken: Iterable<string>): string {
  const used = new Set(taken);
  const base = codeFromName(name);
  if (!used.has(base)) {
    return base;
  }
  // Leaves room for the suffix rather than overrunning the length a column allows.
  const stem = base.slice(0, MAX_LENGTH - 4).replace(/_+$/g, '');
  for (let n = 2; n < 1000; n += 1) {
    const candidate = `${stem}_${String(n)}`;
    if (!used.has(candidate)) {
      return candidate;
    }
  }
  // A thousand dishes of one name is not a menu; refusing beats looping forever.
  throw new Error(`cannot derive a unique code from "${name}"`);
}
