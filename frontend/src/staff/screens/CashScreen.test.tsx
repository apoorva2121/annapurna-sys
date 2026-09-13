// The till, and the three things this screen must not do.
//
// **It must not show what the till should hold while somebody is counting it.** A figure to aim at
// is a figure some people count towards; expected cash and the variance appear after the count.
//
// **It must not work anything out.** What it sends is what somebody counted or handed over; "short"
// and "over" are read from the sign of the server's variance.
//
// **It must not let a shortfall be tidied away.** An adjusted till still shows the original variance.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import CashScreen from './CashScreen';

const OPEN_TILL = {
  id: 'till1',
  status: 'open',
  opened_at: '2026-09-13T06:00:00Z',
  opened_by: 'e2',
  opening_float: '2000.00',
  business_date: '2026-09-13',
  closed_at: null,
  closed_by: null,
  counted_cash: null,
  variance: null,
  cash_taken: '3530.00',
  payouts: '300.00',
  adjustments: '0.00',
  expected_cash: '5230.00',
  adjusted_variance: null,
};

const CLOSED_TILL = {
  ...OPEN_TILL,
  status: 'closed',
  closed_at: '2026-09-13T23:00:00Z',
  closed_by: 'e2',
  counted_cash: '4830.00',
  variance: '-400.00',
  adjusted_variance: '-400.00',
  counts: [],
  movements: [],
};

function json(body: unknown, status = 200): Response {
  return {
    ok: status < 400,
    status,
    json: () => Promise.resolve(body),
    headers: new Headers({ 'content-type': 'application/json' }),
  } as unknown as Response;
}

function renderScreen(
  tills: Record<string, unknown>[],
  nextCursor: string | null = null,
): ReturnType<typeof vi.fn> {
  let current = tills;
  const fetchMock = vi.fn((input: unknown, init?: RequestInit) => {
    const url = String(input);
    if (init?.method === 'POST' && url.endsWith('/close')) {
      current = [CLOSED_TILL];
      return Promise.resolve(json(CLOSED_TILL));
    }
    if (init?.method === 'POST') {
      return Promise.resolve(json({ ...OPEN_TILL, counts: [], movements: [] }, 201));
    }
    if (url.endsWith('/staff/cash/sessions')) {
      return Promise.resolve(json({ items: current, next_cursor: nextCursor }));
    }
    return Promise.resolve(json({}));
  });
  vi.stubGlobal('fetch', fetchMock);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <CashScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

function postTo(fetchMock: ReturnType<typeof vi.fn>, suffix: string): RequestInit | undefined {
  const call = fetchMock.mock.calls.find(
    ([input, init]) =>
      (init as RequestInit | undefined)?.method === 'POST' && String(input).endsWith(suffix),
  );
  return call?.[1] as RequestInit | undefined;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('CashScreen', () => {
  it('with no till open, opens one with the float counted into the drawer', async () => {
    const fetchMock = renderScreen([]);
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText('Opening float'), '2000');
    await user.click(screen.getByRole('button', { name: 'Open the till' }));

    expect(JSON.parse(postTo(fetchMock, '/staff/cash/sessions')?.body as string)).toEqual({
      opening_float: '2000.00',
    });
  });

  it('shows an open till’s float and payouts, but not what it should hold', async () => {
    renderScreen([OPEN_TILL]);

    expect(await screen.findByText('₹2,000.00')).toBeInTheDocument();
    expect(screen.getByText('₹300.00')).toBeInTheDocument();
    expect(screen.queryByText('₹5,230.00')).not.toBeInTheDocument();
    expect(screen.queryByText('₹3,530.00')).not.toBeInTheDocument();
  });

  it('records a payout with a reason, behind an idempotency key', async () => {
    const fetchMock = renderScreen([OPEN_TILL]);
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText('Amount paid out'), '300');
    await user.type(screen.getAllByLabelText('Reason')[0] as HTMLElement, 'Vegetable seller');
    await user.click(screen.getByRole('button', { name: 'Record payout' }));

    expect(await screen.findByText('Payout recorded')).toBeInTheDocument();
    const init = postTo(fetchMock, '/till1/payouts');
    expect(JSON.parse(init?.body as string)).toEqual({
      amount: '300.00',
      reason: 'Vegetable seller',
    });
    expect((init?.headers as Record<string, string>)['Idempotency-Key']).toMatch(/^[0-9a-f-]{36}$/);
  });

  it('closes with a count per denomination, then says what the till was short by', async () => {
    const fetchMock = renderScreen([OPEN_TILL]);
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText('How many ₹500'), '9');
    await user.type(screen.getByLabelText('How many ₹100'), '3');
    await user.click(screen.getByRole('button', { name: 'Close the till' }));

    expect(await screen.findByText('Till closed')).toBeInTheDocument();
    expect(screen.getAllByText(/Short by ₹400\.00/).length).toBeGreaterThan(0);
    expect(JSON.parse(postTo(fetchMock, '/till1/close')?.body as string)).toEqual({
      counts: [
        { denomination: '500.00', quantity: 9 },
        { denomination: '100.00', quantity: 3 },
      ],
    });
  });

  it('refuses a count that is not a whole number before sending anything', async () => {
    const fetchMock = renderScreen([OPEN_TILL]);
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText('How many ₹500'), '2.5');
    await user.click(screen.getByRole('button', { name: 'Close the till' }));

    expect(
      await screen.findByText('The count of ₹500 must be a whole number.'),
    ).toBeInTheDocument();
    expect(postTo(fetchMock, '/till1/close')).toBeUndefined();
  });

  it('says older tills are not shown, rather than letting the list look complete', async () => {
    renderScreen([CLOSED_TILL], 'till0');

    expect(await screen.findByText('Older tills are not shown here.')).toBeInTheDocument();
  });

  it('keeps the original shortfall beside the adjusted one, and sends a signed adjustment', async () => {
    const adjusted = { ...CLOSED_TILL, adjustments: '400.00', adjusted_variance: '0.00' };
    const fetchMock = renderScreen([adjusted]);
    const user = userEvent.setup();

    expect(await screen.findByText('Short by ₹400.00')).toBeInTheDocument();
    expect(screen.getByText('After adjustments: Exact')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Adjust this till' }));
    await user.type(screen.getByLabelText('Amount (minus for missing)'), '-50');
    await user.type(screen.getByLabelText('Reason'), 'Missing after the recount');
    await user.click(screen.getByRole('button', { name: 'Record adjustment' }));

    expect(JSON.parse(postTo(fetchMock, '/till1/adjustments')?.body as string)).toEqual({
      amount: '-50.00',
      reason: 'Missing after the recount',
    });
  });
});
