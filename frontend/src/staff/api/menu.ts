import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';

import { apiGet, apiPatch, apiPost, apiPut } from '@shared/api';
import type { FoodType } from '@shared/ui/foodTypeMark';

/**
 * The menu surface.
 *
 * **Every amount is a string and stays one.** `price` and `price_delta` arrive as `"470.00"` and
 * are sent back the same way. Typing them as `number` here would be the single change that breaks
 * CLAUDE.md invariant 3 across the whole frontend, because TypeScript would then happily let
 * someone add two of them.
 *
 * **One key prefix for the whole surface.** Any mutation invalidates everything menu-related
 * without knowing which screens are mounted. These lists are small and change rarely, so the cost
 * of over-invalidating is a refetch nobody notices; the cost of under-invalidating is a screen
 * showing a dish that no longer exists.
 */

export type MenuCategory = {
  id: string;
  code: string;
  name: string;
  seq: number;
  is_active: boolean;
};

export type MenuVariant = {
  id: string;
  code: string;
  name: string;
  price: string;
  tax_group_id: string;
  prep_minutes: number;
  seq: number;
  is_active: boolean;
};

export type Modifier = {
  id: string;
  code: string;
  name: string;
  price_delta: string;
  is_active: boolean;
};

export type ModifierGroup = {
  id: string;
  code: string;
  name: string;
  min_select: number;
  max_select: number;
  is_required: boolean;
  is_active: boolean;
  modifiers: Modifier[];
};

export type MenuItem = {
  id: string;
  menu_category_id: string;
  code: string;
  name: string;
  description: string | null;
  food_type: FoodType;
  station_id: string;
  image_url: string | null;
  seq: number;
  is_active: boolean;
  variants: MenuVariant[];
};

type Page<T> = { items: T[]; next_cursor: string | null };

const MENU_KEY = ['staff', 'menu'] as const;

function useInvalidateMenu(): () => void {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: MENU_KEY });
  };
}

// --------------------------------------------------------------------------- categories

export function useMenuCategories(includeInactive = true): UseQueryResult<Page<MenuCategory>> {
  return useQuery({
    queryKey: [...MENU_KEY, 'categories', includeInactive],
    queryFn: () =>
      apiGet<Page<MenuCategory>>(`/staff/menu/categories?include_inactive=${String(includeInactive)}`),
  });
}

export function useCreateCategory(): UseMutationResult<
  MenuCategory,
  Error,
  { code: string; name: string }
> {
  const invalidate = useInvalidateMenu();
  return useMutation({
    mutationFn: (body) => apiPost<MenuCategory>('/staff/menu/categories', body),
    onSuccess: invalidate,
  });
}

export function useUpdateCategory(): UseMutationResult<
  MenuCategory,
  Error,
  { id: string; changes: Partial<Pick<MenuCategory, 'name' | 'seq' | 'is_active'>> }
> {
  const invalidate = useInvalidateMenu();
  return useMutation({
    mutationFn: ({ id, changes }) => apiPatch<MenuCategory>(`/staff/menu/categories/${id}`, changes),
    onSuccess: invalidate,
  });
}

/**
 * Swap two categories' positions in one mutation.
 *
 * One mutation and not two `mutate()` calls, for the reason M02 learned on the floor plan: two
 * calls on one observer report only the second, so a half-failed swap renders nothing and leaves
 * both rows on the same `seq`. The server-side atomic reorder is still backlogged; this keeps the
 * *reporting* honest in the meantime.
 */
export function useSwapCategorySeq(): UseMutationResult<
  void,
  Error,
  { category: MenuCategory; other: MenuCategory }
> {
  const invalidate = useInvalidateMenu();
  return useMutation({
    mutationFn: async ({ category, other }) => {
      await apiPatch<MenuCategory>(`/staff/menu/categories/${category.id}`, { seq: other.seq });
      await apiPatch<MenuCategory>(`/staff/menu/categories/${other.id}`, { seq: category.seq });
    },
    onSuccess: invalidate,
  });
}

// --------------------------------------------------------------------------- items

export function useMenuItems(
  categoryId: string | null,
  includeInactive = true,
): UseQueryResult<Page<MenuItem>> {
  return useQuery({
    queryKey: [...MENU_KEY, 'items', categoryId, includeInactive],
    queryFn: () =>
      apiGet<Page<MenuItem>>(
        `/staff/menu/items?include_inactive=${String(includeInactive)}` +
          (categoryId === null ? '' : `&category_id=${categoryId}`),
      ),
    enabled: categoryId !== null,
  });
}

/**
 * One dish, by id.
 *
 * A dedicated read rather than filtering the list: `useMenuItems` is keyed by category and is
 * disabled without one, so reusing it here meant the detail screen never fetched anything at all —
 * caught by `MenuItemScreen.test.tsx` before it could be caught by a person opening the screen.
 * Loading the whole menu to render one dish would also have been the wrong shape.
 */
export function useMenuItem(itemId: string | undefined): UseQueryResult<MenuItem> {
  return useQuery({
    queryKey: [...MENU_KEY, 'item', itemId],
    queryFn: () => apiGet<MenuItem>(`/staff/menu/items/${String(itemId)}`),
    enabled: itemId !== undefined,
  });
}

