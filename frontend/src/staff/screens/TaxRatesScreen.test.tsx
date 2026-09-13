// Tax groups and their rates, and the three things this screen must not let someone do.
//
// A rate is copied onto every order line and cited by an invoice. Editing one in place silently
// restates tax already charged and reported — a filing problem, not a data-quality one. The server
// refuses it; this screen must not offer it either, because a control that exists and then fails is
// worse than one that was never there.
//
// The second risk is subtler: superseded rows hidden for tidiness. An invoice from March cites the
// March rate, and someone checking that invoice has to be able to see it.
//
// The third is new in M03. A group is an identity a menu item points at; a rate change must add a
// row *under the same group*, never mint a second group. These tests assert the request shape that
// guarantees it — a POST to the group's own `/rates`, carrying no name and no group of its own.

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

/** One group whose rate has already changed once: 5% until March, 12% since April. */
const GST5 = {
  id: 'group-food',
  code: 'GST5',
  name: 'GST 5% (restaurant, no ITC)',
  is_active: true,
  rates: [
    {
      id: 'rate-current',
      rate: '0.1200',
      is_inclusive: false,
      effective_from: '2026-04-01',
      effective_to: null,
    },
    {
      id: 'rate-old',
      rate: '0.0500',
      is_inclusive: false,
      effective_from: '2025-01-01',
      effective_to: '2026-03-31',
    },
  ],
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
    hasMoreRestaurants: false,
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
    Promise.resolve(init?.method === 'POST' ? json(GST5, 201) : json({ items, next_cursor: null })),
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

function post(mock: ReturnType<typeof listReturns>): FetchCall | undefined {
  return mock.mock.calls.find(([, init]) => init?.method === 'POST');
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the list', () => {
  it('shows superseded rates as well as the current one', async () => {
    listReturns(GST5);

    renderScreen();

    expect(await screen.findByText(/GST 5% \(restaurant/)).toBeInTheDocument();
    // Twice: the group header states what it charges today, the history row states when that began.
    expect(screen.getAllByText('12%')).toHaveLength(2);
    // The one that matters: an invoice from March cites this, so hiding it would make the audit
    // impossible while making the screen look tidier.
    expect(screen.getByText('5%')).toBeInTheDocument();
  });

  it('says which rate is current in a word, not only in a colour', async () => {
    // restaurant-ui rule 5. Commercial kitchens are full of colour-blind men and steamed screens.
    listReturns(GST5);

    renderScreen();

    // Once in the header summary, once on the live row.
    expect(await screen.findAllByText('Current')).toHaveLength(2);
    expect(screen.getByText('Superseded')).toBeInTheDocument();
  });

  it('shows the code, because that is what a menu item joins on', async () => {
    listReturns(GST5);

    renderScreen();

    expect(await screen.findByText('GST5')).toBeInTheDocument();
  });
});

describe('immutability', () => {
  it('offers no way to edit a rate — only to charge a new one', async () => {
    listReturns(GST5);

    renderScreen();
    await screen.findByText('GST5');

    // No control anywhere on the screen claims to change a rate in place.
    expect(screen.queryByRole('button', { name: /^edit/i })).not.toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /change the rate/i })).toHaveLength(1);
  });
});

