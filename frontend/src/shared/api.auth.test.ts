// The authenticated half of the API client: what it sends, and what it does with a 401.
//
// The 401 path is the part worth testing hardest. Getting it wrong does not produce a wrong pixel,
// it produces a refresh loop — a tab that hammers /auth/refresh forever on a dead session, on a
// restaurant's metered connection, with nobody watching. The spec asks for exactly one attempt and
// these tests are what hold that to exactly one.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiClientError, apiGet, apiPost, onSessionExpired, setAccessToken } from '@shared/api';

/** Answers calls in order, so a test can script "401, then the refresh, then the retry". */
function mockFetchSequence(...responses: (Response | Error)[]) {
  const queue = [...responses];
  const spy = vi.fn(() => {
    const next = queue.shift();
    if (next === undefined) {
      throw new Error('fetch was called more times than the test scripted');
    }
    return next instanceof Error ? Promise.reject(next) : Promise.resolve(next);
  });
  vi.stubGlobal('fetch', spy);
  return spy;
}

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
}

function unauthorised(): Response {
  return jsonResponse(
    { code: 'auth.token_expired', message: 'Your session has expired.' },
    {
      status: 401,
    },
  );
}

function headersOf(call: unknown): Record<string, string> {
  const [, init] = call as [string, RequestInit];
  return (init.headers ?? {}) as Record<string, string>;
}

beforeEach(() => {
  setAccessToken(null);
  onSessionExpired(null);
});

afterEach(() => {
  vi.unstubAllGlobals();
  setAccessToken(null);
  onSessionExpired(null);
});

describe('sending', () => {
  it('posts a JSON body and returns the parsed response', async () => {
    const fetchSpy = mockFetchSequence(jsonResponse({ access_token: 'tok' }));

    const result = await apiPost<{ access_token: string }>('/auth/login', {
      identifier: 'owner@spicegarden.test',
      password: 'Staging#2026',
    });

    expect(result.access_token).toBe('tok');
    const [url, init] = fetchSpy.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/api/v1/auth/login');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toMatchObject({ identifier: 'owner@spicegarden.test' });
  });

  it('attaches the access token when there is one', async () => {
    setAccessToken('the-token');
    const fetchSpy = mockFetchSequence(jsonResponse({ items: [] }));

    await apiGet('/staff/employees');

    expect(headersOf(fetchSpy.mock.calls[0]).Authorization).toBe('Bearer the-token');
  });

  it('sends no Authorization header before anyone has signed in', async () => {
    const fetchSpy = mockFetchSequence(jsonResponse({ ok: true }));

    await apiGet('/version');

    expect(headersOf(fetchSpy.mock.calls[0]).Authorization).toBeUndefined();
  });

  it('returns undefined for 204, which is what logout and deactivate answer', async () => {
    mockFetchSequence(new Response(null, { status: 204 }));

    await expect(apiPost('/auth/logout')).resolves.toBeUndefined();
  });
});

