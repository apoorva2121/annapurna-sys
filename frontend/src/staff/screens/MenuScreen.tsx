import { type FormEvent, type ReactElement, useState } from 'react';

import { formatINR } from '@shared/money';
import { Button } from '@shared/ui/button';
import { FoodTypeMark } from '@shared/ui/foodTypeMark';
import { Label } from '@shared/ui/label';
import { Switch } from '@shared/ui/switch';
import { Field } from '@staff/components/Field';
import { Notice } from '@staff/components/Notice';
import { QueryState } from '@staff/components/QueryState';
import { errorProps, fieldErrors } from '@staff/components/errorProps';
import { suffixedCode } from '@staff/codeFromName';
import { strings } from '@staff/strings';
import {
  type MenuCategory,
  type MenuItem,
  useCreateCategory,
  useMenuCategories,
  useMenuItems,
  useReorderCategories,
} from '@staff/api/menu';

/**
 * The menu: categories, and the dishes in them.
 *
 * **Two lists and a detail pane, not a tree widget.** The data is three levels deep and the
 * interaction deliberately is not — this is exactly `FloorPlanScreen`'s shape (areas → tables),
 * reused because it already works with a glove and a steamed-up screen and because reaching for a
 * tree library here would be the signal that the design went wrong. Categories on the left,
 * dishes in the selected category on the right, one dish open at a time.
 *
 * **Reordering is buttons, not drag** — the same deviation M02 recorded in `docs/backlog.md`, for
 * the same reasons: drag needs a library plus a keyboard path, and the buttons *are* the keyboard
 * path.
 *
 * **Prices are shown but not edited here.** Editing one needs `menu.price`, which a manager does
 * not hold (`seed/organization.yaml`'s P1 design withholds it by name), and a control that appears
 * and then 403s is worse than one that was never there. `MenuItemScreen` renders it conditionally.
 */
export default function MenuScreen(): ReactElement {
  const [showInactive, setShowInactive] = useState(false);
  const categories = useMenuCategories(showInactive);
  const [selected, setSelected] = useState<string | null>(null);
  // Lifted to the screen, not per row: one in-flight reorder has to disable *every* row's arrows.
  // Held per row, the neighbour's buttons stayed live and a second swap could interleave with the
  // first (M02, FloorPlanScreen).
  const swap = useReorderCategories();

  const items = categories.data?.items ?? [];
  // Reconciled against what is actually on screen. A category can leave this list while still
  // being selected — deactivate it, or turn the filter off — and a selection pointing at a row
  // nobody can see leaves the dishes below attributed to a section the screen no longer shows.
  const current = items.some((category) => category.id === selected)
    ? selected
    : (items[0]?.id ?? null);

  return (
    <div className="space-y-page">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold">{strings.menu.title}</h1>
        <div className="flex items-center gap-2">
          <Switch
            id="menu-show-inactive"
            checked={showInactive}
            onCheckedChange={setShowInactive}
          />
          <Label htmlFor="menu-show-inactive">{strings.menu.showInactive}</Label>
        </div>
      </div>

      <p className="text-sm text-muted-foreground">{strings.menu.neverDeleted}</p>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">{strings.menu.categoriesTitle}</h2>
        <QueryState
          isPending={categories.isPending}
          error={categories.error}
          pendingLabel={strings.menu.categoriesTitle}
        >
          {items.length === 0 ? (
            <p className="text-muted-foreground">{strings.menu.categoriesEmpty}</p>
          ) : (
            <ul className="divide-y rounded-md border">
              {items.map((category, index) => (
                <CategoryRow
                  key={category.id}
                  category={category}
                  isFirst={index === 0}
                  isLast={index === items.length - 1}
                  previous={items[index - 1]}
                  next={items[index + 1]}
                  isSelected={category.id === current}
                  swap={swap}
                  order={items.map((row) => row.id)}
                  onSelect={() => {
                    setSelected(category.id);
                  }}
                />
              ))}
            </ul>
          )}
        </QueryState>
        {swap.isError && <Notice tone="critical" {...errorProps(swap.error)} />}
        <AddCategory existing={items.map((category) => category.code)} />
      </section>

      {current !== null && <DishesSection categoryId={current} showInactive={showInactive} />}
    </div>
  );
}

