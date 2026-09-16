// Owner defect sheet rows 19 and 20 (backlog-issues B12, D23): permissions in words, and an
// appearance section that says it is for this device only.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { AuthContext, type AuthState } from '@staff/auth/AuthContext';
import type { RestaurantSummary } from '@staff/auth/session';

import ProfileScreen from './ProfileScreen';

const RESTAURANT: RestaurantSummary = {
  id: 'r1',
  name: 'Spice Garden',
  code: 'SG',
  timezone: 'Asia/Kolkata',
  currency: 'INR',
  business_day_start: '05:00:00',
  theme: { default: null, schedule: [] },
};

function renderScreen(permissions: string[]): void {
  const auth: AuthState = {
    session: {
      employeeId: 'e1',
      passwordChangeRequired: false,
      fullName: 'Vikram Deshmukh',
      employeeCode: 'EMP003',
      restaurant: RESTAURANT,
      restaurants: [RESTAURANT],
      hasMoreRestaurants: false,
      roles: ['manager'],
      permissions: new Set(permissions),
    },
    signIn: () => Promise.resolve(),
    signOut: () => Promise.resolve(),
    can: (permission) => permissions.includes(permission),
  };
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <AuthContext.Provider value={auth}>
          <ProfileScreen />
        </AuthContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ProfileScreen', () => {
  it('says what a person can do in words, never as codes', () => {
    renderScreen(['cash.manage', 'cost.view']);

    expect(screen.getByText('Open and close the till, count the cash, and record payouts')).toBeInTheDocument();
    expect(screen.queryByText('cash.manage')).not.toBeInTheDocument();
  });

  it('says the appearance chosen here is for this device only', () => {
    renderScreen([]);

    expect(screen.getByRole('heading', { name: 'Appearance on this device' })).toBeInTheDocument();
  });
});
