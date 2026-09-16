import { render } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { WaiterSurface } from './WaiterSurface';

afterEach(() => {
  delete document.body.dataset.surface;
});

describe('WaiterSurface', () => {
  it('puts the page on the waiter surface while mounted, and puts back what was there', () => {
    // The staff app starts on the manager surface; a waiter screen needs 48 px targets, and leaving
    // it must not strand the next screen on them.
    document.body.dataset.surface = 'manager';

    const { unmount } = render(
      <WaiterSurface>
        <p>tables</p>
      </WaiterSurface>,
    );
    expect(document.body.dataset.surface).toBe('waiter');

    unmount();
    expect(document.body.dataset.surface).toBe('manager');
  });
});
