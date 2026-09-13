// Today's bills, and the two ways a list like this goes wrong.
//
// **"Today" in the wrong calendar.** At 01:30 the browser's today is tomorrow, but the restaurant is
// still trading on last night's business day (CLAUDE.md invariant 4). A manager crediting a bill
// settled at 01:00 must find it under the evening it belongs to.
//
// **A list that stops without saying so.** A full page offers the next one.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthContext, type AuthState } from '@staff/auth/AuthContext';
import type { RestaurantSummary, Session } from '@staff/auth/session';

import BillsScreen from './BillsScreen';

const RESTAURANT: RestaurantSummary = {
  id: 'r1',
  name: 'Spice Garden',
  code: 'SG',
  timezone: 'Asia/Kolkata',
  currency: 'INR',
  business_day_start: '05:00:00',
  theme: { default: null, schedule: [] },
};

const AUTH: AuthState = {
  session: {
    employeeId: 'e2',
    passwordChangeRequired: false,
    fullName: 'Arjun Mehta',
    employeeCode: 'EMP002',
    restaurant: RESTAURANT,
    restaurants: [RESTAURANT],
    hasMoreRestaurants: false,
    roles: ['manager'],
    permissions: new Set<string>(),
  } satisfies Session,
  signIn: () => Promise.resolve(),
  signOut: () => Promise.resolve(),
  can: () => true,
};

function bill(
  id: string,
  orderNumber: string,
  status: string,
  total: string,
): Record<string, unknown> {
  return {
    id,
    order_number: orderNumber,
    status,
    business_date: '2026-09-13',
    grand_total: total,
    version: 7,
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

function renderScreen(
  ...pages: { items: unknown[]; next_cursor: string | null }[]
): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn((input: unknown) => {
    const cursor = new URL(String(input), 'http://test').searchParams.get('cursor');
    const page = cursor === null ? pages[0] : pages[1];
    return Promise.resolve(json(page ?? { items: [], next_cursor: null }));
  });
  vi.stubGlobal('fetch', fetchMock);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AuthContext.Provider value={AUTH}>
          <BillsScreen />
        </AuthContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

function requested(fetchMock: ReturnType<typeof vi.fn>, call = 0): URLSearchParams {
  return new URL(String(fetchMock.mock.calls[call]?.[0]), 'http://test').searchParams;
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('BillsScreen', () => {
  it('lists settled and cancelled bills with their status in words', async () => {
    const fetchMock = renderScreen({
      items: [bill('o1', '7', 'settled', '987.00'), bill('o2', '8', 'voided', '470.00')],
      next_cursor: null,
    });

    expect(await screen.findByRole('link', { name: 'Order 7' })).toHaveAttribute(
      'href',
      '/bills/o1',
    );
    expect(screen.getByText('Settled')).toBeInTheDocument();
    expect(screen.getByText('Cancelled')).toBeInTheDocument();
    expect(screen.getByText('₹987.00')).toBeInTheDocument();
    expect(requested(fetchMock).getAll('status')).toEqual(['settled', 'voided']);
  });

  it('asks for the restaurant’s business day, so 01:30 is still last night', async () => {
    // 20:00 UTC on the 13th is 01:30 on the 14th in Kolkata, before the 05:00 day start.
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-09-13T20:00:00Z'));
    const fetchMock = renderScreen({ items: [], next_cursor: null });

    expect(await screen.findByText('No bills settled today yet.')).toBeInTheDocument();
    expect(requested(fetchMock).get('business_date')).toBe('2026-09-13');
  });

  it('offers the next page when the page was full, and asks for it by cursor', async () => {
    const fetchMock = renderScreen(
      { items: [bill('o1', '7', 'settled', '987.00')], next_cursor: 'o1' },
      { items: [bill('o3', '9', 'settled', '250.00')], next_cursor: null },
    );
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Next page' }));

    expect(await screen.findByRole('link', { name: 'Order 9' })).toBeInTheDocument();
    expect(requested(fetchMock, 1).get('cursor')).toBe('o1');
    expect(screen.getByRole('button', { name: 'Back to the first page' })).toBeInTheDocument();
  });
});
