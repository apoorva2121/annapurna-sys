// Signing in when one login belongs to two organizations (backlog-issues B4, D1a and D1b).
//
// **The question comes after the password.** Asked straight after the phone number, it would tell
// anyone holding that number which businesses its owner works at.
//
// **The last choice is ticked, not skipped.** Someone who works for two groups still sees where they
// are about to sign in, and it costs one tap.

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthContext, type AuthState } from '@staff/auth/AuthContext';
import { OrganizationChoiceNeeded } from '@staff/auth/session';

import LoginScreen from './LoginScreen';

const ORGANIZATIONS = [
  { id: 'o1', name: 'Spice Garden' },
  { id: 'o2', name: 'Tandoor House' },
];

function renderScreen(signIn: AuthState['signIn']): void {
  render(
    <MemoryRouter>
      <AuthContext.Provider
        value={{
          session: null,
          signIn,
          signOut: () => Promise.resolve(),
          can: () => false,
        }}
      >
        <LoginScreen />
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

async function signInAs(identifier: string, password: string): Promise<void> {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('Phone number or email'), identifier);
  await user.type(screen.getByLabelText('Password'), password);
  await user.click(screen.getByRole('button', { name: 'Sign in' }));
}

afterEach(() => {
  localStorage.clear();
});

describe('LoginScreen', () => {
  it('asks which hotel only after the password, then signs in to the one chosen', async () => {
    const signIn = vi
      .fn<AuthState['signIn']>()
      .mockRejectedValueOnce(new OrganizationChoiceNeeded('pass-1', ORGANIZATIONS))
      .mockResolvedValueOnce(undefined);
    renderScreen(signIn);
    const user = userEvent.setup();

    await signInAs('9876543210', 'Staging#2026');
    expect(await screen.findByText('Which hotel?')).toBeInTheDocument();
    await user.click(screen.getByRole('radio', { name: 'Tandoor House' }));
    await user.click(screen.getByRole('button', { name: 'Continue' }));

    expect(signIn).toHaveBeenLastCalledWith('9876543210', 'Staging#2026', {
      ticket: 'pass-1',
      organizationId: 'o2',
    });
    expect(localStorage.getItem('restaurant-os.last-organization')).toBe('o2');
  });

  it('ticks the hotel chosen last time on this device', async () => {
    localStorage.setItem('restaurant-os.last-organization', 'o2');
    const signIn = vi
      .fn<AuthState['signIn']>()
      .mockRejectedValueOnce(new OrganizationChoiceNeeded('pass-1', ORGANIZATIONS));
    renderScreen(signIn);

    await signInAs('9876543210', 'Staging#2026');

    expect(await screen.findByRole('radio', { name: 'Tandoor House' })).toBeChecked();
    expect(screen.getByRole('radio', { name: 'Spice Garden' })).not.toBeChecked();
  });
});
