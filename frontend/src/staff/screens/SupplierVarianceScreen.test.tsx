// The report the module exists for, and the two things that make it readable.
//
// **The headline is a sentence.** A manager who reads one line of this screen should still learn
// the thing worth knowing — "Sharma Traders: 3 deliveries, ₹126.00 billed and not delivered" —
// because a table of quantities is something people mean to come back to and do not.
//
// **A clean supplier gets a sentence too.** An empty table is ambiguous between "they delivered
// everything" and "this report is broken", and `docs/ui/conventions.md` requires an empty state
// that explains.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import SupplierVarianceScreen from './SupplierVarianceScreen';

const ROW = {
  stock_item_id: 'i1',
  code: 'PANEER',
  name: 'Paneer',
  base_unit: 'g',
  deliveries: 3,
  invoiced: '30000.0000',
  received: '27000.0000',
  rejected: '0.0000',
  short_delivery: '3000.0000',
  short_delivery_value: '126.00',
};

function report(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    supplier_id: 's1',
    supplier_name: 'Sharma Traders',
    start: '2026-06-15',
    end: '2026-09-13',
    deliveries: 3,
    invoiced: '30000.0000',
    received: '27000.0000',
    short_delivery_value: '126.00',
    rows: [ROW],
    ...overrides,
  };
}

function json(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: () => Promise.resolve(body),
    headers: new Headers({ 'content-type': 'application/json' }),
  } as unknown as Response;
}

function renderScreen(body: Record<string, unknown>): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(json(body))),
  );
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/purchasing/suppliers/s1/variance']}>
        <Routes>
          <Route
            path="/purchasing/suppliers/:supplierId/variance"
            element={<SupplierVarianceScreen />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('a supplier delivery record', () => {
  it('says the thing worth knowing in one sentence, above the table', async () => {
    renderScreen(report());

    const headline = await screen.findByRole('status');
    expect(headline).toHaveTextContent('Sharma Traders');
    expect(headline).toHaveTextContent('3 deliveries');
    expect(headline).toHaveTextContent('₹126.00');
  });

  it('tells an honest supplier apart from a broken report', async () => {
    // Zero owed, but deliveries happened. "They delivered everything they billed for" is
    // information; a blank screen is not.
    renderScreen(report({ short_delivery_value: '0.00' }));

    const headline = await screen.findByRole('status');
    expect(headline).toHaveTextContent('delivered everything they billed for');
  });

  it('explains an empty period instead of showing a bare nothing', async () => {
    renderScreen(report({ rows: [], deliveries: 0, short_delivery_value: '0.00' }));

    expect(await screen.findByText(/No deliveries from this supplier/)).toBeInTheDocument();
    // And no headline at all: there is nothing to be pleased or worried about yet.
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('shows billed and arrived as two separate columns', async () => {
    // The whole module in one assertion. If these ever collapse into one column, the report is
    // decoration.
    renderScreen(report());

    expect(await screen.findByText('Billed')).toBeInTheDocument();
    expect(screen.getByText('Arrived')).toBeInTheDocument();
    expect(screen.getByText(/30000\.0000/)).toBeInTheDocument();
    expect(screen.getByText(/27000\.0000/)).toBeInTheDocument();
  });

  it('names the window it is reporting on', async () => {
    // Business days, not calendar days (`docs/ui/conventions.md`): a delivery booked at 01:30
    // belongs to the previous business day, and a report that disagreed with the ledger about
    // which would be quietly wrong at both ends.
    renderScreen(report());

    expect(await screen.findByText(/Business days: 2026-06-15/)).toBeInTheDocument();
  });
});
