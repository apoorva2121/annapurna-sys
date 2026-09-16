// The screen's job is to make a negative position impossible to miss, and impossible to misread.
//
// A negative on-hand figure means stock was consumed that nobody recorded receiving. For a
// restaurant that has never kept records that is not an edge case — `docs/onboarding-cold-start.md`
// says it is week one. So the screen has to do three things that a plain table would not: surface
// it above the fold, say what it means in words a manager can act on, and never call it an error,
// because the ledger is not broken and telling someone it is sends them to the wrong place.
//
// The other thing asserted here is that the screen never does arithmetic on a quantity. It renders
// the string the server sent and trusts the server's `is_negative` flag — parsing a quantity to a
// number to decide how to paint a row is one step from adding two of them, which is CLAUDE.md
// invariant 3.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import StockOnHandScreen from './StockOnHandScreen';

const ON_HAND = {
  items: [
    {
      stock_item_id: 's1',
      code: 'PANEER',
      name: 'Paneer',
      base_unit: 'g',
      quantity: '4400.0000',
      value: '1584.000000',
      is_negative: false,
    },
    {
      stock_item_id: 's2',
      code: 'ONION',
      name: 'Onion',
      // Consumed without a recorded delivery. The row this screen exists for.
      quantity: '-600.0000',
      base_unit: 'g',
      value: '-24.000000',
      is_negative: true,
    },
  ],
  negative_count: 1,
};

const EXPIRING = {
  batches: [
    {
      batch_id: 'b1',
      stock_item_id: 's1',
      code: 'PANEER',
      name: 'Paneer',
      base_unit: 'g',
      unit_cost: '0.360000',
      remaining: '500.0000',
      expiry_date: '2026-09-14',
    },
  ],
};

function json(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: () => Promise.resolve(body),
    headers: new Headers({ 'content-type': 'application/json' }),
  } as unknown as Response;
}

function renderScreen(onHand: unknown = ON_HAND): void {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: unknown) => {
      const url = String(input);
      if (url.includes('expiring')) return Promise.resolve(json(EXPIRING));
      if (url.includes('movements')) return Promise.resolve(json([]));
      return Promise.resolve(json(onHand));
    }),
  );
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <StockOnHandScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('stock on hand', () => {
  it('renders the quantity exactly as the server sent it', async () => {
    renderScreen();

    // Not "4400" and not "4,400" — the string, with its scale intact. The moment a screen
    // reformats a quantity it has parsed it, and the moment it has parsed it somebody will add two.
    expect(await screen.findByText(/4400\.0000/)).toBeInTheDocument();
  });

  it('leads with the negative rather than burying it in the table', async () => {
    renderScreen();

    const banner = await screen.findByRole('status');

    expect(banner).toHaveTextContent('1 item has been used without a recorded delivery');
  });

  it('tells a manager what to do about it, not merely that it happened', async () => {
    renderScreen();

    const banner = await screen.findByRole('status');

    // The remedy, in the banner. A count is the other way out, and saying so is the difference
    // between an alert somebody acts on and one they learn to scroll past.
    expect(banner).toHaveTextContent(/record the missing delivery/i);
    expect(banner).toHaveTextContent(/count the shelf/i);
  });

  it('never calls a negative position an error', async () => {
    // The ledger is not broken; the paperwork is behind. Those need different responses, and
    // "error" sends a manager to look for a bug that is not there.
    renderScreen();

    const banner = await screen.findByRole('status');

    expect(banner.textContent ?? '').not.toMatch(/error|failed|wrong/i);
  });

  it('marks the negative row with a word, not only a colour', async () => {
    // docs/ui/conventions.md rule 5. Commercial kitchens are full of steamed-up screens and
    // colour-blind men, and this is a row somebody has to act on.
    renderScreen();

    expect(await screen.findByText('No delivery recorded')).toBeInTheDocument();
  });

  it('shows no banner when nothing is negative', async () => {
    renderScreen({ items: [ON_HAND.items[0]], negative_count: 0 });

    await screen.findByText(/4400\.0000/);

    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('says what is expiring rather than leaving the section blank', async () => {
    renderScreen();

    await waitFor(() => {
      expect(screen.getByText(/2026-09-14/)).toBeInTheDocument();
    });
  });
});

// Owner defect sheet row 26, decision D24 (backlog-issues B12).
describe('expiring stock', () => {
  it('names the item that is expiring', async () => {
    renderScreen();

    const section = (await screen.findByRole('heading', { name: /expiring/i })).closest('section');
    expect(await within(section as HTMLElement).findByText('Paneer')).toBeInTheDocument();
  });

  it('shows the expiry in the item’s own row', async () => {
    renderScreen();

    // The row is looked up inside waitFor, not before it. "Paneer" appears in the expiring list
    // above the table as well, so findAllByText resolves on that one while the table is still
    // pending — capturing the row once would pin it to undefined and retry forever.
    await waitFor(() => {
      const row = screen
        .getAllByText('Paneer')
        .map((element) => element.closest('tr'))
        .find((element) => element !== null);
      expect(row).toBeDefined();
      expect(within(row as HTMLElement).getByText('Expires 2026-09-14')).toBeInTheDocument();
    });
  });
});
