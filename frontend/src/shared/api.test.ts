import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiClientError, apiGet } from '@shared/api';

// api.ts is the only module allowed to call fetch, so it is the only one that has to be tested
// against a faked fetch rather than a faked api client.
// Returns the spy rather than reading the global back: eslint forbids referencing `fetch` outside
// api.ts, and the rule is worth more than the convenience of `vi.mocked(fetch)`.
function mockFetch(response: Response | Error) {
  const spy = vi.fn(() =>
    response instanceof Error ? Promise.reject(response) : Promise.resolve(response),
  );
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

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('apiGet', () => {
  it('prefixes /api/v1 and returns the parsed body', async () => {
    const fetchSpy = mockFetch(jsonResponse({ git_sha: 'abc1234' }));

    const result = await apiGet<{ git_sha: string }>('/version');

    expect(result.git_sha).toBe('abc1234');
    expect(fetchSpy).toHaveBeenCalledWith('/api/v1/version', {
      method: 'GET',
      headers: { Accept: 'application/json' },
    });
  });

  it('keeps money as a string so no float ever touches a rupee', async () => {
    mockFetch(jsonResponse({ total_amount: '1240.00' }));

    const result = await apiGet<{ total_amount: string }>('/orders/1');

    expect(result.total_amount).toBe('1240.00');
    expect(typeof result.total_amount).toBe('string');
  });

  it('turns the backend error envelope into an ApiClientError', async () => {
    mockFetch(
      jsonResponse(
        {
          code: 'order.already_settled',
          message: 'Order #1042 was settled at 21:14.',
          details: { order_id: '1042' },
        },
        { status: 409, headers: { 'X-Request-Id': 'req-abc' } },
      ),
    );

    await expect(apiGet('/orders/1042')).rejects.toMatchObject({
      code: 'order.already_settled',
      message: 'Order #1042 was settled at 21:14.',
      details: { order_id: '1042' },
      requestId: 'req-abc',
    });
  });

  it('synthesises a code when the body is not our envelope', async () => {
    // A proxy 502 or an HTML error page never reached the application, but the UI still switches
    // on code and never on HTTP status, so one has to be invented.
    mockFetch(new Response('<html>502 Bad Gateway</html>', { status: 502 }));

    await expect(apiGet('/version')).rejects.toMatchObject({ code: 'http.502' });
  });

  it('synthesises a code when the envelope is missing required fields', async () => {
    mockFetch(jsonResponse({ code: 404 }, { status: 404 }));

    await expect(apiGet('/version')).rejects.toMatchObject({ code: 'http.404' });
  });

  it('reports a dead network as a coded error, not a bare TypeError', async () => {
    // Restaurant networks drop constantly; the error state renders `code`, so it must exist.
    mockFetch(new TypeError('Failed to fetch'));

    const error = await apiGet('/version').catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiClientError);
    expect(error).toMatchObject({ code: 'network.unreachable' });
  });

  it('omits requestId when the response carries no header', async () => {
    mockFetch(jsonResponse({ code: 'a.b', message: 'nope' }, { status: 400 }));

    const error = (await apiGet('/version').catch((caught: unknown) => caught)) as ApiClientError;

    expect(error.requestId).toBeUndefined();
  });
});
