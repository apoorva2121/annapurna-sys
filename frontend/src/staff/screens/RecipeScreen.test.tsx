// The chef's screen, and the three things it must never get wrong.
//
// 1. **No rupees.** `seed/organization.yaml` gives a chef `recipe.manage` and withholds `cost.view`
//    by name — "a chef sees grams, not rupees". The API already strips the price from a chef's copy
//    of every row; a screen that put one back would be asking for the boundary to be removed.
// 2. **No recipe is not an empty recipe.** A dish with no recipe is uncosted; a dish with an empty
//    one costs zero. The cost screen depends on those never collapsing into each other, so the
//    editor opens empty on a 404 and says so.
// 3. **An unchecked recipe says so.** `library/PROVENANCE.md` is explicit that most of the starter
//    library is estimated.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthContext, type AuthState } from '@staff/auth/AuthContext';
import type { RestaurantSummary, Session } from '@staff/auth/session';

import RecipeScreen from './RecipeScreen';
import { type Draft, problemWith } from './recipeLine';

const RESTAURANT: RestaurantSummary = {
  id: 'r1',
  name: 'Spice Garden',
  code: 'SG',
  timezone: 'Asia/Kolkata',
  currency: 'INR',
  business_day_start: '05:00:00',
  theme: { default: null, schedule: [] },
};

const ITEMS = {
  items: [
    {
      id: 'paneer',
      kind: 'ingredient',
      code: 'PANEER',
      name: 'Paneer',
      base_unit: 'g',
      category: 'dairy',
      storage_type: 'chilled',
      is_active: true,
      ingredient: null,
      preparation: null,
    },
    {
      id: 'gravy',
      kind: 'preparation',
      code: 'PREP_MAKHANI',
      name: 'Makhani gravy',
      base_unit: 'ml',
      category: null,
      storage_type: null,
      is_active: true,
      ingredient: null,
      preparation: null,
    },
  ],
  next_cursor: null,
};

/** As a chef receives it: lines and versions, and no `unit_cost` anywhere. */
const RECIPE = {
  id: 'rec-1',
  menu_item_variant_id: 'v-full',
  produces_stock_item_id: null,
  modifier_id: null,
  version: 2,
  is_current: true,
  effective_from: '2026-09-01T00:00:00Z',
  notes: null,
  source: 'library',
  confirmed_at: null,
  lines: [{ component_id: 'paneer', quantity: '200.0000', seq: 0 }],
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
      fullName: 'Ramesh Iyer',
      employeeCode: 'EMP004',
      restaurant: RESTAURANT,
      restaurants: [RESTAURANT],
      hasMoreRestaurants: false,
      roles: ['chef'],
      permissions: held,
    } satisfies Session,
    signIn: () => Promise.resolve(),
    signOut: () => Promise.resolve(),
    can: (permission: string) => held.has(permission),
  };
}

function renderScreen(
  permissions: string[],
  { recipe = RECIPE }: { recipe?: unknown } = {},
): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url.includes('/recipe') && (init?.method ?? 'GET') === 'GET') {
      return Promise.resolve(
        recipe === null
          ? json({ code: 'recipe.not_found', message: 'That dish has no recipe yet.' }, 404)
          : json(recipe),
      );
    }
    if (url.includes('/recipes')) {
      return Promise.resolve(json(RECIPE, 201));
    }
    return Promise.resolve(json(ITEMS));
  });
  vi.stubGlobal('fetch', fetchMock);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/recipes/v-full']}>
        <AuthContext.Provider value={auth(permissions)}>
          <Routes>
            <Route path="/recipes/:variantId" element={<RecipeScreen />} />
          </Routes>
        </AuthContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

const CHEF = ['recipe.view', 'recipe.manage'];

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('what a chef sees', () => {
  it('shows each line in the unit that line is measured in', async () => {
    renderScreen(CHEF);

    expect(await screen.findByText('Paneer')).toBeInTheDocument();
    // The quantity is an editable field, and the unit sits beside it rather than inside it — a
    // number with no unit next to it is the easiest way there is to put 200 kg of paneer in a dish.
    expect(screen.getByLabelText('Quantity of Paneer')).toHaveValue('200.0000');
    expect(screen.getByRole('cell', { name: /g$/ })).toBeInTheDocument();
  });

  it('lets a chef correct a quantity in place', async () => {
    // The first version of this screen offered only Add and Remove, so changing 200 g to 180 g
    // meant deleting the line and retyping it — on the screen whose whole job is a chef correcting
    // library quantities during onboarding.
    const user = userEvent.setup();
    renderScreen(CHEF);
    const field = await screen.findByLabelText('Quantity of Paneer');

    await user.clear(field);
    await user.type(field, '180');

    expect(field).toHaveValue('180');
  });

  it('shows no rupee figure anywhere', async () => {
    renderScreen(CHEF);
    await screen.findByText('Paneer');

    expect(screen.queryByText(/₹/)).not.toBeInTheDocument();
  });

  it('says nobody has checked a recipe that came from the library', async () => {
    renderScreen(CHEF);

    expect(await screen.findByText(/Nobody has checked these quantities/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Confirm these quantities/i })).toBeInTheDocument();
  });

  it('does not ask for confirmation once a chef has given it', async () => {
    renderScreen(CHEF, { recipe: { ...RECIPE, confirmed_at: '2026-09-10T00:00:00Z' } });

    expect(await screen.findByText(/Confirmed by a chef/i)).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /Confirm these quantities/i }),
    ).not.toBeInTheDocument();
  });
});

