// The waiter's first screen, and the things that make it worth having.
//
// **Status is a word, never only a colour.** A dim room and a colour-blind waiter are both ordinary,
// so every table says "Free" or "Occupied" in text, and a table whose bill was asked for says so.
//
// **One tap into a table.** A free table opens a dine-in order for exactly that table and goes
// straight to order taking — no form in between.
//
// **A table being cleared is not a free table** (backlog-issues B2). In the M07 manual pass, tapping
// a settled table to clear it opened an empty order that held it Occupied. Now it counts down, offers
// Mark ready, and opens nothing; and busy mode is a switch only for whoever holds `floor.manage`.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthContext, type AuthState } from '@staff/auth/AuthContext';
import type { RestaurantSummary, Session } from '@staff/auth/session';

import TableMapScreen from './TableMapScreen';

const RESTAURANT: RestaurantSummary = {
  id: 'r1',
  name: 'Spice Garden',
  code: 'SG',
  timezone: 'Asia/Kolkata',
  currency: 'INR',
  business_day_start: '05:00:00',
  theme: { default: null, schedule: [] },
};

function floor(busy = false): Record<string, unknown> {
  return {
    busy,
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
            ready_at: null,
            orders: [
              {
                id: 'o1',
                order_number: '7',
                status: 'sent',
                grand_total: '987.00',
                first_sent_at: '2026-09-13T12:05:00Z',
                bill_requested_at: '2026-09-13T12:50:00Z',
                version: 5,
                waiter_name: 'Suresh Patil',
              },
            ],
          },
          { id: 't7', code: 'T7', seats: 2, status: 'free', ready_at: null, orders: [] },
          {
            id: 't8',
            code: 'T8',
            seats: 4,
            status: 'cleaning',
            // Four minutes from now, give or take the test's own runtime.
            ready_at: new Date(Date.now() + 4 * 60_000 - 1_000).toISOString(),
            orders: [],
          },
        ],
      },
    ],
  };
}

// Who the server says can take orders here (`GET /staff/waiters`), sorted by name.
const WAITERS = {
  items: [
    { id: 'e2', full_name: 'Kavita Rane', employee_code: 'EMP012' },
    { id: 'e1', full_name: 'Suresh Patil', employee_code: 'EMP009' },
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

function authFor(permissions: string[]): AuthState {
  const held = new Set(permissions);
  return {
    session: {
      employeeId: 'e1',
      passwordChangeRequired: false,
      fullName: 'Asha',
      employeeCode: 'E001',
      restaurant: RESTAURANT,
      restaurants: [RESTAURANT],
      hasMoreRestaurants: false,
      roles: [],
      permissions: held,
    } satisfies Session,
    signIn: () => Promise.resolve(),
    signOut: () => Promise.resolve(),
    can: (permission: string) => held.has(permission),
  };
}

// What each POST answers, by the end of its URL. A table rather than an if-chain, so adding a route
// to this fake server does not add a branch to the function that serves them.
const POST_ANSWERS: [suffix: string, body: unknown, status: number][] = [
  ['/staff/orders', { id: 'o9', version: 1, lines: [] }, 201],
  ['/staff/floor/busy', { busy: true }, 200],
  ['/ready', { id: 't8', code: 'T8', seats: 4, status: 'free', ready_at: null, orders: [] }, 200],
];

function renderScreen({
  busy = false,
  permissions = ['order.create'],
}: { busy?: boolean; permissions?: string[] } = {}): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn((input: unknown, init?: RequestInit) => {
    const url = String(input);
    if (init?.method === 'POST') {
      const answer = POST_ANSWERS.find(([suffix]) => url.endsWith(suffix));
      return Promise.resolve(json(answer?.[1] ?? {}, answer?.[2] ?? 200));
    }
    if (url.endsWith('/staff/waiters')) return Promise.resolve(json(WAITERS));
    return Promise.resolve(json(url.endsWith('/staff/floor') ? floor(busy) : {}));
  });
  vi.stubGlobal('fetch', fetchMock);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <AuthContext.Provider value={authFor(permissions)}>
        <MemoryRouter initialEntries={['/floor']}>
          <Routes>
            <Route path="/floor" element={<TableMapScreen />} />
            <Route path="/orders/:orderId" element={<p>order taking</p>} />
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>
    </QueryClientProvider>,
  );
  return fetchMock;
}

