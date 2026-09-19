// One dish, and the boundary the P1 design drew through it.
//
// `seed/organization.yaml` gives a manager `menu.manage` and withholds `menu.price` by name. The
// backend enforces that; this screen must not offer a control that will then 403, because a
// control that exists and fails reads as a bug in the product rather than as a boundary in it.
//
// The other thing asserted here is the FSSAI mark. It is legally required on an Indian menu, and
// it sits on the red-green axis — so it carries a label and a shape, not only a colour
// (`docs/ui/conventions.md`, restaurant-ui rule 5).

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthContext, type AuthState } from '@staff/auth/AuthContext';
import type { RestaurantSummary, Session } from '@staff/auth/session';

import MenuItemScreen from './MenuItemScreen';

const RESTAURANT: RestaurantSummary = {
  id: 'r1',
  name: 'Spice Garden',
  code: 'SG',
  timezone: 'Asia/Kolkata',
  currency: 'INR',
  business_day_start: '05:00:00',
  theme: { default: null, schedule: [] },
};

const DISH = {
  id: 'dish-1',
  menu_category_id: 'cat-1',
  code: 'BUTTER_CHICKEN',
  name: 'Butter Chicken',
  description: null,
  food_type: 'non_veg',
  station_id: 'st-1',
  image_url: null,
  seq: 0,
  is_active: true,
  // What the dish already has attached. The screen sends the whole set back on save, so this
  // is the value that stops a save from being a silent detach.
  modifier_group_ids: ['g-spice'],
  variants: [
    {
      id: 'v-full',
      code: 'FULL',
      name: 'Full',
      price: '470.00',
      tax_group_id: 'tg-1',
      prep_minutes: 11,
      seq: 0,
      is_active: true,
    },
  ],
};

const GROUPS = {
  items: [
    {
      id: 'g-spice',
      code: 'SPICE_LEVEL',
      name: 'Spice level',
      min_select: 0,
      max_select: 1,
      is_required: false,
      is_active: true,
      modifiers: [{ id: 'm-mild', code: 'MILD', name: 'Mild', price_delta: '0.00', seq: 0 }],
    },
    {
      id: 'g-addons',
      code: 'ADDONS',
      name: 'Add-ons',
      min_select: 0,
      max_select: 3,
      is_required: false,
      is_active: true,
      modifiers: [
        {
          id: 'm-paneer',
          code: 'EXTRA_PANEER',
          name: 'Extra paneer',
          price_delta: '30.00',
          seq: 0,
        },
      ],
    },
  ],
  next_cursor: null,
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function auth(permissions: string[]): AuthState {
  const held = new Set(permissions);
  return {
    session: {
      employeeId: 'e1',
      passwordChangeRequired: false,
      fullName: 'Vikram Deshmukh',
      employeeCode: 'EMP003',
      restaurant: RESTAURANT,
      restaurants: [RESTAURANT],
      hasMoreRestaurants: false,
      roles: ['manager'],
      permissions: held,
      takesTables: true,
    } satisfies Session,
    signIn: () => Promise.resolve(),
    signOut: () => Promise.resolve(),
    can: (permission: string) => held.has(permission),
  };
}

function renderScreen(permissions: string[]): void {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) =>
      Promise.resolve(url.includes('modifier-groups') ? json(GROUPS) : json(DISH)),
    ),
  );
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/menu/dish-1']}>
        <AuthContext.Provider value={auth(permissions)}>
          <Routes>
            <Route path="/menu/:itemId" element={<MenuItemScreen />} />
          </Routes>
        </AuthContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the price boundary', () => {
  it('offers no way to change a price without menu.price', async () => {
    // A manager: shapes the menu, does not price it.
    renderScreen(['menu.view', 'menu.manage']);
    await screen.findByText('Butter Chicken');

    expect(screen.queryByRole('button', { name: /change/i })).not.toBeInTheDocument();
  });

  it('says who can change it, rather than leaving a manager to guess', async () => {
    renderScreen(['menu.view', 'menu.manage']);

    expect(await screen.findByText(/menu.price permission/i)).toBeInTheDocument();
  });

  it('offers the control to someone holding menu.price', async () => {
    renderScreen(['menu.view', 'menu.manage', 'menu.price']);
    await screen.findByText('Butter Chicken');

    expect(screen.getByRole('button', { name: /change/i })).toBeInTheDocument();
  });

  it('still shows the price to someone who cannot change it', async () => {
    // Hiding it would be the wrong fix: a manager needs to read prices to run a shift.
    renderScreen(['menu.view', 'menu.manage']);

    expect(await screen.findByText('₹470.00')).toBeInTheDocument();
  });
});

