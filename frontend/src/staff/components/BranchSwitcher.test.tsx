// The branch switcher, and the case where it must not appear at all.
//
// Almost everyone works at one restaurant. A switcher offering a single option is a control that
// does nothing, and controls that do nothing teach people to stop reading controls — so the
// interesting assertion here is the negative one.
//
// What is deliberately *not* tested here is whether a person may switch. That is a tenant boundary,
// it is decided by the server, and it is tested against a two-organization fixture in
// `backend/tests/test_auth_switch.py`. A test here could only assert what this component was handed.

import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthContext, type AuthState } from '@staff/auth/AuthContext';
import type { RestaurantSummary, Session } from '@staff/auth/session';

import { BranchSwitcher } from './BranchSwitcher';

function restaurant(id: string, name: string): RestaurantSummary {
  return {
    id,
    name,
    code: id.toUpperCase(),
    timezone: 'Asia/Kolkata',
    currency: 'INR',
    business_day_start: '05:00:00',
    theme: { default: null, schedule: [] },
  };
}

const KOREGAON = restaurant('r1', 'Spice Garden - Koregaon Park');
const BANER = restaurant('r2', 'Spice Garden - Baner');

function authWith(restaurants: RestaurantSummary[]): AuthState {
  return {
    session: {
      employeeId: 'e1',
      passwordChangeRequired: false,
      fullName: 'Priya Nair',
      employeeCode: 'EMP001',
      restaurant: restaurants[0] ?? KOREGAON,
      restaurants,
      roles: ['owner'],
      permissions: new Set<string>(),
    } satisfies Session,
    signIn: () => Promise.resolve(),
    signOut: () => Promise.resolve(),
    can: () => true,
  };
}

function renderWith(restaurants: RestaurantSummary[]): void {
  render(
    <AuthContext.Provider value={authWith(restaurants)}>
      <BranchSwitcher />
    </AuthContext.Provider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the branch switcher', () => {
  it('does not appear for someone who works at one restaurant', () => {
    renderWith([KOREGAON]);

    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });

  it('appears for someone who works at two', () => {
    renderWith([KOREGAON, BANER]);

    expect(screen.getByRole('combobox')).toBeInTheDocument();
  });

  it('shows the branch the session is currently at', () => {
    renderWith([KOREGAON, BANER]);

    expect(screen.getByRole('combobox')).toHaveTextContent('Koregaon Park');
  });

  it('survives a session the server sent no branch list for', () => {
    // Deploy skew: the app and the API are briefly different versions. `session.restaurants` is
    // filled in by the session mapper precisely so this component cannot read `.length` of
    // undefined and take the whole signed-in app down with it.
    render(
      <AuthContext.Provider
        value={{ ...authWith([KOREGAON]), session: { ...authWith([]).session } as Session }}
      >
        <BranchSwitcher />
      </AuthContext.Provider>,
    );

    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });
});
