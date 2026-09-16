// Decision D24 (backlog-issues B12): "What uses this" opens under the item's own row, rather than in
// a panel below a long table where nobody sees it appear.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthContext, type AuthState } from '@staff/auth/AuthContext';
import { strings } from '@staff/strings';

import StockItemsScreen from './StockItemsScreen';

const ITEM = (id: string, code: string, name: string): Record<string, unknown> => ({
  id,
  kind: 'ingredient',
  code,
  name,
  base_unit: 'g',
  category: 'dairy',
  storage_type: 'chilled',
  is_active: true,
  ingredient: {
    purchase_unit: 'kg',
    purchase_to_base: '1000',
    yield_factor: '0.98',
    shelf_life_days: 4,
    reorder_level: null,
    reorder_quantity: null,
  },
  preparation: null,
});

const AUTH: AuthState = {
  session: null,
  signIn: () => Promise.resolve(),
  signOut: () => Promise.resolve(),
  can: () => false,
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('what uses an item', () => {
  it('opens under that item’s row', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) =>
        Promise.resolve(
          new Response(
            JSON.stringify(
              url.includes('used-by')
                ? { preparations: [], dishes: ['v1'], dish_names: ['Palak Paneer'] }
                : { items: [ITEM('s1', 'PANEER', 'Paneer'), ITEM('s2', 'ONION', 'Onion')], next_cursor: null },
            ),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
        ),
      ),
    );
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter>
          <AuthContext.Provider value={AUTH}>
            <StockItemsScreen />
          </AuthContext.Provider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const user = userEvent.setup();
    const paneerRow = (await screen.findByText('Paneer')).closest('tr');

    const buttons = screen.getAllByRole('button', { name: strings.stock.usedBy });
    await user.click(buttons[0] as HTMLElement);

    const dish = await screen.findByText('Palak Paneer');
    expect(dish.closest('tr')?.previousElementSibling).toBe(paneerRow);
    expect(buttons[0]).toHaveAttribute('aria-expanded', 'true');
  });
});
