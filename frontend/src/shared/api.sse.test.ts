// The SSE reader behind M08's kitchen display.
//
// Three of these are the ones that bite in a real kitchen rather than in a demo: an event split
// across two network chunks, a multi-byte character split across two network chunks, and a
// heartbeat that must not look like an event. The fourth is the reason this exists at all — the
// browser's own EventSource cannot carry an Authorization header, and this application's access
// token is in memory rather than in a cookie.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { openEventStream, setAccessToken, type StreamEvent } from '@shared/api';

/** A response whose body yields exactly these chunks, in order. */
function streamingResponse(chunks: string[], status = 200): Response {
  const encoder = new TextEncoder();
  let index = 0;
  const body = {
    getReader: () => ({
      read: () =>
        Promise.resolve(
          index < chunks.length
            ? { done: false, value: encoder.encode(chunks[index++]) }
            : { done: true, value: undefined },
        ),
      releaseLock: () => undefined,
    }),
  };
  return { ok: status >= 200 && status < 300, status, body } as unknown as Response;
}

async function collect(): Promise<StreamEvent[]> {
  const seen: StreamEvent[] = [];
  await openEventStream('/staff/kot/stream', {
    signal: new AbortController().signal,
    onEvent: (event) => seen.push(event),
  });
  return seen;
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);
  setAccessToken('a-token');
});

afterEach(() => {
  setAccessToken(null);
  vi.unstubAllGlobals();
});

describe('openEventStream', () => {
  it('carries the access token, which is the whole reason it is not an EventSource', async () => {
    fetchMock.mockResolvedValue(streamingResponse(['data: {"a":1}\n\n']));

    await collect();

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer a-token');
  });

  it('asks the server to resume from the last event it applied', async () => {
    fetchMock.mockResolvedValue(streamingResponse([': ping\n\n']));

    await openEventStream('/staff/kot/stream', {
      signal: new AbortController().signal,
      lastEventId: '41',
      onEvent: () => undefined,
    });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((init.headers as Record<string, string>)['Last-Event-ID']).toBe('41');
  });

  it('never puts the token in the URL, where every proxy log would keep it', async () => {
    fetchMock.mockResolvedValue(streamingResponse([': ping\n\n']));

    await collect();

    const [url] = fetchMock.mock.calls[0] as [string];
    expect(url).not.toContain('a-token');
  });

  it('parses an event that arrives whole', async () => {
    fetchMock.mockResolvedValue(
      streamingResponse(['id: 7\nevent: ticket\ndata: {"ticket_number":"12"}\n\n']),
    );

    const seen = await collect();

    expect(seen).toEqual([{ id: '7', event: 'ticket', data: '{"ticket_number":"12"}' }]);
  });

  it('parses an event split across two chunks', async () => {
    // TCP does not respect event boundaries. Parsing each chunk on its own would drop this one.
    fetchMock.mockResolvedValue(
      streamingResponse(['id: 7\nevent: ticket\nda', 'ta: {"ticket_number":"12"}\n\n']),
    );

    const seen = await collect();

    expect(seen).toHaveLength(1);
    expect(seen[0]?.data).toBe('{"ticket_number":"12"}');
  });

  it('keeps a multi-byte character whole across a chunk boundary', async () => {
    // A rupee sign, or a dish name in Devanagari, straddling two chunks. Decoding each chunk
    // independently corrupts it — and a corrupted dish name on a kitchen display is a wrong dish.
    const encoder = new TextEncoder();
    const bytes = encoder.encode('data: ₹\n\n');
    const decoder = new TextDecoder();
    const first = decoder.decode(bytes.slice(0, 7), { stream: true });
    const second = decoder.decode(bytes.slice(7), { stream: true });
    fetchMock.mockResolvedValue(streamingResponse([first, second]));

    const seen = await collect();

    expect(seen[0]?.data).toBe('₹');
  });

  it('treats a heartbeat comment as proof of life and not as an event', async () => {
    fetchMock.mockResolvedValue(streamingResponse([': heartbeat\n\n', 'data: real\n\n']));

    const seen = await collect();

    expect(seen.map((event) => event.data)).toEqual(['real']);
  });

  it('reports the server-chosen backoff so the screen does not invent its own', async () => {
    fetchMock.mockResolvedValue(streamingResponse(['retry: 3000\ndata: x\n\n']));
    const intervals: number[] = [];

    await openEventStream('/staff/kot/stream', {
      signal: new AbortController().signal,
      onEvent: () => undefined,
      onRetryInterval: (milliseconds) => intervals.push(milliseconds),
    });

    expect(intervals).toEqual([3000]);
  });

  it('joins a multi-line data field with newlines, as the wire format says', async () => {
    fetchMock.mockResolvedValue(streamingResponse(['data: one\ndata: two\n\n']));

    const seen = await collect();

    expect(seen[0]?.data).toBe('one\ntwo');
  });

  it('refreshes once and reconnects when the token expired mid-service', async () => {
    fetchMock
      .mockResolvedValueOnce(streamingResponse([], 401))
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ access_token: 'fresh' }),
        headers: new Headers(),
      })
      .mockResolvedValueOnce(streamingResponse(['data: after\n\n']));

    const seen = await collect();

    expect(seen[0]?.data).toBe('after');
  });

  it('raises the error envelope rather than a bare failure when refused', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 403,
      json: () => Promise.resolve({ code: 'permission.denied', message: 'You do not have access.' }),
      headers: new Headers(),
    });

    await expect(
      openEventStream('/staff/kot/stream', {
        signal: new AbortController().signal,
        onEvent: () => undefined,
      }),
    ).rejects.toMatchObject({ code: 'permission.denied' });
  });
});
