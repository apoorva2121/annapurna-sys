// The two rules the waste screen lives or dies by, checked by a machine.
//
// `docs/waste-model.md` states both and states them as consequences, not preferences:
//
// 1. **No cost before the waste is logged.** "Showing the rupee value *after* logging is good — it
//    teaches. Showing it before suppresses honest reporting." A figure on screen while somebody is
//    deciding what to record is a figure some people record towards, which is the same reason M07's
//    cash count and M06's goods-receipt weight are blind.
// 2. **Presets, not a number pad.** "quantity (with big preset buttons: ¼, ½, 1, 2)". Typing a
//    quantity one-handed in a kitchen is slow, and slow means it does not get logged.
//
// And one this codebase learned the hard way: **the screen never converts a unit.** A quantity
// divided by a thousand in a browser is the float round-trip invariant 3 forbids, and the defect
// behind that rule repriced cabbage to ₹40 per gram.
//
// Same shape as `brandChecklist.test.ts` and `kdsReadability.test.ts`: a rule that lives only in
// prose is a rule the next screen written in a hurry quietly skips.
import { describe, expect, it } from 'vitest';

const sources = import.meta.glob<string>('./screens/Waste*.tsx', {
  query: '?raw',
  import: 'default',
  eager: true,
});

const presets = import.meta.glob<string>('./screens/wastePresets.ts', {
  query: '?raw',
  import: 'default',
  eager: true,
});

function withoutComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1');
}

function screen(name: string): string {
  const found = Object.entries(sources).find(([path]) => path.endsWith(`/${name}.tsx`));
  expect(found, `${name} was not found — this test would otherwise pass vacuously`).toBeDefined();
  return withoutComments(found?.[1] ?? '');
}

describe('the waste screen keeps its two promises', () => {
  it('reads the screens it checks, so an empty parse cannot pass', () => {
    expect(Object.keys(sources).length).toBeGreaterThanOrEqual(2);
  });

  // Rule 1. The logging screen renders money in exactly one place: the confirmation after the
  // event comes back. Anywhere else is a figure shown while somebody is still deciding.
  it('shows no money on the logging screen until the waste is logged', () => {
    const code = screen('WasteScreen');
    const moneyCalls = [...code.matchAll(/formatINR\(/g)];

    expect(moneyCalls).toHaveLength(1);
    // And the one call sits inside the component that only exists once the server has answered.
    const logged = code.slice(code.indexOf('function Logged'));
    expect(logged).toContain('formatINR(');
  });

  it('never reads a cost off anything but the logged event', () => {
    const code = screen('WasteScreen');
    // `cost_value` is the only money field in this module, and the screen may touch it only on the
    // event it just created — never on an item, a batch or a reason.
    const reads = [...code.matchAll(/\.cost_value/g)];
    expect(reads.length).toBeLessThanOrEqual(1);
    if (reads.length === 1) {
      expect(code).toContain('event.cost_value');
    }
  });

  // Rule 2. Preset buttons and no free-text quantity: an `<input>` on this screen is somebody
  // typing a decimal point one-handed, which is where a quantity goes wrong by a factor of ten.
  it('offers presets rather than a box to type a quantity into', () => {
    const code = screen('WasteScreen');

    expect(code).toContain('PRESETS');
    expect(code).not.toMatch(/<input\b/);
    expect(code).not.toMatch(/<Field\b/);
  });

  it('keeps the four presets the waste model asks for', () => {
    const source = Object.values(presets)[0] ?? '';
    const listed = /PRESETS = \[([^\]]+)\]/.exec(withoutComments(source));

    expect(listed?.[1]).toContain("'0.25'");
    expect(listed?.[1]).toContain("'0.5'");
    expect(listed?.[1]).toContain("'1'");
    expect(listed?.[1]).toContain("'2'");
  });

  // The lesson from the ₹40-a-gram cabbage: the browser does no arithmetic on a quantity. It sends
  // what was tapped plus a flag saying which unit that is, and the server converts.
  it('does no unit arithmetic in the browser', () => {
    const code = screen('WasteScreen') + withoutComments(Object.values(presets)[0] ?? '');

    expect(code).toContain('perPurchaseUnit');
    // No multiplication or division anywhere near a quantity. `Number(` would be the other way in.
    expect(code).not.toMatch(/quantity\s*[*/]/);
    expect(code).not.toMatch(/[*/]\s*1000/);
    expect(code).not.toMatch(/Number\(/);
  });

  // The summary is the report the model exists for, and its whole point is that it is not one
  // number. A screen rendering only the total would be the thing `waste-model.md` calls useless.
  it('splits the summary by stage rather than showing one total', () => {
    const code = screen('WasteSummaryScreen');

    expect(code).toContain('summary.lines');
    expect(code).toContain('strings.waste.stage[line.stage]');
    expect(code).toContain('share_percent');
  });

  it('never recomputes a share or a total in the browser', () => {
    const code = screen('WasteSummaryScreen');

    // Every figure is the server's, rendered. Invariant 3: nothing on this screen adds two
    // numbers, and the shares add to a hundred precisely because they were computed once, in
    // Decimal, on the server.
    expect(code).not.toMatch(/reduce\(/);
    expect(code).not.toMatch(/Number\(/);
    expect(code).not.toMatch(/parseFloat\(/);
  });
});
