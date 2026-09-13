// The worked example under `business_day_start`, which is the reason this screen exists.
//
// ADR 0004 calls this the setting owners misunderstand most, and the M02 spec asks for a worked
// example rather than a tooltip. The risk being tested is not that the sentence is missing — it is
// that the sentence is *stale*: written once as prose, it would keep saying "counts towards
// Monday's sales" for a value where that is no longer true, and nobody reading it could tell.
//
// So these assert the sentence changes with the control, and that the midnight case says something
// different rather than quietly producing a nonsense example.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthContext, type AuthState } from '@staff/auth/AuthContext';
import type { RestaurantSummary, Session } from '@staff/auth/session';

import RestaurantSettingsScreen from './RestaurantSettingsScreen';

const RESTAURANT: RestaurantSummary = {
  id: 'r1',
  name: 'Spice Garden',
  code: 'SG',
  timezone: 'Asia/Kolkata',
  currency: 'INR',
  business_day_start: '05:00:00',
  theme: { default: null, schedule: [] },
};

const SETTINGS = {
  id: 'r1',
  name: 'Spice Garden',
  code: 'SG',
  timezone: 'Asia/Kolkata',
  currency: 'INR',
  business_day_start: '05:00:00',
  gstin: null,
  fssai_licence: null,
  address: null,
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
          <RestaurantSettingsScreen />
        </AuthContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
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

describe('the business day start', () => {
  it('explains what the saved value does, in a sentence', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(json(SETTINGS))),
    );

    renderScreen();

    // 05:00, so a 01:30 order on Tuesday is still Monday's trading. This is the spec's own example.
    expect(
      await screen.findByText(/An order at 01:30 am on Tuesday counts towards Monday's sales\./),
    ).toBeInTheDocument();
  });

  it('re-explains when the value changes, rather than describing the saved one', async () => {
    // The failure this rules out: prose written once, describing 05:00 forever.
    //
    // 01:00 is chosen deliberately. The example is anchored at 1:30am for any start later than
    // that, so 02:00 or 06:00 would produce the *same* sentence as 05:00 and this test would pass
    // against a hardcoded string. A start of 01:00 has no 1:30 to illustrate, so the example moves
    // to 12:30 am — a value only a real computation produces.
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(json(SETTINGS))),
    );
    const user = userEvent.setup();
    renderScreen();
    const control = await screen.findByLabelText(/business day starts at/i);
    expect(screen.getByText(/An order at 01:30 am/)).toBeInTheDocument();

    await user.clear(control);
    await user.type(control, '01:00');

    await waitFor(() => {
      expect(
        screen.getByText(/An order at 12:30 am on Tuesday counts towards Monday's sales\./),
      ).toBeInTheDocument();
    });
    expect(screen.queryByText(/An order at 01:30 am/)).not.toBeInTheDocument();
  });

  it('says something different at midnight instead of inventing an example', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(json(SETTINGS))),
    );
    const user = userEvent.setup();
    renderScreen();
    const control = await screen.findByLabelText(/business day starts at/i);

    await user.clear(control);
    await user.type(control, '00:00');

    await waitFor(() => {
      expect(screen.getByText(/the business day is the calendar day/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/counts towards/)).not.toBeInTheDocument();
  });
});

describe('saving', () => {
  it('sends the time as HH:MM:SS, which is what the API takes', async () => {
    // Typed rather than inferred, so `mock.calls` destructures to (url, init) without this test
    // declaring parameters it never reads.
    const fetchMock = vi.fn<(...call: FetchCall) => Promise<Response>>(() =>
      Promise.resolve(json(SETTINGS)),
    );
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();
    renderScreen();
    await screen.findByLabelText(/business day starts at/i);

    await user.click(screen.getByRole('button', { name: /save settings/i }));

    await waitFor(() => {
      const patch = fetchMock.mock.calls.find(([, init]) => init?.method === 'PATCH');
      expect(patch).toBeDefined();
      const body = sentJson(patch);
      expect(body.business_day_start).toBe('05:00:00');
    });
  });

  it('sends an empty optional field as null, not as an empty string', async () => {
    // "" would make "this restaurant has a GSTIN" true for one that does not.
    // Typed rather than inferred, so `mock.calls` destructures to (url, init) without this test
    // declaring parameters it never reads.
    const fetchMock = vi.fn<(...call: FetchCall) => Promise<Response>>(() =>
      Promise.resolve(json(SETTINGS)),
    );
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();
    renderScreen();
    await screen.findByLabelText(/business day starts at/i);

    await user.click(screen.getByRole('button', { name: /save settings/i }));

    await waitFor(() => {
      const patch = fetchMock.mock.calls.find(([, init]) => init?.method === 'PATCH');
      const body = sentJson(patch);
      expect(body.gstin).toBeNull();
      expect(body.fssai_licence).toBeNull();
    });
  });

  it('reports a refusal from the server rather than failing silently', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string, init?: RequestInit) =>
        Promise.resolve(
          init?.method === 'PATCH'
            ? json(
                {
                  code: 'restaurant.unknown_timezone',
                  message: "'Asia/Kolkta' is not a known timezone.",
                  details: {},
                },
                422,
              )
            : json(SETTINGS),
        ),
      ),
    );
    const user = userEvent.setup();
    renderScreen();
    await screen.findByLabelText(/business day starts at/i);

    await user.click(screen.getByRole('button', { name: /save settings/i }));

    expect(await screen.findByText(/is not a known timezone/i)).toBeInTheDocument();
  });
});

// Backlog-issues B2: the cleaning time and busy hours, saved on their own.
describe('tables after the bill', () => {
  it('saves a blank cleaning time as null and a new busy window as HH:MM', async () => {
    const fetchMock = vi.fn<(...call: FetchCall) => Promise<Response>>(() =>
      Promise.resolve(json({ ...SETTINGS, tables: { cleaning_minutes: 5, busy_windows: [] } })),
    );
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();
    renderScreen();

    const minutes = await screen.findByLabelText(/Cleaning time/);
    expect(minutes).toHaveValue('5');
    await user.clear(minutes);
    await user.click(screen.getByRole('button', { name: 'Add busy hours' }));
    await user.click(screen.getByRole('button', { name: 'Save table settings' }));

    await waitFor(() => {
      const patch = fetchMock.mock.calls.find(([, init]) => init?.method === 'PATCH');
      expect(sentJson(patch)).toEqual({
        tables: { cleaning_minutes: null, busy_windows: [{ starts: '12:00', ends: '15:00' }] },
      });
    });
  });
});
