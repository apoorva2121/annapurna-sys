// What the staff app shows to whom.
//
// These are the UI half of manual tests A1, A2, C2, C3 and D4. They render the real App inside the
// real AuthProvider and drive it through a faked network, so the thing under test is the actual
// route tree and the actual guards rather than a component in isolation.
//
// The UI is not a security control — the server refuses every request on its own — so what is
// asserted here is that a waiter is not *shown* doors that will not open, and that typing the URL
// anyway produces a readable refusal instead of a blank screen.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthProvider } from '@staff/auth/AuthProvider';
import type { RestaurantSummary } from '@staff/auth/session';

import App from './App';

// Typed, so that a field added to the API contract fails to compile here rather than leaving this
// fixture quietly describing a response the server stopped sending.
const RESTAURANT: RestaurantSummary = {
  id: 'r1',
  name: 'Spice Garden - Koregaon Park',
  code: 'SG_KOREGAON',
  timezone: 'Asia/Kolkata',
  currency: 'INR',
  business_day_start: '05:00:00',
};

const OWNER_PERMISSIONS = [
  'employee.view',
  'employee.create',
  'employee.edit',
  'employee.deactivate',
  'employee.role.assign',
  'employee.password.reset',
  'role.view',
];

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

/**
 * Answer by URL rather than by call order: the app fetches /auth/refresh, then /auth/me, then
 * whatever the landing screen needs, and a positional script would break every time a screen
 * gained a query.
 */
function mockApi(routes: Record<string, () => Response>): void {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      const handler = routes[url.replace('/api/v1', '')];
      return Promise.resolve(
        handler === undefined ? json({ code: 'x', message: 'x' }, 404) : handler(),
      );
    }),
  );
}

/** A signed-in session with the given permissions. */
function signedInAs(permissions: string[], roles: string[]): void {
  mockApi({
    '/auth/refresh': () =>
      json({
        access_token: 'token',
        expires_in_seconds: 900,
        employee_id: 'e1',
        full_name: 'Rajesh Mehta',
        restaurant: RESTAURANT,
        roles,
        permissions,
      }),
    '/auth/me': () =>
      json({
        employee_id: 'e1',
        full_name: 'Rajesh Mehta',
        employee_code: 'EMP001',
        restaurant: RESTAURANT,
        roles,
        permissions,
      }),
    '/staff/employees': () => json({ items: [], next_cursor: null }),
  });
}

function renderAt(path: string): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('a visitor who is not signed in', () => {
  it('is shown the login screen, not the app', async () => {
    // A 401 from refresh is the ordinary state of a login page, not an error.
    mockApi({ '/auth/refresh': () => json({ code: 'auth.session_invalid', message: 'no' }, 401) });

    renderAt('/');

    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument();
  });

  it('gets the login screen even when they deep-link to a staff URL', async () => {
    // Manual test D4: pasting a URL from a previous session must not show data.
    mockApi({ '/auth/refresh': () => json({ code: 'auth.session_invalid', message: 'no' }, 401) });

    renderAt('/staff');

    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument();
    expect(screen.queryByText('Add employee')).not.toBeInTheDocument();
  });
});

describe('an owner', () => {
  it('lands on a page that names their restaurant', async () => {
    // Acceptance criterion 1, and the first place a tenant-scoping bug would be visible.
    signedInAs(OWNER_PERMISSIONS, ['owner']);

    renderAt('/');

    expect(await screen.findByRole('heading', { name: RESTAURANT.name })).toBeInTheDocument();
  });

  it('is offered the staff navigation', async () => {
    signedInAs(OWNER_PERMISSIONS, ['owner']);

    renderAt('/');

    expect(await screen.findAllByRole('link', { name: 'Staff' })).not.toHaveLength(0);
  });
});

describe('a waiter', () => {
  // A waiter holds no permissions at all in M01 — the catalogue gives them none until M07.
  it('is shown no staff navigation', async () => {
    signedInAs([], ['waiter']);

    renderAt('/');

    await screen.findByText(/Signed in as/);
    expect(screen.queryByRole('link', { name: 'Staff' })).not.toBeInTheDocument();
  });

  it('is told plainly that the staff page is not theirs, rather than shown a blank screen', async () => {
    // Manual test C3: typing the URL directly must produce a refusal a human can read.
    signedInAs([], ['waiter']);

    renderAt('/staff');

    expect(await screen.findByText('You do not have access to this.')).toBeInTheDocument();
  });

  it('is told why they have nothing to do yet', async () => {
    // An empty page would read as a broken app. Empty states explain (docs/ui/conventions.md).
    signedInAs([], ['waiter']);

    renderAt('/');

    expect(await screen.findByText(/nothing has been assigned to you yet/)).toBeInTheDocument();
  });
});