describe('a 401', () => {
  it('refreshes once and replays the original request', async () => {
    setAccessToken('expired-token');
    const fetchSpy = mockFetchSequence(
      unauthorised(),
      jsonResponse({ access_token: 'fresh-token' }),
      jsonResponse({ items: ['a waiter'] }),
    );

    const result = await apiGet<{ items: string[] }>('/staff/employees');

    expect(result.items).toEqual(['a waiter']);
    expect(fetchSpy).toHaveBeenCalledTimes(3);
    // The replay must carry the NEW token. Replaying with the expired one would 401 again and,
    // depending on the retry guard, either fail a valid session or loop.
    expect(headersOf(fetchSpy.mock.calls[2]).Authorization).toBe('Bearer fresh-token');
  });

  it('gives up after one failed refresh instead of looping', async () => {
    setAccessToken('expired-token');
    const fetchSpy = mockFetchSequence(
      unauthorised(),
      jsonResponse(
        { code: 'auth.session_invalid', message: 'Please sign in again.' },
        {
          status: 401,
        },
      ),
    );

    await expect(apiGet('/staff/employees')).rejects.toBeInstanceOf(ApiClientError);

    // Exactly two: the original and the refresh. Not a third, and not a thousand.
    expect(fetchSpy).toHaveBeenCalledTimes(2);
  });

  it('tells the app the session is over so it can redirect to login', async () => {
    setAccessToken('expired-token');
    mockFetchSequence(
      unauthorised(),
      jsonResponse(
        { code: 'auth.session_invalid', message: 'Please sign in again.' },
        {
          status: 401,
        },
      ),
    );
    const expired = vi.fn();
    onSessionExpired(expired);

    await apiGet('/staff/employees').catch(() => undefined);

    expect(expired).toHaveBeenCalledTimes(1);
  });

  it('forgets the dead access token, so nothing replays it', async () => {
    setAccessToken('expired-token');
    const fetchSpy = mockFetchSequence(
      unauthorised(),
      jsonResponse({ code: 'auth.session_invalid', message: 'no' }, { status: 401 }),
      jsonResponse({ ok: true }),
    );

    await apiGet('/staff/employees').catch(() => undefined);
    await apiGet('/version');

    expect(headersOf(fetchSpy.mock.calls[2]).Authorization).toBeUndefined();
  });

  it('refreshes once for several requests that fail together', async () => {
    // Three widgets mount at once and all 401. Without single-flighting this is three refreshes,
    // and because refresh rotates the token, two of them are replays — which the backend treats as
    // theft and answers by revoking the whole family. The user is then logged out for loading a page.
    setAccessToken('expired-token');
    const fetchSpy = mockFetchSequence(
      unauthorised(),
      unauthorised(),
      unauthorised(),
      jsonResponse({ access_token: 'fresh-token' }),
      jsonResponse({ one: true }),
      jsonResponse({ two: true }),
      jsonResponse({ three: true }),
    );

    await Promise.all([apiGet('/a'), apiGet('/b'), apiGet('/c')]);

    const refreshCalls = fetchSpy.mock.calls.filter(
      (call) => (call as unknown as [string])[0] === '/api/v1/auth/refresh',
    );
    expect(refreshCalls).toHaveLength(1);
  });

  it('does not end the session when the refresh fails for a reason that is not the session', async () => {
    // A 502 from a proxy during a deploy is not "your session expired" — it is "come back in ten
    // seconds". Signing someone out for it is a mid-service lockout caused by our own deployment,
    // and it is inconsistent with a dropped connection, which already propagates as an error
    // rather than ending the session.
    setAccessToken('a-perfectly-good-token');
    mockFetchSequence(
      unauthorised(),
      new Response('<html>502 Bad Gateway</html>', { status: 502 }),
    );
    const expired = vi.fn();
    onSessionExpired(expired);

    await apiGet('/staff/employees').catch(() => undefined);

    expect(expired).not.toHaveBeenCalled();
  });

  it('does not try to refresh a failed login', async () => {
    // A wrong password is a 401 the user must see, not a session to repair. Refreshing here would
    // turn "Invalid login or password" into a confusing second failure.
    const fetchSpy = mockFetchSequence(
      jsonResponse(
        { code: 'auth.invalid_credentials', message: 'Invalid login or password.' },
        {
          status: 401,
        },
      ),
    );

    await expect(apiPost('/auth/login', { identifier: 'x', password: 'y' })).rejects.toMatchObject({
      code: 'auth.invalid_credentials',
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });
});

// Backlog-issues B4 (owner decision D6). The server has no grace window: a rotated refresh token
// presented twice revokes the whole family. So tabs of one browser take turns — each refreshes
// inside the same Web Lock — and a browser without Web Locks keeps this tab's single-flight.
function refreshes(spy: ReturnType<typeof vi.fn>): number {
  return spy.mock.calls.filter(
    (call) => (call as unknown as [string])[0] === '/api/v1/auth/refresh',
  ).length;
}

describe('refreshing across tabs', () => {
  it('refreshes inside the lock every tab of this browser shares', async () => {
    setAccessToken('expired-token');
    const fetchSpy = mockFetchSequence(
      unauthorised(),
      jsonResponse({ access_token: 'fresh-token' }),
      jsonResponse({ ok: true }),
    );
    const request = vi.fn(async (_name: string, run: () => Promise<unknown>) => {
      expect(refreshes(fetchSpy)).toBe(0);
      const result = await run();
      expect(refreshes(fetchSpy)).toBe(1);
      return result;
    });
    vi.stubGlobal('navigator', { locks: { request } });

    await expect(apiGet('/a')).resolves.toEqual({ ok: true });

    expect(request).toHaveBeenCalledTimes(1);
    expect(request.mock.calls[0]?.[0]).toBe('restaurant-os-refresh');
  });

  it('still refreshes exactly once in a browser without the lock', async () => {
    setAccessToken('expired-token');
    vi.stubGlobal('navigator', {});
    const fetchSpy = mockFetchSequence(
      unauthorised(),
      jsonResponse({ access_token: 'fresh-token' }),
      jsonResponse({ ok: true }),
    );

    await expect(apiGet('/a')).resolves.toEqual({ ok: true });

    expect(refreshes(fetchSpy)).toBe(1);
  });
});
