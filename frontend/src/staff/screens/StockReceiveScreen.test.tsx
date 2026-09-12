// Recording a delivery is the most important write in the product, and the two things asserted
// here are the two ways the screen earns that.
//
// It sends quantities as **strings**, untouched. A receipt of 0.05 g of saffron must arrive at the
// server as "0.05" — parsing it to a number anywhere on this path is how a ledger whose whole
// purpose is exactness starts disagreeing with itself (CLAUDE.md invariant 3).
//
// And its expiry hint explains the *consequence* rather than the field. "Optional" tells somebody
// they may skip it; saying that undated stock waits behind everything dated tells them what
// skipping it does — which is what makes them fill it in for the paneer rather than the rice.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import StockReceiveScreen from './StockReceiveScreen';

const ITEMS = {
  items: [{ id: 's1', code: 'PANEER', name: 'Paneer', base_unit: 'g', kind: 'ingredient' }],
};

function json(body: unknown, status = 200): Response {
  return {
    ok: status < 400,
    status,
    json: () => Promise.resolve(body),
    headers: new Headers({ 'content-type': 'application/json' }),
  } as unknown as Response;
}

function renderScreen(): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn((input: unknown, init?: RequestInit) => {
    const url = String(input);
    if (init?.method === 'POST') return Promise.resolve(json({ id: 'b1' }, 201));
    if (url.includes('stock-items')) return Promise.resolve(json(ITEMS));
    return Promise.resolve(json({}));
  });
  vi.stubGlobal('fetch', fetchMock);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <StockReceiveScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

/** The POST body, typed rather than stringified through `String()`.
 *
 * eslint's `no-base-to-string` is right to refuse the shorter version: `RequestInit['body']` is a
 * union that includes `FormData` and `Blob`, and `String()` on either yields "[object Object]" —
 * an assertion that would then pass or fail for reasons unrelated to what was sent. */
function postedBody(fetchMock: ReturnType<typeof vi.fn>): Record<string, unknown> {
  const post = fetchMock.mock.calls.find(
    ([, init]) => (init as RequestInit | undefined)?.method === 'POST',
  );
  expect(post).toBeDefined();
  const raw = (post?.[1] as RequestInit).body;
  expect(typeof raw).toBe('string');
  return JSON.parse(raw as string) as Record<string, unknown>;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('recording a delivery', () => {
  it('explains what leaving the expiry blank actually does', async () => {
    renderScreen();

    expect(await screen.findByText(/waits behind everything that has a date/)).toBeInTheDocument();
  });

  it('says why recording the delivery matters at all', async () => {
    // The person typing this is the person who decides whether it gets typed. The intro is aimed
    // at them: unrecorded stock reappears later as a position below zero somebody has to explain.
    renderScreen();

    expect(await screen.findByText(/shows up later as a position below zero/)).toBeInTheDocument();
  });

  it('sends the quantity as the exact string that was typed', async () => {
    const fetchMock = renderScreen();
    await screen.findByRole('option', { name: /Paneer/ });

    await userEvent.selectOptions(screen.getByLabelText(/Item/), 's1');
    await userEvent.type(screen.getByLabelText(/Quantity/), '0.05');
    await userEvent.type(screen.getByLabelText(/Cost per unit/), '410.50');
    await userEvent.click(screen.getByRole('button', { name: 'Record it' }));

    const body = postedBody(fetchMock);
    // Strings, not 0.05 and 410.5. A float round-trip is how the second becomes 410.49999999999994.
    expect(body.quantity).toBe('0.05');
    expect(body.unit_cost).toBe('410.50');
  });

  it('sends null rather than an empty string for an omitted expiry', async () => {
    // `""` is not a date, and a server that had to interpret it would be guessing.
    const fetchMock = renderScreen();
    await screen.findByRole('option', { name: /Paneer/ });

    await userEvent.selectOptions(screen.getByLabelText(/Item/), 's1');
    await userEvent.type(screen.getByLabelText(/Quantity/), '100');
    await userEvent.type(screen.getByLabelText(/Cost per unit/), '1');
    await userEvent.click(screen.getByRole('button', { name: 'Record it' }));

    const body = postedBody(fetchMock);
    expect(body.expiry_date).toBeNull();
    expect(body.storage_location).toBeNull();
  });
});
