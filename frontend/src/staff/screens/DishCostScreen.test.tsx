// The day-1 screen, and the two things it must never say.
//
// A dish with no recipe must not read "₹0.00" — that is a dish that is free to make, which is the
// opposite of what an uncosted dish means. And a cost computed from a recipe nobody has checked
// must say so: `library/PROVENANCE.md` is explicit that most of the starter library is `estimated`,
// so presenting a matched recipe's cost like a chef-written one states a number nobody has earned.
//
// The third thing asserted here is the order. Somebody opening this screen is looking for the dish
// that is losing money, not reading an alphabetical list.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import DishCostScreen from './DishCostScreen';

const COSTS = {
  rows: [
    {
      menu_item_id: 'i1',
      menu_item_name: 'Chilli Paneer',
      menu_item_variant_id: 'v1',
      variant_name: 'Full',
      cost: '124.20',
      price: '270.00',
      food_cost_percent: '46.0',
      margin: '145.80',
      has_recipe: true,
      recipe_confirmed: true,
    },
    {
      menu_item_id: 'i2',
      menu_item_name: 'Butter Chicken',
      menu_item_variant_id: 'v2',
      variant_name: 'Full',
      cost: '126.70',
      price: '470.00',
      food_cost_percent: '27.0',
      margin: '343.30',
      has_recipe: true,
      // Matched from the library, never checked by a chef.
      recipe_confirmed: false,
    },
    {
      menu_item_id: 'i3',
      menu_item_name: 'New Special',
      menu_item_variant_id: 'v3',
      variant_name: 'Full',
      cost: '0.00',
      price: '300.00',
      food_cost_percent: null,
      margin: '0.00',
      has_recipe: false,
      recipe_confirmed: false,
    },
  ],
  average_food_cost_percent: '36.5',
  uncosted: 1,
};

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

function renderScreen(): void {
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(json(COSTS))));
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <DishCostScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('what the screen must not say', () => {
  it('shows "No recipe" for an uncosted dish, never ₹0.00', async () => {
    renderScreen();
    await screen.findByText('New Special');

    const row = screen.getByText('New Special').closest('tr');
    expect(row).not.toBeNull();
    expect(within(row as HTMLElement).getByText(/no recipe/i)).toBeInTheDocument();
    expect(within(row as HTMLElement).queryByText('₹0.00')).not.toBeInTheDocument();
  });

  it('labels a cost that rests on a recipe nobody has confirmed', async () => {
    renderScreen();
    await screen.findByText('Butter Chicken');

    const row = screen.getByText('Butter Chicken').closest('tr');
    expect(within(row as HTMLElement).getByText(/unconfirmed/i)).toBeInTheDocument();
  });

  it('does not label a confirmed recipe', async () => {
    renderScreen();
    await screen.findByText('Chilli Paneer');

    const row = screen.getByText('Chilli Paneer').closest('tr');
    expect(within(row as HTMLElement).queryByText(/unconfirmed/i)).not.toBeInTheDocument();
  });
});

describe('what the screen is for', () => {
  it('puts the dish losing the most money first', async () => {
    renderScreen();
    await screen.findByText('Chilli Paneer');

    const names = screen
      .getAllByRole('row')
      .slice(1)
      .map((row) => row.textContent ?? '');
    expect(names[0]).toContain('Chilli Paneer');
  });

  it('flags a high food cost in a word, not only a colour', async () => {
    // restaurant-ui rule 5. 46% is well past the ~26% the seed targets.
    renderScreen();
    await screen.findByText('Chilli Paneer');

    const row = screen.getByText('Chilli Paneer').closest('tr');
    expect(within(row as HTMLElement).getByText('High')).toBeInTheDocument();
  });

  it('does not flag a dish inside the normal range', async () => {
    renderScreen();
    await screen.findByText('Butter Chicken');

    const row = screen.getByText('Butter Chicken').closest('tr');
    expect(within(row as HTMLElement).queryByText('High')).not.toBeInTheDocument();
  });

  it('formats every rupee figure with Indian grouping', async () => {
    renderScreen();

    expect(await screen.findByText('₹470.00')).toBeInTheDocument();
    expect(screen.getByText('₹126.70')).toBeInTheDocument();
  });

  it('says how many dishes have no recipe at all', async () => {
    // The number an owner acts on second: a menu with uncosted dishes has a margin figure that is
    // only true of part of it.
    renderScreen();

    expect(await screen.findByText('Without a recipe')).toBeInTheDocument();
  });
});