describe('changing a rate', () => {
  it('posts to the group it belongs to, so the menu is never repointed', async () => {
    // **The assertion M03 decision 1 exists for.** A rate change must add a row under the existing
    // group. Posting to `/setup/tax-groups` instead would mint a second group, and every menu item
    // pointing at the first would be left on a closed period.
    const fetchMock = listReturns(GST5);
    const user = userEvent.setup();
    renderScreen();
    await screen.findByText('GST5');

    await user.click(screen.getByRole('button', { name: /change the rate/i }));
    await user.click(screen.getByRole('button', { name: /^change the rate$/i }));

    await waitFor(() => {
      const sent = post(fetchMock);
      expect(sent?.[0]).toContain('/staff/setup/tax-groups/group-food/rates');
    });
    const body = sentJson(post(fetchMock));
    // No name and no code: a rate has neither. Sending one would mean the client thought it was
    // creating a group.
    expect(body.name).toBeUndefined();
    expect(body.code).toBeUndefined();
  });

  it('sends the rate as a four-decimal string, never a float', async () => {
    // 5 in the box is 0.0500 on the wire. Parsing to a number and back is how five percent becomes
    // 0.05000000000000001 on some bill, some day (CLAUDE.md invariant 3).
    const fetchMock = listReturns(GST5);
    const user = userEvent.setup();
    renderScreen();
    await screen.findByText('GST5');

    await user.click(screen.getByRole('button', { name: /change the rate/i }));
    await user.click(screen.getByRole('button', { name: /^change the rate$/i }));

    await waitFor(() => {
      const body = sentJson(post(fetchMock));
      expect(body.rate).toBe('0.0500');
      expect(typeof body.rate).toBe('string');
    });
  });

  it('refuses to send a rate when the rate box is empty', async () => {
    // The defect this closes was unrecoverable. `Number("")` is 0, so submitting with the rate
    // field blank posted `"0.0000"` — a valid rate to the server, copied onto every order line, and
    // then impossible to correct because a rate can only be superseded, never edited. Found by
    // external review of M02.
    //
    // Two independent protections and this asserts the **outcome**, not either one: the browser's
    // `required` (kept by not setting `noValidate`) and the `asFraction` guard. Verified: removing
    // either alone still passes, removing both fails. That is the honest description — a
    // defence-in-depth test, not an isolation test.
    const fetchMock = listReturns(GST5);
    const user = userEvent.setup();
    renderScreen();
    await screen.findByText('GST5');

    await user.click(screen.getByRole('button', { name: /change the rate/i }));
    // Scoped to this group's own card. Two percent boxes are on screen once the change form opens
    // — this one and the add-a-group form's — and clearing the wrong one would make the test pass
    // for the wrong reason.
    const card = screen.getByText('GST5').closest('section');
    expect(card).not.toBeNull();
    await user.clear(within(card as HTMLElement).getByLabelText(/percent/i));
    await user.click(screen.getByRole('button', { name: /^change the rate$/i }));

    // No request at all — not a request the server happens to reject.
    expect(post(fetchMock)).toBeUndefined();
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
            : json({ items: [GST5], next_cursor: null }),
        ),
      ),
    );
    const user = userEvent.setup();
    renderScreen();
    await screen.findByText('GST5');

    await user.click(screen.getByRole('button', { name: /change the rate/i }));
    await user.click(screen.getByRole('button', { name: /^change the rate$/i }));

    expect(await screen.findByText(/cannot start before today/i)).toBeInTheDocument();
  });
});

describe('creating a group', () => {
  it('sends an uppercased code, because a lowercase one would be refused for a reason nobody knows', async () => {
    const fetchMock = listReturns(GST5);
    const user = userEvent.setup();
    renderScreen();
    await screen.findByText('GST5');

    await user.type(screen.getByLabelText(/^code$/i), 'gst18');
    await user.type(screen.getByLabelText(/^name$/i), 'GST 18% (packaged)');
    await user.click(screen.getByRole('button', { name: /^add a tax group$/i }));

    await waitFor(() => {
      const body = sentJson(post(fetchMock));
      expect(body.code).toBe('GST18');
    });
  });

  it('creates the group and its opening rate in one request', async () => {
    // A group with no rate is a trap: a menu item could be attached to it and M07 would find
    // nothing to charge at order time.
    const fetchMock = listReturns(GST5);
    const user = userEvent.setup();
    renderScreen();
    await screen.findByText('GST5');

    await user.type(screen.getByLabelText(/^code$/i), 'GST18');
    await user.type(screen.getByLabelText(/^name$/i), 'GST 18% (packaged)');
    await user.click(screen.getByRole('button', { name: /^add a tax group$/i }));

    await waitFor(() => {
      const sent = post(fetchMock);
      expect(sent?.[0]).toMatch(/\/staff\/setup\/tax-groups$/);
      const body = sentJson(sent);
      expect(body.code).toBe('GST18');
      expect(body.rate).toBe('0.0500');
    });
  });
});
