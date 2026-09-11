// Regression tests for the session the app holds after each way of obtaining one.
//
// There are two paths to a session — signing in, and restoring from the refresh cookie on a cold
// load — and they went through different code. Anything true of one and not the other shows up as
// a field that is populated after a page refresh but blank immediately after login, which is
// exactly the kind of defect nobody reproduces because everybody reloads while developing.

import { afterEach, describe, expect, it, vi } from 'vitest';

import { setAccessToken } from '@shared/api';

import { login, restore } from './session';
import type { RestaurantSummary } from './session';

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

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function mockApi(routes: Record<string, () => Response>): void {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      const handler = routes[url.replace('/api/v1', '')];
      return Promise.resolve(
        handler === undefined ? json({ code: 'x', message: 'not scripted' }, 404) : handler(),
      );
    }),
  );
}

const LOGIN_RESPONSE = {
  access_token: 'tok',
  password_change_required: false,
  expires_in_seconds: 900,
  employee_id: 'e1',
  full_name: 'Rajesh Mehta',
  restaurant: RESTAURANT,
  roles: ['owner'],
  permissions: ['employee.view'],
};

const ME_RESPONSE = {
  employee_id: 'e1',
  full_name: 'Rajesh Mehta',
  employee_code: 'EMP001',
  restaurant: RESTAURANT,
  roles: ['owner'],
  permissions: ['employee.view'],
};

afterEach(() => {
  vi.unstubAllGlobals();
  setAccessToken(null);
});

describe('signing in', () => {
  it('knows the employee code, which only /auth/me carries', async () => {
    // Regression: the profile screen renders session.employeeCode. Built from the login response
    // alone it was the empty string, so a person who had just signed in saw a blank code — and it
    // filled itself in on the next page reload, which is why it survived development.
    mockApi({
      '/auth/login': () => json(LOGIN_RESPONSE),
      '/auth/me': () => json(ME_RESPONSE),
    });

    const session = await login('owner@spicegarden.test', 'Staging#2026');

    expect(session.employeeCode).toBe('EMP001');
  });

  it('produces the same shape as a cold-load restore', async () => {
    // The property that actually matters: two paths in, one session out. Asserting the fields
    // rather than one of them, so the next field added to /auth/me cannot diverge quietly.
    mockApi({
      '/auth/login': () => json(LOGIN_RESPONSE),
      '/auth/refresh': () => json(LOGIN_RESPONSE),
      '/auth/me': () => json(ME_RESPONSE),
    });

    const signedIn = await login('owner@spicegarden.test', 'Staging#2026');
    const restored = await restore();

    expect(restored).toEqual(signedIn);
  });

  it('reports a bad password rather than a half-built session', async () => {
    mockApi({
      '/auth/login': () =>
        json({ code: 'auth.invalid_credentials', message: 'Invalid login or password.' }, 401),
    });

    await expect(login('owner@spicegarden.test', 'wrong')).rejects.toMatchObject({
      code: 'auth.invalid_credentials',
    });
  });
});

describe('restoring on a cold load', () => {
  it('returns null when nobody is signed in, rather than throwing', async () => {
    // The ordinary state of a login page. Treating it as an error would put a red box on the
    // screen of every first-time visitor.
    mockApi({ '/auth/refresh': () => json({ code: 'auth.session_invalid', message: 'no' }, 401) });

    await expect(restore()).resolves.toBeNull();
  });
});

describe('a password somebody else set', () => {
  it('is carried into the session so the profile screen can say so', async () => {
    // /auth/me describes the person, not the credential — the flag only ever arrives on the login
    // or refresh response, so it has to survive the hop through profile().
    mockApi({
      '/auth/login': () => json({ ...LOGIN_RESPONSE, password_change_required: true }),
      '/auth/me': () => json(ME_RESPONSE),
    });

    const session = await login('waiter@spicegarden.test', 'a-temporary-password');

    expect(session.passwordChangeRequired).toBe(true);
  });

  it('is not set for an ordinary sign-in', async () => {
    mockApi({
      '/auth/login': () => json(LOGIN_RESPONSE),
      '/auth/me': () => json(ME_RESPONSE),
    });

    const session = await login('owner@spicegarden.test', 'Staging#2026');

    expect(session.passwordChangeRequired).toBe(false);
  });
});
