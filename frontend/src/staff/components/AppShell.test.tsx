// The header, which is the only navigation present on every screen.
//
// M03 and M04 each shipped screens behind routes that nothing linked to — reachable only by typing
// a URL, which is to say not reachable. The home page lists them too, but the header is the fix
// that matters: a chef standing at the pass is already inside the app, and walking back to a
// landing page to reach the next screen is not how anybody works a shift.
//
// The other half is the absence. Navigation is built from permissions and never from a role name
// (ADR 0007), so a chef must not be offered Dish costs — `seed/organization.yaml` says a chef sees
// grams, not rupees, and a link that 403s reads as a broken product rather than as a boundary.

import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { AuthContext, type AuthState } from '@staff/auth/AuthContext';
import type { RestaurantSummary, Session } from '@staff/auth/session';
import { AppShell } from '@staff/components/AppShell';

const RESTAURANT: RestaurantSummary = {
  id: 'r1',
  name: 'Spice Garden',
  code: 'SG',
  timezone: 'Asia/Kolkata',
  currency: 'INR',
  business_day_start: '05:00:00',
  theme: { default: null, schedule: [] },
};

function renderFor(permissions: string[]): void {
  const held = new Set(permissions);
  const state: AuthState = {
    session: {
      employeeId: 'e1',
      passwordChangeRequired: false,
      fullName: 'Asha',
      employeeCode: 'E001',
      restaurant: RESTAURANT,
      restaurants: [RESTAURANT],
      roles: [],
      permissions: held,
    } satisfies Session,
    signIn: () => Promise.resolve(),
    signOut: () => Promise.resolve(),
    can: (permission: string) => held.has(permission),
  };
  render(
    <MemoryRouter>
      <AuthContext.Provider value={state}>
        <AppShell />
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

function hrefs(): string[] {
  return screen
    .getAllByRole('link')
    .map((link) => link.getAttribute('href') ?? '')
    .sort();
}

describe('the header navigation', () => {
  it('reaches the menu and the options screens with menu.view', () => {
    renderFor(['menu.view']);

    expect(hrefs()).toContain('/menu');
    expect(hrefs()).toContain('/menu/options');
  });

  it('reaches ingredients and recipes with recipe.view', () => {
    renderFor(['recipe.view']);

    expect(hrefs()).toContain('/stock');
  });

  it('reaches dish costs with cost.view', () => {
    renderFor(['cost.view']);

    expect(hrefs()).toContain('/costs');
  });

  it('offers a chef no way to dish costs, because a chef sees grams and not rupees', () => {
    renderFor(['menu.view', 'recipe.view', 'recipe.manage']);

    expect(hrefs()).not.toContain('/costs');
  });

  it('offers a manager the costs and not the recipe writes it does not hold', () => {
    // A manager holds cost.view and not recipe.manage. The stock screen is still theirs to read.
    renderFor(['menu.view', 'menu.manage', 'recipe.view', 'cost.view']);

    expect(hrefs()).toContain('/costs');
    expect(hrefs()).toContain('/stock');
  });

  it('reaches purchasing with supplier.view', () => {
    // M06 shipped five screens. Two of them belong in the header, because a store manager arrives
    // either to raise an order or to look up what a supplier owes them, and those are different
    // errands on different days.
    renderFor(['supplier.view']);

    expect(hrefs()).toContain('/purchasing/orders');
    expect(hrefs()).toContain('/purchasing/suppliers');
  });

  it('offers a chef no way into purchasing at all', () => {
    // A kitchen cannot book in a sack it then cooks, and the P1 design gives a chef none of the
    // three procurement permissions.
    renderFor(['menu.view', 'recipe.view', 'recipe.manage', 'stock.view', 'stock.produce']);

    expect(hrefs()).not.toContain('/purchasing/orders');
    expect(hrefs()).not.toContain('/purchasing/suppliers');
  });

  it('offers a waiter nothing but their own profile', () => {
    // menu.view is every staff role's, so a waiter does get the menu. Nothing else.
    renderFor(['menu.view']);

    expect(hrefs()).not.toContain('/staff');
    expect(hrefs()).not.toContain('/settings');
    expect(hrefs()).not.toContain('/stock');
    expect(hrefs()).not.toContain('/costs');
    expect(hrefs()).not.toContain('/purchasing/orders');
    expect(hrefs()).toContain('/profile');
  });
});
