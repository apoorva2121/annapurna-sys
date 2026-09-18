// The centre, and the two things about it that are product decisions rather than layout.
//
// **An empty centre is the right answer, and it has to say so.** Everything here is derived from
// live queries, so "nothing needs you" is a real statement about the restaurant. A blank screen
// would be indistinguishable from a broken one — which is exactly the failure a stored-notification
// table filled by a job that is not running produces, and the reason this product does not have one.
//
// **Colour never carries the meaning alone** (`docs/ui/conventions.md` rule 5). Every row says in
// words what kind of condition it is; the tint is the second signal. On a steamed-up screen in a
// kitchen, and for anybody not reading colour, the word is the one that survives.
//
// Who sees which condition is decided on the server, per condition, from the permissions somebody
// holds — `tests/test_audit_endpoints.py::TestTheCentreShowsWhatAPersonCanActOn` is where that
// lives, because it is a rule about people rather than about rendering.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import NotificationsScreen from './NotificationsScreen';

const NEGATIVE = {
  key: 'stock.negative:11111111-1111-1111-1111-111111111111',
  kind: 'stock.negative',
  severity: 'critical',
  subject: 'Paneer',
  detail: '-1400 on the books. Stock was used that nobody recorded receiving.',
  ref_type: 'stock_item',
  ref_id: '11111111-1111-1111-1111-111111111111',
  occurred_at: null,
  read: false,
  dismissed: false,
};

function renderWith(body: unknown): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(
      () =>
        new Response(JSON.stringify(body), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
    ),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const tree: ReactElement = (
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <NotificationsScreen />
      </QueryClientProvider>
    </MemoryRouter>
  );
  render(tree);
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the notification centre', () => {
  it('says nothing needs you, rather than showing a blank screen', async () => {
    renderWith({ items: [], unread: 0 });

    expect(await screen.findByText(/Nothing needs you right now/)).toBeTruthy();
  });

  it('names the kind of condition in words, not only in colour', async () => {
    renderWith({ items: [NEGATIVE], unread: 1 });

    expect(await screen.findByText('Paneer')).toBeTruthy();
    expect(screen.getByText('Stock')).toBeTruthy();
  });

  it('offers a way to go and deal with it', async () => {
    // A notification that cannot be acted on from itself is one somebody has to go and find the
    // screen for, which is how a centre becomes a list people scroll past.
    renderWith({ items: [NEGATIVE], unread: 1 });

    const link = await screen.findByRole('link', { name: /deal with it/ });
    expect(link.getAttribute('href')).toBe('/stock/on-hand');
  });

  it('says out loud that dismissing hides the alert and not the problem', async () => {
    renderWith({ items: [NEGATIVE], unread: 1 });

    expect(
      await screen.findByText(/Dismissing hides this alert. It does not change what it is about./),
    ).toBeTruthy();
  });
});
