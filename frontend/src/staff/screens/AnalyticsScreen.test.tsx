// What the trends screen must never say.
//
// Four of these come straight from decisions somebody already made and paid for:
//
// - **A bucket with no trading is a hole, not a zero.** The API sends `null` for a day the shop was
//   shut. Rendering it as ₹0.00 invents a catastrophic day, and on a chart it draws a line through
//   the floor — which is the failure this module exists to surface, not to manufacture.
// - **A branch with no dine-in guests has no spend per guest.** `null`, not zero: a zero would rank
//   a closed branch worst rather than unanswerable, and the endpoint deliberately sorts it last.
// - **Covers per trading day is shown beside spend per guest**, because the owner's chosen basis
//   has a recorded blind spot — a branch whose footfall collapsed but whose remaining guests spend
//   well looks healthy on spend alone.
// - **A figure opens the rows it came from, already filtered** (criterion 6), which means the
//   window travels in the URL rather than in memory.

import type { ReactElement } from 'react';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthContext, type AuthState } from '@staff/auth/AuthContext';
import type { RestaurantSummary, Session } from '@staff/auth/session';

import AnalyticsScreen from './AnalyticsScreen';

function restaurant(id: string, name: string): RestaurantSummary {
  return {
    id,
    name,
    code: name.slice(0, 2).toUpperCase(),
    timezone: 'Asia/Kolkata',
    currency: 'INR',
    business_day_start: '05:00:00',
    theme: { default: null, schedule: [] },
  };
}

const SPICE = restaurant('r1', 'Spice Garden');
const TANDOOR = restaurant('r2', 'Tandoor House');

function auth(restaurants: RestaurantSummary[]): AuthState {
  return {
    session: {
      employeeId: 'e1',
      passwordChangeRequired: false,
      fullName: 'Priya Nair',
      employeeCode: 'EMP001',
      restaurant: SPICE,
      restaurants,
      hasMoreRestaurants: false,
      roles: ['owner'],
      permissions: new Set<string>(),
      takesTables: false,
    } satisfies Session,
    signIn: () => Promise.resolve(),
    signOut: () => Promise.resolve(),
    can: () => true,
  };
}

const TREND = {
  metric: 'revenue',
  bucket: 'day',
  since: '2026-09-01',
  until: '2026-09-04',
  restaurant_ids: ['r1'],
  points: [
    { starts_on: '2026-09-01', ends_on: '2026-09-01', value: '18400.00', days_traded: 1 },
    // The day the restaurant was shut. Not a zero.
    { starts_on: '2026-09-02', ends_on: '2026-09-02', value: null, days_traded: 0 },
    { starts_on: '2026-09-03', ends_on: '2026-09-03', value: '21050.50', days_traded: 1 },
    { starts_on: '2026-09-04', ends_on: '2026-09-04', value: '19990.00', days_traded: 1 },
  ],
};

const BRANCHES = {
  since: '2026-09-01',
  until: '2026-09-04',
  branches: [
    {
      restaurant_id: 'r1',
      name: 'Spice Garden',
      revenue: '59440.50',
      dine_in_revenue: '44000.00',
      covers: 220,
      orders: 180,
      business_days_traded: 3,
      revenue_per_trading_day: '19813.50',
      spend_per_cover: '200.00',
    },
    {
      // Delivery only in this window: no covers, so no spend per guest. The trap decision 2
      // recorded — dividing total revenue by covers would have ranked this branch healthiest.
      restaurant_id: 'r2',
      name: 'Tandoor House',
      revenue: '31000.00',
      dine_in_revenue: '0.00',
      covers: 0,
      orders: 140,
      business_days_traded: 4,
      revenue_per_trading_day: '7750.00',
      spend_per_cover: null,
    },
  ],
  total_revenue: '90440.50',
  total_covers: 220,
  total_orders: 320,
  average_bill: '282.63',
};

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

function renderScreen(restaurants: RestaurantSummary[] = [SPICE, TANDOOR]): void {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: unknown) => {
      const url = String(input);
      return Promise.resolve(json(url.includes('/analytics/branches') ? BRANCHES : TREND));
    }),
  );
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <AuthContext.Provider value={auth(restaurants)}>
        <MemoryRouter initialEntries={['/analytics']}>
          <Routes>
            <Route path="/analytics" element={<AnalyticsScreen />} />
            {/* Where a drill-through lands. The test asserts the window arrives in the URL. */}
            <Route path="/reports/sales" element={<SalesStub />} />
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>
    </QueryClientProvider>,
  );
}