function CategoryRow({
  category,
  isFirst,
  isLast,
  previous,
  next,
  isSelected,
  swap,
  order,
  onSelect,
}: {
  category: MenuCategory;
  isFirst: boolean;
  isLast: boolean;
  previous: MenuCategory | undefined;
  next: MenuCategory | undefined;
  isSelected: boolean;
  swap: ReturnType<typeof useReorderCategories>;
  /** The ids on screen, in order: a move sends the whole new order, not a pair. */
  order: string[];
  onSelect: () => void;
}): ReactElement {
  /** One request carrying the whole new order — see `FloorPlanScreen` (backlog-issues B3). */
  function swapWith(other: MenuCategory | undefined): void {
    if (other === undefined) {
      return;
    }
    swap.mutate(
      order.map((id) => (id === category.id ? other.id : id === other.id ? category.id : id)),
    );
  }

  return (
    <li className="flex flex-wrap items-center gap-2 p-2">
      <button
        type="button"
        onClick={onSelect}
        // Colour is not the only signal: the selected row is also the one whose dishes are shown
        // below, and it is announced (restaurant-ui rule 5).
        aria-current={isSelected ? 'true' : undefined}
        className={`min-h-target flex-1 rounded-md px-2 text-left ${
          isSelected ? 'bg-accent text-accent-foreground' : ''
        }`}
      >
        {category.name}
        {!category.is_active && (
          <span className="ml-2 rounded-sm bg-neutral-soft px-1.5 py-0.5 text-xs text-neutral">
            {strings.menu.inactive}
          </span>
        )}
      </button>

      <Button
        variant="ghost"
        size="icon"
        aria-label={`${strings.menu.moveUp}: ${category.name}`}
        disabled={isFirst || swap.isPending}
        onClick={() => {
          swapWith(previous);
        }}
      >
        ↑
      </Button>
      <Button
        variant="ghost"
        size="icon"
        aria-label={`${strings.menu.moveDown}: ${category.name}`}
        disabled={isLast || swap.isPending}
        onClick={() => {
          swapWith(next);
        }}
      >
        ↓
      </Button>
    </li>
  );
}

/**
 * A category is named, and its code is derived.
 *
 * The code field used to be here and required, and the code was printed beside every name — the
 * same thing said twice, once for a person and once for the database. The owner removed it from
 * the screens on 2026-09-19, and a form that still asked for one would be asking somebody to
 * invent a value they will never see again. `codeFromName` fills it; `/menu/codes` is where the
 * result can be read when a recipe or an import needs it.
 */
function AddCategory({ existing }: { existing: string[] }): ReactElement {
  const create = useCreateCategory();
  const problems = fieldErrors(create.error);
  const [name, setName] = useState('');

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    create.mutate(
      // Derived once, here, at creation. A rename must never reach this — the code is the join key
      // `library/dishes.yaml` and every M04 recipe use, and a code that followed the name would
      // detach a dish from its recipe the first time somebody fixed a spelling.
      { code: suffixedCode(name.trim(), existing), name: name.trim() },
      {
        onSuccess: () => {
          setName('');
        },
      },
    );
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-wrap items-end gap-2">
      {/* The server can still refuse a code — a collision this client could not see, from
          another tab — so its message has to land somewhere a person will read it. */}
      {problems.code === undefined ? null : (
        <Notice tone="critical" title={problems.code} />
      )}
      <Field
        label={strings.menu.categoryName}
        value={name}
        onChange={(event) => {
          setName(event.target.value);
        }}
        required
        error={problems.name}
      />
      <Button type="submit" disabled={create.isPending || name.trim() === ''}>
        {create.isPending ? strings.menu.creating : strings.menu.addCategory}
      </Button>
      {create.isError && (
        <div className="w-full">
          <Notice
            tone="critical"
            {...errorProps(create.error, {
              code: strings.menu.categoryCode,
              name: strings.menu.categoryName,
            })}
          />
        </div>
      )}
    </form>
  );
}

function DishesSection({
  categoryId,
  showInactive,
}: {
  categoryId: string;
  showInactive: boolean;
}): ReactElement {
  const dishes = useMenuItems(categoryId, showInactive);
  const items = dishes.data?.items ?? [];

  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">{strings.menu.dishesTitle}</h2>
      <QueryState
        isPending={dishes.isPending}
        error={dishes.error}
        pendingLabel={strings.menu.dishesTitle}
      >
        {items.length === 0 ? (
          <p className="text-muted-foreground">{strings.menu.dishesEmpty}</p>
        ) : (
          <ul className="divide-y rounded-md border">
            {items.map((dish) => (
              <DishRow key={dish.id} dish={dish} />
            ))}
          </ul>
        )}
      </QueryState>
    </section>
  );
}

function DishRow({ dish }: { dish: MenuItem }): ReactElement {
  const active = dish.variants.filter((variant) => variant.is_active);

  return (
    <li className="flex flex-wrap items-center gap-3 p-2">
      {/* FSSAI's mark, first, because that is where a diner's eye goes and where a menu prints it. */}
      <FoodTypeMark foodType={dish.food_type} />
      <a href={`/menu/${dish.id}`} className="min-h-target flex-1 rounded-md px-2 py-1">
        {dish.name}
        {!dish.is_active && (
          <span className="ml-2 rounded-sm bg-neutral-soft px-1.5 py-0.5 text-xs text-neutral">
            {strings.menu.inactive}
          </span>
        )}
      </a>
      {/* Every price this dish sells at, right-aligned and tabular: a column of prices is read
          down. `formatINR` is the only thing that turns a rupee string into characters. */}
      <span className="font-mono text-sm tabular-nums">
        {active.length === 0
          ? strings.menu.noVariants
          : active.map((variant) => `${variant.name} ${formatINR(variant.price)}`).join('  ·  ')}
      </span>
    </li>
  );
}
