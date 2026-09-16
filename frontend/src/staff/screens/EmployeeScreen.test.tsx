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
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactElement } from 'react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
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

function StaffListProbe(): ReactElement {
  const { state } = useLocation() as { state: { added?: string } | null };
  return <p>{state?.added ?? 'no notice'}</p>;
}

function renderScreen(path = '/staff/e1'): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <AuthContext.Provider value={ALL_PERMISSIONS}>
          <Routes>
            <Route path="/staff" element={<StaffListProbe />} />
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

// Backlog-issues B6: an owner or manager sets a new password for someone from their page. The server
// already refused anyone more senior (G-4, G-5); there was simply no button.
describe('setting a new password for someone', () => {
  it('waits for ten characters, then sends only the new password', async () => {
    everythingLoaded();
    renderScreen();
    const user = userEvent.setup();

    const box = await screen.findByLabelText('New password');
    const set = screen.getByRole('button', { name: 'Set new password' });
    await user.type(box, 'short');
    expect(set).toBeDisabled();
    await user.type(box, '-enough-now');
    await user.click(set);

    await waitFor(() => {
      const call = vi
        .mocked(globalThis.fetch)
        .mock.calls.find(
          (args) =>
            ((args as unknown[])[0] as string).endsWith('/staff/employees/e1/password') &&
            (args as unknown[])[1] !== undefined,
        );
      expect(call).toBeDefined();
      const init = (call as unknown[])[1] as RequestInit;
      expect(JSON.parse(init.body as string)).toEqual({ new_password: 'short-enough-now' });
    });
  });
});

// Decision D14 (backlog-issues B12): adding someone ended on their page with nowhere to go.
describe('finishing an employee', () => {
  it('asks for a role after adding, then finishes back to the staff list naming it', async () => {
    everythingLoaded();
    renderScreen('/staff/e1?added=1');
    const user = userEvent.setup();

    expect(await screen.findByText('Now give Vikram Deshmukh a role')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Finish' }));

    expect(await screen.findByText('Vikram Deshmukh added as Manager')).toBeInTheDocument();
  });

  it('offers a way back when editing someone who already exists', async () => {
    everythingLoaded();
    renderScreen();

    expect(await screen.findByRole('link', { name: 'Back to staff' })).toHaveAttribute('href', '/staff');
  });
});
