import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { newKey, useIdempotencyKey } from '@shared/useIdempotencyKey';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('useIdempotencyKey', () => {
  it('keeps one key across renders until the submission succeeds and renews it', () => {
    const { result, rerender } = renderHook(() => useIdempotencyKey());
    const first = result.current.key;

    rerender();
    expect(result.current.key).toBe(first);

    act(() => {
      result.current.renew();
    });
    expect(result.current.key).not.toBe(first);
    expect(result.current.key).toMatch(UUID);
  });
});

describe('newKey', () => {
  it('still makes a UUID where randomUUID is unavailable, as on a LAN address over http', () => {
    const real = globalThis.crypto;
    vi.stubGlobal('crypto', {
      getRandomValues: <T extends ArrayBufferView>(array: T): T => real.getRandomValues(array),
    });

    const one = newKey();
    const two = newKey();

    expect(one).toMatch(UUID);
    expect(two).not.toBe(one);
  });
});
