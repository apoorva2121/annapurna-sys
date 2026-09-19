// The only way into the rest of the app, which is why it is tested at all.
//
// M02, M03 and M04 each shipped screens behind routes that nothing linked to. Every one worked
// perfectly if you typed its URL and did not exist if you did not — and no test noticed, because
// every screen test rendered its screen directly. These assert the doors, not the rooms.
//
// They also assert the *absence* of doors, which is the half that keeps the list honest: a chef
// sees ingredients and recipes and must not be offered dish costs, because `seed/organization.yaml`
// says a chef sees grams and not rupees. Offering a link that 403s reads as a broken product.
//
// **Rewritten 2026-09-19.** This page used to list eighteen screens, eight of which were also in
// the header — the owner's report: *"the options that are present at the top they should not be
// repeated below … that is redundant."* The header and this page are now one partition of one
// list (`navigation.ts`), so the expectations below are shorter by exactly those eight. Menu,
// recipes, dish costs, reports, staff, settings and the profile moved to the header, which is on
// every screen; this page keeps the ten that were only ever here.

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
    hasMoreRestaurants: false,
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
  // `queryAllByRole`, not `getAllByRole`: "no links at all" is now a real and correct outcome —
  // somebody whose screens all live in the header lands here and finds nothing — and `getAllBy`
  // throws rather than returning an empty array.
  return screen
    .queryAllByRole('link')
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
      'stock.view',
      'stock.receive',
      'stock.produce',
      'stock.count',
      'kot.view',
      'wastage.log',
      'report.operational.view',
    ]);

    // Ten, not eighteen: the other eight are in the header and no longer repeated here.
    expect(hrefs()).toEqual([
      '/kitchen',
      '/stock/count',
      '/stock/on-hand',
      '/stock/produce',
      '/stock/receive',
      '/waste',
      '/waste/summary',
    ]);
  });

  it('offers a chef the batch he makes and not the delivery he does not sign for', () => {
    // The grant that carries the most meaning in M05, visible at the level a person experiences
    // it: the chef's home screen has "Make a batch" on it and no way to record a delivery.
    // M09 adds two: a chef logs waste (`wastage.log`) and sees the summary (`stock.view`), and
    // still cannot approve it — approval is a manager's, which is the separation of duties the
    // module's whole control rests on.
    renderFor(['stock.view', 'stock.produce', 'wastage.log']);

    expect(hrefs()).toEqual(['/stock/on-hand', '/stock/produce', '/waste', '/waste/summary']);
  });

  it('offers kitchen staff the shelf and nothing that changes it', () => {
    // `stock.view` alone is what `seed/organization.yaml` grants kitchen_staff. Seeing what is on
    // the shelf is the job; changing what the book says it is, is not — and the home screen is
    // where that boundary first becomes visible to the person holding it.
    // `stock.view` alone now also opens the waste *summary* — reading what was thrown away is
    // seeing the shelf's history, not changing it. Logging still needs `wastage.log`.
    renderFor(['stock.view']);

    expect(hrefs()).toEqual(['/stock/on-hand', '/waste/summary']);
  });

  // Menu, recipes and dish costs are header screens now, so a chef holding only those reaches
  // this page and finds nothing on it — correct, and the reason the empty state below matters more
  // than it used to. The chef-sees-grams-not-rupees boundary moved with them and is asserted in
  // `AppShell.test.tsx`, which is where those links now live.
  it('offers nothing to somebody whose screens are all in the header', () => {
    renderFor(['menu.view', 'menu.manage', 'recipe.view', 'cost.view']);

    expect(hrefs()).toEqual([]);
  });

  it('tells someone with no permissions why the page is empty', () => {
    renderFor([]);

    expect(screen.queryAllByRole('link')).toHaveLength(0);
    expect(screen.getByText(/nothing has been assigned to you yet/i)).toBeInTheDocument();
  });
});
