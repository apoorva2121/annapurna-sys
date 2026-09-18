// The reports hub, and the one thing about it that is a product decision rather than a layout.
//
// The P1 design gives `report.operational.view` to the owner, the manager, the store manager and
// the accountant, and `report.financial.view` to the owner and the accountant alone. A manager
// therefore has no way to the money — and the way this screen expresses that is by **not drawing
// the link at all**, rather than drawing a disabled one. A greyed-out door is an invitation to
// find out what is behind it, which is the same argument the route makes when it answers 403
// instead of a screen full of blanks.
//
// The figures themselves are the server's and are tested on the server (`test_reporting.py`,
// `test_reports_endpoints.py`). What is testable *here* is who is offered what.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AuthContext, type AuthState } from '@staff/auth/AuthContext';
import type { Session } from '@staff/auth/session';

import TodayScreen from './TodayScreen';

const TODAY = {
  business_date: '2026-09-18',
  revenue: { value: '18400.00', previous: '16000.00', change: '2400.00', change_percent: '15.00' },
  covers: { value: '64', previous: '58', change: '6', change_percent: '10.34' },
  open_orders: 3,
  average_rating: '4.30',
  ratings_counted: 12,
};

const RESTAURANT = {
  id: 'r1',
  name: 'Spice Garden',
  code: 'R1',
  timezone: 'Asia/Kolkata',
  theme: { default: null, schedule: [] },
};

function renderFor(permissions: string[]): void {
  const session = {
    employeeId: 'e1',
    passwordChangeRequired: false,
    fullName: 'Asha',
    employeeCode: 'E001',
    restaurant: RESTAURANT,
    restaurants: [RESTAURANT],
    hasMoreRestaurants: false,
    roles: [],
    permissions: new Set(permissions),
  } as unknown as Session;
  const state: AuthState = {
    session,
    signIn: async () => {},
    signOut: async () => {},
    can: (permission: string) => session.permissions.has(permission),
  };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const tree: ReactElement = (
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <AuthContext.Provider value={state}>
          <TodayScreen />
        </AuthContext.Provider>
      </QueryClientProvider>
    </MemoryRouter>
  );
  render(tree);
}

async function hrefs(): Promise<string[]> {
  await waitFor(() => {
    expect(screen.getAllByRole('link').length).toBeGreaterThan(0);
  });
  return screen
    .getAllByRole('link')
    .map((link) => link.getAttribute('href') ?? '')
    .sort();
}

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(
      () =>
        new Response(JSON.stringify(TODAY), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
    ),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the reports hub', () => {
  it('offers a manager the operations and no way to the money', async () => {
    renderFor(['report.operational.view']);

    expect(await hrefs()).toEqual(['/reports/dishes', '/reports/waste']);
  });

  it('offers an owner all four', async () => {
    renderFor(['report.operational.view', 'report.financial.view']);

    expect(await hrefs()).toEqual([
      '/reports/dishes',
      '/reports/sales',
      '/reports/variance',
      '/reports/waste',
    ]);
  });

  it('says which business day it is answering about', async () => {
    // Invariant 4: a restaurant's day starts at five in the morning, so "today" here and "today"
    // on the phone in somebody's hand are different dates at 2am. The screen names the one it
    // means rather than leaving somebody to wonder why 2am is on yesterday.
    renderFor(['report.operational.view']);

    expect(await screen.findByText(/2026-09-18/)).toBeTruthy();
  });

  it('says how many ratings the average is of', async () => {
    // A 4.3 from twelve people and a 4.3 from one are different facts, and only one of them is
    // worth acting on.
    renderFor(['report.operational.view']);

    expect(await screen.findByText(/From 12 ratings/)).toBeTruthy();
  });
});
