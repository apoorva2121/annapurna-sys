// The waiter's first screen, and the two things that make it worth having.
//
// **Status is a word, never only a colour.** A dim room and a colour-blind waiter are both ordinary,
// so every table says "Free" or "Occupied" in text, and a table whose bill was asked for says so.
//
// **One tap into a table.** A free table opens a dine-in order for exactly that table and goes
// straight to order taking — no form in between.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import TableMapScreen from './TableMapScreen';

const FLOOR = {
  areas: [
    {
      id: 'a1',
      name: 'Hall',
      tables: [
        {
          id: 't6',
          code: 'T6',
          seats: 4,
          status: 'occupied',
          orders: [
            {
              id: 'o1',
              order_number: '7',
              status: 'sent',
              grand_total: '987.00',
              first_sent_at: '2026-09-13T12:05:00Z',
              bill_requested_at: '2026-09-13T12:50:00Z',
              version: 5,
            },
          ],
        },
        { id: 't7', code: 'T7', seats: 2, status: 'free', orders: [] },
      ],
    },
  ],
};

function json(body: unknown, status = 200): Response {
  return {
    ok: status < 400,
    status,
    json: () => Promise.resolve(body),
    headers: new Headers({ 'content-type': 'application/json' }),
  } as unknown as Response;
}

function renderScreen(): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn((input: unknown, init?: RequestInit) => {
    const url = String(input);
    if (init?.method === 'POST' && url.endsWith('/staff/orders')) {
      return Promise.resolve(json({ id: 'o9', version: 1, lines: [] }, 201));
    }
    if (url.endsWith('/staff/floor')) return Promise.resolve(json(FLOOR));
    return Promise.resolve(json({}));
  });
  vi.stubGlobal('fetch', fetchMock);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/floor']}>
        <Routes>
          <Route path="/floor" element={<TableMapScreen />} />
          <Route path="/orders/:orderId" element={<p>order taking</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('TableMapScreen', () => {
  it('says what is happening at each table in words, not only colour', async () => {
    renderScreen();

    expect(await screen.findByText('Occupied')).toBeInTheDocument();
    expect(screen.getByText('Order 7')).toBeInTheDocument();
    expect(screen.getByText('₹987.00')).toBeInTheDocument();
    expect(screen.getByText('Bill asked for')).toBeInTheDocument();
    expect(screen.getByText('Free')).toBeInTheDocument();
    expect(screen.getByText('2 seats')).toBeInTheDocument();
  });

  it('opens a dine-in order for a free table in one tap and goes straight to it', async () => {
    const fetchMock = renderScreen();
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: /T7/ }));

    expect(await screen.findByText('order taking')).toBeInTheDocument();
    const post = fetchMock.mock.calls.find(
      ([, init]) => (init as RequestInit | undefined)?.method === 'POST',
    );
    const body = JSON.parse((post?.[1] as RequestInit).body as string) as Record<string, unknown>;
    expect(body).toEqual({ type: 'dine_in', table_ids: ['t7'] });
  });
});
