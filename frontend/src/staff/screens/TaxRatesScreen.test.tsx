// Tax rates, and the two things this screen must not let someone do.
//
// A rate is copied onto every order line and cited by an invoice. Editing one in place silently
// restates tax already charged and reported — a filing problem, not a data-quality one. The server
// refuses it; this screen must not offer it either, because a control that exists and then fails is
// worse than one that was never there.
//
// The other risk is subtler: superseded rows hidden for tidiness. An invoice from March cites the
// March rate, and someone checking that invoice has to be able to see it.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthContext, type AuthState } from '@staff/auth/AuthContext';
import type { RestaurantSummary, Session } from '@staff/auth/session';

import TaxRatesScreen from './TaxRatesScreen';

const RESTAURANT: RestaurantSummary = {
  id: 'r1',
  name: 'Spice Garden',
  code: 'SG',
  timezone: 'Asia/Kolkata',
  currency: 'INR',
  business_day_start: '05:00:00',
  theme: { default: null, schedule: [] },
};

const CURRENT = {
  id: 'tax-current',
  name: 'GST 12%',
  rate: '0.1200',
  is_inclusive: false,
  effective_from: '2026-04-01',
  effective_to: null,
};

const SUPERSEDED = {
  id: 'tax-old',
  name: 'GST 5%',
  rate: '0.0500',
  is_inclusive: false,
  effective_from: '2025-01-01',
  effective_to: '2026-03-31',
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const AUTH: AuthState = {
  session: {
    employeeId: 'e1',
    passwordChangeRequired: false,
    fullName: 'Priya Nair',
    employeeCode: 'EMP001',
    restaurant: RESTAURANT,
    restaurants: [RESTAURANT],
    roles: ['owner'],
    permissions: new Set<string>(),
  } satisfies Session,
  signIn: () => Promise.resolve(),
  signOut: () => Promise.resolve(),
  can: () => true,
};

function renderScreen(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AuthContext.Provider value={AUTH}>
          <TaxRatesScreen />
        </AuthContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function listReturns(...items: unknown[]) {
  const mock = vi.fn((_url: string, init?: RequestInit) =>
    Promise.resolve(
      init?.method === 'POST' ? json(CURRENT, 201) : json({ items, next_cursor: null }),
    ),
  );
  vi.stubGlobal('fetch', mock);
  return mock;
}

/** The JSON a recorded fetch call sent. `body` is a `BodyInit`, so this narrows rather than
 *  stringifying — `String(body)` on a non-string yields "[object Object]" and a useless failure. */
type FetchCall = [url: string, init?: RequestInit | undefined];

function sentJson(call: FetchCall | undefined): Record<string, unknown> {
  const body = call?.[1]?.body;
  if (typeof body !== 'string') {
    throw new Error('that request sent no JSON body');
  }
  return JSON.parse(body) as Record<string, unknown>;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the list', () => {
  it('shows superseded rates as well as the current one', async () => {
    listReturns(CURRENT, SUPERSEDED);

    renderScreen();

    expect(await screen.findByText('GST 12%')).toBeInTheDocument();
    // The one that matters: an invoice from March cites this, so hiding it would make the audit
    // impossible while making the screen look tidier.
    expect(screen.getByText('GST 5%')).toBeInTheDocument();
  });

  it('says which is current in a word, not only in a colour', async () => {
    // restaurant-ui rule 5. Commercial kitchens are full of colour-blind men and steamed screens.
    listReturns(CURRENT, SUPERSEDED);

    renderScreen();

    expect(await screen.findByText('Current')).toBeInTheDocument();
    expect(screen.getByText('Superseded')).toBeInTheDocument();
  });

  it('renders the rate as a percentage without doing arithmetic on a rupee', async () => {
    listReturns(CURRENT, SUPERSEDED);

    renderScreen();

    expect(await screen.findByText('12%')).toBeInTheDocument();
    expect(screen.getByText('5%')).toBeInTheDocument();
  });
});

describe('immutability', () => {
  it('offers no way to edit a rate — only to replace it', async () => {
    listReturns(CURRENT, SUPERSEDED);

    renderScreen();
    await screen.findByText('GST 12%');

    // No control anywhere on the screen claims to change a rate in place.
    expect(screen.queryByRole('button', { name: /^edit/i })).not.toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /replace this rate/i })).toHaveLength(1);
  });

  it('does not offer to replace an already superseded rate', async () => {
    // It is already closed; replacing it would mean two rates live on one date, and an order line
    // would take whichever the query happened to return first.
    listReturns(CURRENT, SUPERSEDED);

    renderScreen();
    const supersededRow = (await screen.findByText('GST 5%')).closest('tr');

    expect(supersededRow).not.toBeNull();
    expect(
      within(supersededRow as HTMLElement).queryByRole('button', { name: /replace/i }),
    ).not.toBeInTheDocument();
  });
});

describe('creating a rate', () => {
  it('sends the rate as a four-decimal string, never a float', async () => {
    // 5 in the box is 0.0500 on the wire. Parsing to a number and back is how five percent becomes
    // 0.05000000000000001 on some bill, some day (CLAUDE.md invariant 3).
    const fetchMock = listReturns(CURRENT);
    const user = userEvent.setup();
    renderScreen();
    await screen.findByText('GST 12%');

    await user.type(screen.getByLabelText(/^name$/i), 'GST 5%');
    await user.click(screen.getByRole('button', { name: /^add a tax rate$/i }));

    await waitFor(() => {
      const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST');
      expect(post).toBeDefined();
      const body = sentJson(post);
      expect(body.rate).toBe('0.0500');
      expect(typeof body.rate).toBe('string');
    });
  });

  it('carries supersedes_id when replacing, so the two periods are closed in one request', async () => {
    const fetchMock = listReturns(CURRENT);
    const user = userEvent.setup();
    renderScreen();
    await screen.findByText('GST 12%');

    await user.click(screen.getByRole('button', { name: /replace this rate/i }));
    await user.type(screen.getByLabelText(/^name$/i), 'GST 18%');
    await user.click(screen.getByRole('button', { name: /^add a tax rate$/i }));

    await waitFor(() => {
      const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST');
      const body = sentJson(post);
      expect(body.supersedes_id).toBe('tax-current');
    });
  });

  it('reports a back-dated refusal rather than failing silently', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string, init?: RequestInit) =>
        Promise.resolve(
          init?.method === 'POST'
            ? json(
                {
                  code: 'tax_group.back_dated',
                  message: 'A rate cannot start before today (2026-09-11).',
                  details: {},
                },
                422,
              )
            : json({ items: [CURRENT], next_cursor: null }),
        ),
      ),
    );
    const user = userEvent.setup();
    renderScreen();
    await screen.findByText('GST 12%');

    await user.type(screen.getByLabelText(/^name$/i), 'GST 5%');
    await user.click(screen.getByRole('button', { name: /^add a tax rate$/i }));

    expect(await screen.findByText(/cannot start before today/i)).toBeInTheDocument();
  });
});
