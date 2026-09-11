// Regression: saving roles before the role catalogue has loaded used to strip every role.
//
// `current` is derived by matching the employee's role *codes* against the catalogue's role *ids*.
// Until the catalogue arrives there is nothing to match, so it is the empty array — and the server
// treats `role_ids: []` as an authoritative full-set replacement: every assignment deleted, every
// session revoked, and the person can no longer sign in at all (`auth.no_restaurant`). It renders
// as a green "Roles updated."
//
// On a restaurant's connection the window is long enough to tap through.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthContext, type AuthState } from '@staff/auth/AuthContext';

import EmployeeScreen from './EmployeeScreen';

const EMPLOYEE = {
  id: 'e1',
  employee_code: 'EMP003',
  full_name: 'Vikram Deshmukh',
  phone: '9820011003',
  joined_on: '2020-01-10',
  employment_type: 'full_time',
  is_active: true,
  deactivated_at: null,
  has_login: true,
  roles: ['manager'],
};

const ROLES = [
  { id: 'r-owner', code: 'owner', name: 'Owner', description: null, rank: 0, is_system: true },
  {
    id: 'r-manager',
    code: 'manager',
    name: 'Manager',
    description: null,
    rank: 20,
    is_system: true,
  },
];

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

const ALL_PERMISSIONS: AuthState = {
  session: null,
  signIn: () => Promise.resolve(),
  signOut: () => Promise.resolve(),
  can: () => true,
};

/** The employee loads; the catalogue is still in flight. */
function catalogueStillLoading(): void {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) =>
      url.includes('/staff/roles')
        ? new Promise<Response>(() => {
            // never settles
          })
        : Promise.resolve(json(EMPLOYEE)),
    ),
  );
}

function everythingLoaded(): void {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => Promise.resolve(json(url.includes('/staff/roles') ? ROLES : EMPLOYEE))),
  );
}

function renderScreen(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/staff/e1']}>
        <AuthContext.Provider value={ALL_PERMISSIONS}>
          <Routes>
            <Route path="/staff/:employeeId" element={<EmployeeScreen />} />
          </Routes>
        </AuthContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('saving roles', () => {
  it('cannot be submitted before the catalogue has loaded', async () => {
    catalogueStillLoading();

    renderScreen();
    const save = await screen.findByRole('button', { name: /save roles/i });

    expect(save).toBeDisabled();
  });

  it('can be submitted once the catalogue is there', async () => {
    everythingLoaded();

    renderScreen();
    // Wait for a checkbox, not for the button: the button renders immediately and the whole point
    // of the fix is that it is inert until the catalogue behind those checkboxes has arrived.
    await screen.findByRole('checkbox', { name: /manager/i });

    expect(screen.getByRole('button', { name: /save roles/i })).toBeEnabled();
  });

  it('starts with the roles the person already holds ticked', async () => {
    // The other half of the same bug: if this mapping were wrong, saving would silently change
    // roles rather than leaving them alone.
    everythingLoaded();

    renderScreen();

    expect(await screen.findByRole('checkbox', { name: /manager/i })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: /owner/i })).not.toBeChecked();
  });
});