export type NewMenuItem = {
  menu_category_id: string;
  code: string;
  name: string;
  description?: string | null;
  food_type: FoodType;
  station_id: string;
  variants: {
    code: string;
    name: string;
    price: string;
    tax_group_id: string;
    prep_minutes: number;
  }[];
};

export function useCreateItem(): UseMutationResult<MenuItem, Error, NewMenuItem> {
  const invalidate = useInvalidateMenu();
  return useMutation({
    mutationFn: (body) => apiPost<MenuItem>('/staff/menu/items', body),
    onSuccess: invalidate,
  });
}

export function useUpdateItem(): UseMutationResult<
  MenuItem,
  Error,
  {
    id: string;
    changes: Partial<
      Pick<
        MenuItem,
        'name' | 'description' | 'food_type' | 'station_id' | 'menu_category_id' | 'is_active'
      >
    >;
  }
> {
  const invalidate = useInvalidateMenu();
  return useMutation({
    mutationFn: ({ id, changes }) => apiPatch<MenuItem>(`/staff/menu/items/${id}`, changes),
    onSuccess: invalidate,
  });
}

export function useUpdateVariant(): UseMutationResult<
  MenuItem,
  Error,
  { id: string; changes: Partial<Pick<MenuVariant, 'name' | 'price' | 'prep_minutes' | 'is_active'>> }
> {
  const invalidate = useInvalidateMenu();
  return useMutation({
    mutationFn: ({ id, changes }) => apiPatch<MenuItem>(`/staff/menu/variants/${id}`, changes),
    onSuccess: invalidate,
  });
}

export function useAddVariant(): UseMutationResult<
  MenuItem,
  Error,
  {
    itemId: string;
    body: { code: string; name: string; price: string; tax_group_id: string; prep_minutes: number };
  }
> {
  const invalidate = useInvalidateMenu();
  return useMutation({
    mutationFn: ({ itemId, body }) => apiPost<MenuItem>(`/staff/menu/items/${itemId}/variants`, body),
    onSuccess: invalidate,
  });
}

// --------------------------------------------------------------------------- modifiers

export function useModifierGroups(): UseQueryResult<Page<ModifierGroup>> {
  return useQuery({
    queryKey: [...MENU_KEY, 'modifier-groups'],
    queryFn: () => apiGet<Page<ModifierGroup>>('/staff/menu/modifier-groups'),
  });
}

export type NewModifierGroup = {
  code: string;
  name: string;
  min_select: number;
  max_select: number;
  is_required: boolean;
  modifiers: { code: string; name: string; price_delta: string }[];
};

export function useCreateModifierGroup(): UseMutationResult<
  ModifierGroup,
  Error,
  NewModifierGroup
> {
  const invalidate = useInvalidateMenu();
  return useMutation({
    mutationFn: (body) => apiPost<ModifierGroup>('/staff/menu/modifier-groups', body),
    onSuccess: invalidate,
  });
}

export function useUpdateModifierGroup(): UseMutationResult<
  ModifierGroup,
  Error,
  {
    id: string;
    changes: Partial<
      Pick<ModifierGroup, 'name' | 'min_select' | 'max_select' | 'is_required' | 'is_active'>
    >;
  }
> {
  const invalidate = useInvalidateMenu();
  return useMutation({
    mutationFn: ({ id, changes }) =>
      apiPatch<ModifierGroup>(`/staff/menu/modifier-groups/${id}`, changes),
    onSuccess: invalidate,
  });
}

export function useAddModifier(): UseMutationResult<
  ModifierGroup,
  Error,
  { groupId: string; body: { code: string; name: string; price_delta: string } }
> {
  const invalidate = useInvalidateMenu();
  return useMutation({
    mutationFn: ({ groupId, body }) =>
      apiPost<ModifierGroup>(`/staff/menu/modifier-groups/${groupId}/modifiers`, body),
    onSuccess: invalidate,
  });
}

export function useAttachModifierGroups(): UseMutationResult<
  MenuItem,
  Error,
  { itemId: string; modifierGroupIds: string[] }
> {
  const invalidate = useInvalidateMenu();
  return useMutation({
    mutationFn: ({ itemId, modifierGroupIds }) =>
      apiPut<MenuItem>(`/staff/menu/items/${itemId}/modifier-groups`, {
        modifier_group_ids: modifierGroupIds,
      }),
    onSuccess: invalidate,
  });
}

/** "All main courses get a spice level" — the shorthand an owner actually uses. */
export function useBulkAttach(): UseMutationResult<
  { items_updated: number },
  Error,
  { categoryId: string; modifierGroupIds: string[]; replace: boolean }
> {
  const invalidate = useInvalidateMenu();
  return useMutation({
    mutationFn: ({ categoryId, modifierGroupIds, replace }) =>
      apiPost<{ items_updated: number }>(`/staff/menu/categories/${categoryId}/modifier-groups`, {
        modifier_group_ids: modifierGroupIds,
        replace,
      }),
    onSuccess: invalidate,
  });
}