describe('the dish', () => {
  it('renders the food-type mark with a label, not only a colour', async () => {
    // restaurant-ui rule 5, and the mark most worth getting right: red-green colour blindness is
    // exactly the axis veg/non-veg sits on.
    renderScreen(['menu.view']);

    expect(await screen.findByRole('img', { name: /non-vegetarian/i })).toBeInTheDocument();
  });

  // Replaced on 2026-09-19. This test used to assert the code was shown here, read-only, because
  // `menu_item.code` is the join key to the starter library and to every recipe M04 attaches.
  //
  // The owner removed codes from every browse and detail screen — *"every dish is mentioned twice,
  // name is okay, but the other thing should not be in ui"* — and asked for one page that lists
  // them instead. So the rule is now the opposite of what it was, and `/menu/codes` is the only
  // screen that shows one. `menuDiscipline.test.ts` holds that from the other side.
  it('does not show the database code beside the dish', async () => {
    renderScreen(['menu.view', 'menu.manage', 'menu.price']);
    await screen.findByText('Butter Chicken');

    expect(screen.queryByLabelText(/dish code/i)).toBeNull();
    expect(screen.queryByText('BUTTER_CHICKEN')).toBeNull();
  });

  it('formats the price with Indian grouping', async () => {
    renderScreen(['menu.view']);

    expect(await screen.findByText('₹470.00')).toBeInTheDocument();
  });
});

describe('the options a dish carries', () => {
  it('starts from what the dish already has, not from nothing', async () => {
    // Attachment is a PUT of the whole set. This screen opened with every switch off, so saving
    // any change at all detached every group the dish had — a 200, and the options were gone.
    renderScreen(['menu.view', 'menu.manage']);
    await screen.findByText('Butter Chicken');

    expect(screen.getByRole('switch', { name: /Spice level/ })).toBeChecked();
    expect(screen.getByRole('switch', { name: /Add-ons/ })).not.toBeChecked();
  });
});

describe('someone who may only read the menu', () => {
  it('is told so, once, instead of being shown forms that will be refused', async () => {
    // A waiter holds menu.view and nothing else.
    renderScreen(['menu.view']);

    expect(await screen.findByText(/read the menu but not change it/i)).toBeInTheDocument();
  });

  it('is offered no save button anywhere on the screen', async () => {
    renderScreen(['menu.view']);
    await screen.findByText('Butter Chicken');

    expect(screen.queryByRole('button', { name: /save/i })).not.toBeInTheDocument();
  });

  it('still sees the dish, because reading it is the job', async () => {
    renderScreen(['menu.view']);

    expect(await screen.findByText('Butter Chicken')).toBeInTheDocument();
    expect(screen.getByText('₹470.00')).toBeInTheDocument();
  });
});

// Backlog-issues B8: what a guest with an allergy, or a covered restaurant's menu, needs to say.
describe('what is in the dish', () => {
  it('saves the allergen statement, calories and serving size', async () => {
    renderScreen(['menu.view', 'menu.manage']);
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText('Allergens'), 'Milk, cashew');
    await user.type(screen.getByLabelText('Calories (kcal)'), '480');
    await user.type(screen.getByLabelText('Serving size'), '1 bowl (300 g)');
    await user.click(screen.getByRole('button', { name: /^save$/i }));

    await waitFor(() => {
      const call = vi
        .mocked(globalThis.fetch)
        .mock.calls.find(
          (args) => ((args as unknown[])[1] as RequestInit | undefined)?.method === 'PATCH',
        );
      const init = (call as unknown[] | undefined)?.[1] as RequestInit | undefined;
      expect(JSON.parse(init?.body as string)).toMatchObject({
        allergen_statement: 'Milk, cashew',
        calories_kcal: 480,
        serving_size: '1 bowl (300 g)',
      });
    });
  });
});