describe('a dish with no recipe', () => {
  it('opens empty and invites the first ingredient, rather than erroring', async () => {
    // 404 here is an answer, not a failure — and it is a different answer from an empty recipe,
    // which would cost zero.
    renderScreen(CHEF, { recipe: null });

    expect(await screen.findByText(/No recipe yet/i)).toBeInTheDocument();
  });
});

describe('the rule for adding a line', () => {
  // Tested directly rather than through the picker: Radix's Select needs a real pointer, and jsdom
  // has none (see `shared/test-setup.ts`). The rule is the part with the bugs in it, and it is pure.
  const existing: Draft[] = [{ component_id: 'paneer', quantity: '200.0000' }];

  it('refuses the same item twice, because the server would refuse it as a 500', () => {
    // `recipe_line`'s primary key is (recipe_id, component_id). A repeat reaches the database as an
    // IntegrityError, which is unmapped, which is a 500 with nothing a person can act on.
    expect(problemWith('paneer', '50', existing)).toMatch(/already on the recipe/i);
  });

  it('refuses a quantity of zero before it reaches the database CHECK', () => {
    expect(problemWith('gravy', '0', existing)).toMatch(/greater than zero/i);
  });

  it('refuses the things that are not quantities at all', () => {
    expect(problemWith('gravy', '', existing)).toMatch(/greater than zero/i);
    expect(problemWith('gravy', '1e3', existing)).toMatch(/greater than zero/i);
    expect(problemWith('gravy', '-5', existing)).toMatch(/greater than zero/i);
  });

  it('refuses a line with nothing chosen', () => {
    expect(problemWith('', '50', existing)).toMatch(/Choose an ingredient/i);
  });

  it('allows four decimal places, because 0.05 g of saffron is a real line', () => {
    expect(problemWith('gravy', '0.0500', existing)).toBeNull();
  });
});

describe('saving', () => {
  it('sends every line, because a save makes a new version rather than editing one', async () => {
    const user = userEvent.setup();
    const fetchMock = renderScreen(CHEF);
    await screen.findByText('Paneer');

    await user.click(screen.getByRole('button', { name: /Save this recipe/i }));

    await waitFor(() => {
      const posted = fetchMock.mock.calls.find(
        (call) => (call[1] as RequestInit | undefined)?.method === 'POST',
      );
      expect(posted).toBeDefined();
      // `body` is typed as BodyInit, which includes Blob and streams; this call site always
      // sends a JSON string, so narrowing rather than stringifying is the honest read.
      const sent = (posted?.[1] as RequestInit | undefined)?.body;
      const body = JSON.parse(typeof sent === 'string' ? sent : '{}') as {
        menu_item_variant_id: string;
        lines: { component_id: string; quantity: string }[];
      };
      expect(body.menu_item_variant_id).toBe('v-full');
      expect(body.lines).toEqual([{ component_id: 'paneer', quantity: '200.0000' }]);
    });
  });

  it('refuses to save an empty recipe, which is not the same as having none', async () => {
    const user = userEvent.setup();
    const fetchMock = renderScreen(CHEF, { recipe: null });
    await screen.findByText(/No recipe yet/i);

    await user.click(screen.getByRole('button', { name: /Save this recipe/i }));

    expect(await screen.findByText(/needs at least one ingredient/i)).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some((call) => (call[1] as RequestInit | undefined)?.method === 'POST'),
    ).toBe(false);
  });
});

describe('confirming', () => {
  it('will not certify a version while the draft has unsaved edits', async () => {
    // `confirmed_at` is what the dish-cost screen reads to decide whether a cost is a proposal or
    // a fact. A chef who changed three quantities and pressed Confirm would have marked the *old*
    // numbers as checked — certifying the wrong version is worse than certifying nothing.
    const user = userEvent.setup();
    renderScreen(CHEF);
    const field = await screen.findByLabelText('Quantity of Paneer');

    await user.clear(field);
    await user.type(field, '180');

    expect(screen.getByRole('button', { name: /Confirm these quantities/i })).toBeDisabled();
    expect(await screen.findByText(/Save your changes before confirming/i)).toBeInTheDocument();
  });

  it('is offered on an untouched recipe, which is the normal case', async () => {
    renderScreen(CHEF);
    await screen.findByText('Paneer');

    expect(screen.getByRole('button', { name: /Confirm these quantities/i })).toBeEnabled();
  });
});

describe('saving', () => {
  it('refuses a line whose quantity was edited down to nothing', async () => {
    // Checked again at save time and not only when a line is added, because quantities are now
    // editable in place: a line that was valid when added can be blank by the time Save is pressed.
    const user = userEvent.setup();
    const fetchMock = renderScreen(CHEF);
    const field = await screen.findByLabelText('Quantity of Paneer');

    await user.clear(field);
    await user.click(screen.getByRole('button', { name: /Save this recipe/i }));

    expect(await screen.findByText(/greater than zero/i)).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some((call) => (call[1] as RequestInit | undefined)?.method === 'POST'),
    ).toBe(false);
  });
});

describe('someone who may only read recipes', () => {
  it('is told so, and offered no way to change anything', async () => {
    // Kitchen staff and the store manager hold `recipe.view` and not `recipe.manage`.
    renderScreen(['recipe.view']);

    expect(await screen.findByText(/read recipes but not change them/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Save this recipe/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Add$/ })).not.toBeInTheDocument();
  });

  it('still sees the quantities, because reading them is the job', async () => {
    renderScreen(['recipe.view']);

    expect(await screen.findByText('Paneer')).toBeInTheDocument();
  });
});
