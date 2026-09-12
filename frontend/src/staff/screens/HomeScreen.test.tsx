// The only way into the rest of the app, which is why it is tested at all.
//
// M02, M03 and M04 each shipped screens behind routes that nothing linked to. Every one worked
// perfectly if you typed its URL and did not exist if you did not — and no test noticed, because
// every screen test rendered its screen directly. These assert the doors, not the rooms.
//
// They also assert the *absence* of doors, which is the half that keeps the list honest: a chef
// sees ingredients and recipes and must not be offered dish costs, because `seed/organization.yaml`
// says a chef sees grams and not rupees. Offering a link that 403s reads as a broken product.

import { render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { AuthContext, type AuthState } from '@staff/auth/AuthContext';
import type { Session } from '@staff/auth/session';

import HomeScreen from './HomeScreen';

const RESTAURANT = {
  id: 'r1',
  name: 'Spice Garden',
  code: 'R1',
  timezone: 'Asia/Kolkata',
  theme: { default: null, schedule: [] },
};

function renderFor(permissions: string[]): void {
  const session = {
    employeeId: 'e1',
    passwordChangeRequired: false,
    fullName: 'Asha',
    employeeCode: 'E001',
    restaurant: RESTAURANT,
    restaurants: [RESTAURANT],
    roles: [],
    permissions: new Set(permissions),
  } as unknown as Session;
  const state: AuthState = {
    session,
    signIn: async () => {},
    signOut: async () => {},
    can: (permission: string) => session.permissions.has(permission),
  };
  const tree: ReactElement = (
    <MemoryRouter>
      <AuthContext.Provider value={state}>
        <HomeScreen />
      </AuthContext.Provider>
    </MemoryRouter>
  );
  render(tree);
}

function hrefs(): string[] {
  return screen
    .getAllByRole('link')
    .map((link) => link.getAttribute('href') ?? '')
    .sort();
}

describe('the staff home screen', () => {
  it('offers an owner every screen this app has', () => {
    renderFor([
      'employee.view',
      'restaurant.configure',
      'menu.view',
      'menu.manage',
      'menu.price',
      'recipe.view',
      'recipe.manage',
      'cost.view',
    ]);

    expect(hrefs()).toEqual([
      '/costs',
      '/menu',
      '/menu/options',
      '/profile',
      '/settings',
      '/staff',
      '/stock',
    ]);
  });

  it('offers a chef recipes and not rupees', () => {
    renderFor(['recipe.view', 'recipe.manage', 'menu.view']);

    expect(hrefs()).toEqual(['/menu', '/menu/options', '/profile', '/stock']);
  });

  it('offers a manager the costs but not the staff list', () => {
    renderFor(['menu.view', 'menu.manage', 'recipe.view', 'cost.view']);

    expect(hrefs()).toEqual(['/costs', '/menu', '/menu/options', '/profile', '/stock']);
  });

  it('tells someone with no permissions why the page is empty', () => {
    renderFor([]);

    expect(screen.queryAllByRole('link')).toHaveLength(0);
    expect(screen.getByText(/nothing has been assigned to you yet/i)).toBeInTheDocument();
  });
});