function posts(fetchMock: ReturnType<typeof vi.fn>): [string, Record<string, unknown>][] {
  return fetchMock.mock.calls
    .filter(([, init]) => (init as RequestInit | undefined)?.method === 'POST')
    .map(([input, init]) => [
      String(input),
      JSON.parse(((init as RequestInit).body as string | undefined) ?? '{}') as Record<
        string,
        unknown
      >,
    ]);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('TableMapScreen', () => {
  it('says what is happening at each table in words, not only colour', async () => {
    renderScreen();

    expect(await screen.findByText('Occupied')).toBeInTheDocument();
    expect(screen.getByText('Order 7')).toBeInTheDocument();
    expect(screen.getByText('Suresh Patil')).toBeInTheDocument();
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
    const [, body] = posts(fetchMock)[0] ?? ['', {}];
    expect(body).toEqual({ type: 'dine_in', table_ids: ['t7'] });
  });
});

describe('a table being cleared', () => {
  it('says so, counts down, and offers Mark ready instead of opening an order', async () => {
    const fetchMock = renderScreen();
    const user = userEvent.setup();

    expect(await screen.findByText('Being cleared')).toBeInTheDocument();
    expect(screen.getByText('Ready in 4 min')).toBeInTheDocument();
    // The cell itself is not a button: tapping the dirty table cannot open an order on it.
    expect(screen.queryByRole('button', { name: /^T8/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Mark T8 ready' }));

    await waitFor(() => {
      expect(posts(fetchMock).map(([url]) => url)).toEqual([
        expect.stringMatching(/\/staff\/floor\/tables\/t8\/ready$/) as unknown as string,
      ]);
    });
  });
});

describe('busy mode', () => {
  it('is not a switch for a waiter, who only reads that it is on', async () => {
    renderScreen({ busy: true, permissions: ['order.create'] });

    expect(await screen.findByText('Busy mode on')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Busy mode/ })).not.toBeInTheDocument();
  });

  it('is switched on from the floor by whoever holds floor.manage', async () => {
    const fetchMock = renderScreen({ permissions: ['order.create', 'floor.manage'] });
    const user = userEvent.setup();

    const toggle = await screen.findByRole('button', { name: 'Busy mode off' });
    expect(toggle).toHaveAttribute('aria-pressed', 'false');
    await user.click(toggle);

    await waitFor(() => {
      expect(posts(fetchMock)).toEqual([
        [expect.stringMatching(/\/staff\/floor\/busy$/) as unknown as string, { on: true }],
      ]);
    });
  });
});

// Who is serving a table (2026-09-14). A waiter who opens a table serves it — still one tap. Anyone
// who holds order.assign is asked who is serving it first, because the person seating a table is
// often not the person who will serve it, and was being credited with it.
describe('who is serving a table', () => {
  it('asks a manager who is serving a free table, and opens it in that name', async () => {
    const fetchMock = renderScreen({ permissions: ['order.create', 'order.assign'] });
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: /T7/ }));
    expect(await screen.findByText('Who is serving T7?')).toBeInTheDocument();
    await user.click(await screen.findByRole('button', { name: 'Kavita Rane' }));

    expect(await screen.findByText('order taking')).toBeInTheDocument();
    const [, body] = posts(fetchMock)[0] ?? ['', {}];
    expect(body).toEqual({ type: 'dine_in', table_ids: ['t7'], waiter_employee_id: 'e2' });
  });

  it('lets a manager open a table that nobody is serving yet', async () => {
    const fetchMock = renderScreen({ permissions: ['order.create', 'order.assign'] });
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: /T7/ }));
    await user.click(await screen.findByRole('button', { name: 'Leave unassigned' }));

    expect(await screen.findByText('order taking')).toBeInTheDocument();
    const [, body] = posts(fetchMock)[0] ?? ['', {}];
    expect(body).toEqual({ type: 'dine_in', table_ids: ['t7'] });
  });
});
