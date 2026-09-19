// The generator that replaced a field people used to type.
//
// The rule that matters most is not tested here because it cannot be: **a code is derived once, at
// creation, and never on rename.** That is a property of the screens that call this, and
// `menuDiscipline.test.ts` holds it by checking that no update path calls the generator.
import { describe, expect, it } from 'vitest';

import { codeFromName, suffixedCode } from '@staff/codeFromName';

describe('codeFromName', () => {
  it('turns a name into the code a person used to type by hand', () => {
    // Exactly what the old uppercase-and-underscore nudge produced, so existing seeds still match.
    expect(codeFromName('Veg Starters')).toBe('VEG_STARTERS');
    expect(codeFromName('Garlic Naan')).toBe('GARLIC_NAAN');
    expect(codeFromName('chilli paneer')).toBe('CHILLI_PANEER');
  });

  it('collapses punctuation rather than carrying it into a join key', () => {
    expect(codeFromName('Paneer Tikka (Half)')).toBe('PANEER_TIKKA_HALF');
    expect(codeFromName('  Dal   Makhani  ')).toBe('DAL_MAKHANI');
    expect(codeFromName('Veg / Non-veg')).toBe('VEG_NON_VEG');
  });

  it('keeps accented letters readable instead of dropping them', () => {
    // "CAF" would be a different dish from "CAFE" to anybody reading the export.
    expect(codeFromName('Café Mocha')).toBe('CAFE_MOCHA');
  });

  it('spells out the symbols an Indian menu actually contains', () => {
    expect(codeFromName('Rice & Dal')).toBe('RICE_AND_DAL');
    expect(codeFromName('₹99 Thali')).toBe('RS99_THALI');
  });

  it('falls back rather than returning nothing for a name it cannot transliterate', () => {
    // Hindi and Marathi are in scope (docs/ui/conventions.md). An empty code would make every
    // Devanagari dish collide with every other one — the failure this fallback exists to avoid.
    expect(codeFromName('दाल मखनी')).toBe('ITEM');
    expect(codeFromName('!!!')).toBe('ITEM');
  });

  it('is deterministic, so a re-seed reproduces the same code', () => {
    expect(codeFromName('Butter Chicken')).toBe(codeFromName('Butter Chicken'));
  });

  it('stays within the length a column and a screen can hold', () => {
    const code = codeFromName('A very long dish name that somebody typed without thinking at all');
    expect(code.length).toBeLessThanOrEqual(32);
    expect(code.endsWith('_')).toBe(false);
  });
});

describe('suffixedCode', () => {
  it('leaves a free code alone', () => {
    expect(suffixedCode('Full', [])).toBe('FULL');
  });

  it('counts rather than randomises, so the same menu loads the same way twice', () => {
    expect(suffixedCode('Full', ['FULL'])).toBe('FULL_2');
    expect(suffixedCode('Full', ['FULL', 'FULL_2'])).toBe('FULL_3');
  });

  it('makes room for the suffix instead of overrunning the length', () => {
    const taken = [codeFromName('A very long dish name that somebody typed without thinking')];
    const next = suffixedCode('A very long dish name that somebody typed without thinking', taken);
    expect(next.length).toBeLessThanOrEqual(32);
    expect(next).not.toBe(taken[0]);
  });

  it('refuses rather than looping when a name is hopeless', () => {
    const taken = ['FULL', ...Array.from({ length: 1000 }, (_, n) => `FULL_${String(n + 2)}`)];
    expect(() => suffixedCode('Full', taken)).toThrow(/unique code/);
  });
});