function SalesStub(): ReactElement {
  // `useLocation`, not `window.location`: MemoryRouter keeps its history in memory and never
  // touches the document's URL, so reading the global would silently assert nothing.
  const location = useLocation();
  return <p>{`sales ${location.search}`}</p>;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the trends screen', () => {
  it('draws a day the restaurant was shut as a gap, never as zero', async () => {
    renderScreen();

    await screen.findByText('₹18,400.00');
    // Two tables on this screen — the series and the branch comparison. The series one is the
    // first, and it is identified by its own "Period" column rather than by position.
    const table = screen
      .getAllByRole('table')
      .find((candidate) => within(candidate).queryByText('Period') !== null);
    expect(table, 'the series table was not found').toBeDefined();
    // The table view carries the same figures as the chart, so the value the chart refuses to
    // draw is the value the table refuses to invent.
    const rows = within(table as HTMLElement).getAllByRole('row');
    const shut = rows.find((row) => row.textContent?.includes('2 Sep'));
    expect(shut).toBeDefined();
    expect(shut?.textContent).toContain('—');
    expect(shut?.textContent).not.toContain('₹0.00');
  });

  it('shows the real figures formatted as rupees, from the server strings', async () => {
    renderScreen();
    expect(await screen.findByText('₹18,400.00')).toBeInTheDocument();
    expect(screen.getByText('₹21,050.50')).toBeInTheDocument();
  });

  it('says how many branches the series covers', async () => {
    renderScreen();
    expect(await screen.findByText(/One branch/)).toBeInTheDocument();
  });
});

describe('the branch comparison', () => {
  it('says a branch has no dine-in guests rather than ranking it zero', async () => {
    renderScreen();
    // Both charts render it, so there is one per chart — the assertion is that it is *said*,
    // never that a zero appears.
    const notes = await screen.findAllByText('No dine-in guests');
    expect(notes.length).toBeGreaterThanOrEqual(1);
  });

  it('shows guests per trading day beside spend per guest, the recorded blind spot', async () => {
    renderScreen();
    expect(await screen.findByText('Spend per dine-in guest')).toBeInTheDocument();
    expect(screen.getByText('Guests a trading day')).toBeInTheDocument();
  });

  it('divides guests by the days a branch actually traded, not by the window', async () => {
    renderScreen();
    // Spice Garden: 220 covers over 3 trading days = 73. Over the window's 4 days it would be 55,
    // which is the figure that makes a shut branch look merely quiet.
    const charts = await screen.findAllByRole('img');
    const footfall = charts.find((chart) =>
      chart.getAttribute('aria-label')?.includes('Guests a trading day'),
    );
    expect(footfall?.textContent).toContain('73');
    expect(footfall?.textContent).not.toContain('55');
  });

  it('is not offered at all to somebody who works at one restaurant', async () => {
    renderScreen([SPICE]);
    await screen.findByText(/One branch/);
    expect(screen.queryByText('Branches compared')).not.toBeInTheDocument();
  });
});

describe('drill-through', () => {
  it('opens the bills for a bucket with the window already in the URL', async () => {
    renderScreen();
    await screen.findByText('₹18,400.00');

    // The keyboard path is the one a test can drive, and it is the same handler the chart's
    // pointer target calls — a chart nobody can tab into is a chart some people cannot use.
    const open = screen.getByRole('button', { name: /Open the bills for 3 Sep/ });
    await userEvent.click(open);

    expect(await screen.findByText(/since=2026-09-03/)).toBeInTheDocument();
    expect(screen.getByText(/until=2026-09-03/)).toBeInTheDocument();
  });
});

describe('the branch drill-through', () => {
  // Found by review, and by watching a full page load end the session in the dev app: the token
  // lives in a module variable, not in storage, so a document load throws it away. The branch
  // already in scope has nothing to re-issue, so it must never take that path.
  it('stays inside the router for the branch already in scope', async () => {
    const assign = vi.fn();
    renderScreen();
    await screen.findByText('Spend per dine-in guest');

    // Replacing the whole `location` is how a jsdom test observes a document load without
    // performing one. If the component calls it, the assertion below fails.
    const original = window.location;
    // Built field by field rather than spread: `Location` is a class instance, and spreading one
    // drops its prototype (eslint no-misused-spread). These are the fields anything here reads.
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        assign,
        href: original.href,
        search: original.search,
        pathname: original.pathname,
        origin: original.origin,
        reload: () => undefined,
      },
    });

    try {
      await userEvent.click(
        screen.getByRole('button', { name: /Open the sales report for Spice Garden/ }),
      );
      expect(assign, 'a document load would discard the access token').not.toHaveBeenCalled();
      expect(await screen.findByText(/since=2026-09-01/)).toBeInTheDocument();
    } finally {
      Object.defineProperty(window, 'location', { configurable: true, value: original });
    }
  });
});
