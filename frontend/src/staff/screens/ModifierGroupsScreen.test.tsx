// Owner defect sheet row 30 (backlog-issues B12): a waiter saw the forms to add options, and the
// server refused the save. Without `menu.manage` the screen is read-only, as the dish screen is.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthContext, type AuthState } from '@staff/auth/AuthContext';

import ModifierGroupsScreen from './ModifierGroupsScreen';

const GROUPS = {
  items: [
    {
      id: 'g1',
      code: 'SPICE_LEVEL',
      name: 'Spice level',
      min_select: 1,
      max_select: 1,
      is_required: true,
      is_active: true,
      modifiers: [{ id: 'm1', code: 'MILD', name: 'Mild', price_delta: '0.00', is_active: true }],
    },
  ],
  next_cursor: null,
};

function renderScreen(permissions: string[]): void {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) =>
      Promise.resolve(
        new Response(
          JSON.stringify(url.includes('modifier-groups') ? GROUPS : { items: [], next_cursor: null }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    ),
  );
  const auth: AuthState = {
    session: null,
    signIn: () => Promise.resolve(),
    signOut: () => Promise.resolve(),
    can: (permission) => permissions.includes(permission),
  };
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <AuthContext.Provider value={auth}>
          <ModifierGroupsScreen />
        </AuthContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ModifierGroupsScreen', () => {
  it('shows a waiter the options and nothing to change them with', async () => {
    renderScreen(['menu.view']);

    expect(await screen.findByText('Mild')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /add option/i })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/option name/i)).not.toBeInTheDocument();
  });

  it('gives someone holding menu.manage the forms', async () => {
    renderScreen(['menu.view', 'menu.manage']);

    expect(await screen.findByText('Mild')).toBeInTheDocument();
    expect(screen.getByLabelText(/option name/i)).toBeInTheDocument();
  });
});
