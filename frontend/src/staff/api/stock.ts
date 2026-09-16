import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';

import { ApiClientError, apiGet, apiPost } from '@shared/api';

/**
 * Stock items, recipes and cost.
 *
 * **Every quantity is a string, not only every price.** A recipe line can be `0.05` g of saffron,
 * and typing these as `number` would let someone add two of them — which is the single change that
 * breaks CLAUDE.md invariant 3 across the frontend. Quantities go through the same rule as money
 * because the cost is the product of the two.
 *
 * **There is no recipe update hook**, because the API has no recipe update endpoint. A change is a
 * new version, and `useSaveRecipeVersion` is both "create" and "change" — deliberately one function,
 * so there is no path that could quietly become an edit.
 */

export type IngredientProfile = {
  purchase_unit: string;
  purchase_to_base: string;
  yield_factor: string;
  shelf_life_days: number;
  reorder_level: string | null;
  reorder_quantity: string | null;
};

export type PreparationProfile = {
  batch_yield: string;
  shelf_life_hours: number;
  station_id: string;
  prep_minutes: number;
};

export type StockItem = {
  id: string;
  kind: 'ingredient' | 'preparation';
  code: string;
  name: string;
  base_unit: 'g' | 'ml' | 'unit';
  category: string | null;
  storage_type: string | null;
  /** **Present only for a `cost.view` holder.** The API serialises a stock item at the caller's
   *  pay grade: `seed/organization.yaml` says a chef sees grams and not rupees, so the price is
   *  absent from a chef's copy of this row rather than zeroed. Optional here for the same reason —
   *  a required field would make the type lie about what a chef receives. */
  current_unit_cost?: string;
  is_active: boolean;
  ingredient: IngredientProfile | null;
  preparation: PreparationProfile | null;
};

export type RecipeLine = {
  component_id: string;
  quantity: string;
  seq: number;
};

export type Recipe = {
  id: string;
  menu_item_variant_id: string | null;
  produces_stock_item_id: string | null;
  modifier_id: string | null;
  version: number;
  is_current: boolean;
  effective_from: string;
  notes: string | null;
  /** Present only for a `cost.view` holder, like `StockItem.current_unit_cost`. */
  unit_cost?: string;
  source: 'typed' | 'seeded' | 'library';
  confirmed_at: string | null;
  lines: RecipeLine[];
};

export type CostedLine = {
  component_id: string;
  code: string;
  quantity: string;
  unit_cost: string;
  cost: string;
};

export type DishCost = {
  menu_item_variant_id: string;
  cost: string;
  price: string;
  food_cost_percent: string | null;
  margin: string;
  lines: CostedLine[];
  has_recipe: boolean;
};

export type MenuCostRow = {
  menu_item_id: string;
  menu_item_name: string;
  menu_item_variant_id: string;
  variant_name: string;
  cost: string;
  price: string;
  food_cost_percent: string | null;
  margin: string;
  has_recipe: boolean;
  recipe_confirmed: boolean;
};

export type MenuCosts = {
  rows: MenuCostRow[];
  average_food_cost_percent: string | null;
  uncosted: number;
};

export type UsedBy = {
  preparations: StockItem[];
  dishes: string[];
  dish_names: string[];
};

type Page<T> = { items: T[]; next_cursor: string | null };

const STOCK_KEY = ['staff', 'stock'] as const;

function useInvalidateStock(): () => void {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: STOCK_KEY });
  };
}

export function useStockItems(
  kind?: 'ingredient' | 'preparation',
): UseQueryResult<Page<StockItem>> {
  return useQuery({
    queryKey: [...STOCK_KEY, 'items', kind ?? 'all'],
    queryFn: () =>
      apiGet<Page<StockItem>>(
        `/staff/stock-items?limit=100${kind === undefined ? '' : `&kind=${kind}`}`,
      ),
  });
}

export function useUsedBy(itemId: string | null): UseQueryResult<UsedBy> {
  return useQuery({
    queryKey: [...STOCK_KEY, 'used-by', itemId],
    queryFn: () => apiGet<UsedBy>(`/staff/stock-items/${String(itemId)}/used-by`),
    enabled: itemId !== null,
  });
}

export function useMenuCosts(): UseQueryResult<MenuCosts> {
  return useQuery({
    queryKey: [...STOCK_KEY, 'menu-costs'],
    queryFn: () => apiGet<MenuCosts>('/staff/menu/costs'),
  });
}

export function useDishCost(variantId: string | null): UseQueryResult<DishCost> {
  return useQuery({
    queryKey: [...STOCK_KEY, 'cost', variantId],
    queryFn: () => apiGet<DishCost>(`/staff/menu-variants/${String(variantId)}/cost`),
    enabled: variantId !== null,
  });
}

/**
 * The recipe currently in force for a dish variant, or `null` when it has none.
 *
 * **404 is an answer here, not a failure.** A dish with no recipe is the normal starting state and
 * the editor opens empty on it — while a dish with an *empty* recipe would cost zero, which is a
 * different and much worse claim. The two must never collapse into each other.
 */
export function useCurrentRecipe(variantId: string | undefined): UseQueryResult<Recipe | null> {
  return useQuery({
    queryKey: [...STOCK_KEY, 'recipe', 'variant', variantId],
    queryFn: async () => {
      try {
        return await apiGet<Recipe>(`/staff/menu-variants/${String(variantId)}/recipe`);
      } catch (error) {
        // On the code, never the status — `shared/api.ts` is explicit that `code` is the stable
        // contract and the HTTP status is not. A 404 from a proxy is a different thing entirely
        // from the server saying this dish has no recipe, and only one of them means "start empty".
        if (error instanceof ApiClientError && error.code === 'recipe.not_found') {
          return null;
        }
        throw error;
      }
    },
    enabled: variantId !== undefined,
  });
}

export type NewRecipeVersion = {
  menu_item_variant_id?: string;
  produces_stock_item_id?: string;
  lines: { component_id: string; quantity: string }[];
  notes?: string | null;
  confirmed?: boolean;
};

/** Create *or* change a recipe. One function, because the API has one operation. */
export function useSaveRecipeVersion(): UseMutationResult<Recipe, Error, NewRecipeVersion> {
  const invalidate = useInvalidateStock();
  return useMutation({
    mutationFn: (body) => apiPost<Recipe>('/staff/recipes', body),
    onSuccess: invalidate,
  });
}

export function useConfirmRecipe(): UseMutationResult<Recipe, Error, { id: string }> {
  const invalidate = useInvalidateStock();
  return useMutation({
    mutationFn: ({ id }) => apiPost<Recipe>(`/staff/recipes/${id}/confirm`, {}),
    onSuccess: invalidate,
  });
}
