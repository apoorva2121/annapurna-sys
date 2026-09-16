// The staff list, and the thing it must not do: hide people without saying so.
//
// The endpoint pages at 50 and hands back a `next_cursor` when there is more. A screen that
// ignores that cursor shows a restaurant with 60 staff exactly 50 of them, with nothing on screen
// to suggest the other 10 exist — a silent failure, which docs/engineering-standards.md section 5
// forbids outright. It is also invisible in the demo data, which has 19.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthContext, type AuthState } from '@staff/auth/AuthContext';

import StaffListScreen from './StaffListScreen';

function employee(index: number) {
  return {
    id: `e${String(index)}`,
    employee_code: `EMP${String(index).padStart(3, '0')}`,
    full_name: `Person ${String(index)}`,
    phone: null,
    joined_on: '2024-01-01',
    employment_type: 'full_time',
    is_active: true,
    deactivated_at: null,
    has_login: true,
    roles: ['waiter'],
  };
}

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

/** A full page followed by a short one — what the API does when there is a second page. */
function twoPages(): void {
  const first = Array.from({ length: 50 }, (_, index) => employee(index + 1));
  const second = Array.from({ length: 10 }, (_, index) => employee(index + 51));
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) =>
      Promise.resolve(
        url.includes('cursor=')
          ? json({ items: second, next_cursor: null })
          : json({ items: first, next_cursor: 'e50' }),
      ),
    ),
  );
}

const AUTH: AuthState = {
  session: null,
  signIn: () => Promise.resolve(),
  signOut: () => Promise.resolve(),
  can: () => true,
};

function renderList(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AuthContext.Provider value={AUTH}>
          <StaffListScreen />
        </AuthContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('when there are more people than fit on one page', () => {
  it('says so, rather than showing fifty and stopping', async () => {
    twoPages();

    renderList();

    expect(await screen.findByRole('button', { name: /show more/i })).toBeInTheDocument();
  });

  it('shows the rest when asked', async () => {
    twoPages();

    renderList();
    fireEvent.click(await screen.findByRole('button', { name: /show more/i }));

    expect(await screen.findByText('Person 60')).toBeInTheDocument();
    // And the first page is still there — this appends, it does not replace.
    expect(screen.getByText('Person 1')).toBeInTheDocument();
  });
});

describe('when everyone fits on one page', () => {
  it('offers nothing more to show', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(json({ items: [employee(1)], next_cursor: null }))),
    );

    renderList();

    expect(await screen.findByText('Person 1')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /show more/i })).not.toBeInTheDocument();
  });
});

// Decision D14 (backlog-issues B12): finishing an added employee lands here, saying so.
describe('after adding someone', () => {
  it('says who was added and as what', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(json({ items: [], next_cursor: null }))),
    );
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter
          initialEntries={[{ pathname: '/staff', state: { added: 'Ravi Sharma added as Waiter' } }]}
        >
          <AuthContext.Provider value={AUTH}>
            <StaffListScreen />
          </AuthContext.Provider>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText('Ravi Sharma added as Waiter')).toBeInTheDocument();
  });
});
