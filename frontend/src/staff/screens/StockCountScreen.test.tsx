// The count screen's job is to keep two things impossible to misunderstand.
//
// First, that **submitting is not the end**. A submitted count is a worksheet; approval is what
// moves the ledger. A manager who believed submitting finished it would wonder, days later, why the
// position never corrected — and would conclude the product does not work.
//
// Second, that **self-approval is refused for a reason**. The screen deliberately offers the button
// and shows the server's refusal rather than hiding the control based on a guess about who counted.
// Hiding it teaches "this button is unavailable"; showing the refusal teaches "a count needs a
// second pair of eyes", which is the actual rule and the one worth learning.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import StockCountScreen from './StockCountScreen';

const ITEMS = {
  items: [{ id: 's1', code: 'PANEER', name: 'Paneer', base_unit: 'g', kind: 'ingredient' }],
};

function countWith(status: 'draft' | 'submitted' | 'approved') {
  return {
    counts: [
      {
        id: 'c1',
        counted_at: '2026-09-12T10:00:00Z',
        business_date: '2026-09-12',
        scope: 'full',
        status,
        counted_by: 'e1',
        approved_by: null,
        lines: [
          {
            stock_item_id: 's1',
            system_quantity: '1000.0000',
            counted_quantity: '940.0000',
            variance_value: '-21.60',
            reason: null,
          },
        ],
      },
    ],
  };
}

function json(body: unknown, status = 200): Response {
  return {
    ok: status < 400,
    status,
    json: () => Promise.resolve(body),
    headers: new Headers({ 'content-type': 'application/json' }),
  } as unknown as Response;
}

function renderScreen(counts: unknown, onApprove?: () => Response): void {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: unknown) => {
      const url = String(input);
      if (url.includes('approve') && onApprove) return Promise.resolve(onApprove());
      if (url.includes('stock-items')) return Promise.resolve(json(ITEMS));
      return Promise.resolve(json(counts));
    }),
  );
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <StockCountScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the stock count screen', () => {
  it('shows the variance in rupees, not only in quantities', async () => {
    // The leakage number is the thing this module exists to surface. A sheet showing only
    // quantities would leave somebody to do the arithmetic the product is for.
    renderScreen(countWith('draft'));

    expect(await screen.findByText(/₹.*21\.60/)).toBeInTheDocument();
  });

  it('says a submitted count is still waiting, not done', async () => {
    renderScreen(countWith('submitted'));

    expect(await screen.findByText('Waiting for approval')).toBeInTheDocument();
  });

  it('explains that approving is what corrects the ledger', async () => {
    renderScreen(countWith('submitted'));

    expect(
      await screen.findByText(/Approving posts a correction for every line that differs/),
    ).toBeInTheDocument();
    expect(screen.getByText(/somebody other than the person who counted/)).toBeInTheDocument();
  });

  it('offers no approve button while the count is still being written', async () => {
    renderScreen(countWith('draft'));

    await screen.findByText('Being counted');

    expect(
      screen.queryByRole('button', { name: /Approve, and correct the ledger/ }),
    ).not.toBeInTheDocument();
  });

  it('shows the server’s own words when approval is refused', async () => {
    // Not a generic "that failed". The refusal explains the rule, and that sentence is the only
    // part worth reading.
    renderScreen(countWith('submitted'), () =>
      json(
        {
          code: 'self_approval',
          message: 'A count must be approved by somebody other than the person who counted it.',
          details: {},
        },
        403,
      ),
    );

    await userEvent.click(
      await screen.findByRole('button', { name: /Approve, and correct the ledger/ }),
    );

    await waitFor(() => {
      expect(
        screen.getByText(
          'A count must be approved by somebody other than the person who counted it.',
        ),
      ).toBeInTheDocument();
    });
  });

  it('does not offer a second count while one is still open', async () => {
    // Two open sheets over the same shelf is how one of them gets approved and the other silently
    // corrects the same variance twice.
    renderScreen(countWith('draft'));

    await screen.findByText('Being counted');

    expect(screen.queryByRole('button', { name: 'Start a count' })).not.toBeInTheDocument();
  });

  it('offers a new count when none is open', async () => {
    renderScreen({ counts: [] });

    expect(await screen.findByRole('button', { name: 'Start a count' })).toBeInTheDocument();
  });
});
