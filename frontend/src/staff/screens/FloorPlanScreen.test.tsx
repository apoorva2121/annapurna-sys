// Owner defect sheet row 7 (backlog-issues B12): a table could not be deactivated, so an area with
// tables could never be either.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import FloorPlanScreen from './FloorPlanScreen';

type FetchCall = [url: string, init?: RequestInit | undefined];

const TABLE = { id: 't1', dining_area_id: 'a1', code: 'T1', seats: 4, status: 'free', is_active: true };

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('a table', () => {
  it('is deactivated from its own row', async () => {
    const fetchMock = vi.fn<(...call: FetchCall) => Promise<Response>>((url, init) => {
      if (init?.method === 'PATCH') {
        return Promise.resolve(json({ ...TABLE, is_active: false }));
      }
      if (url.includes('dining-areas')) {
        return Promise.resolve(
          json({ items: [{ id: 'a1', name: 'Terrace', seq: 0, is_active: true }], next_cursor: null }),
        );
      }
      return Promise.resolve(json({ items: [TABLE], next_cursor: null }));
    });
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter>
          <FloorPlanScreen />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await user.click(await screen.findByRole('button', { name: 'Deactivate table T1' }));

    await waitFor(() => {
      const patch = fetchMock.mock.calls.find(([, init]) => init?.method === 'PATCH');
      expect(String(patch?.[0])).toMatch(/\/staff\/setup\/tables\/t1$/);
      const body = (patch?.[1])?.body;
      expect(typeof body).toBe('string');
      expect(JSON.parse(body as string)).toEqual({ is_active: false });
    });
  });
});
