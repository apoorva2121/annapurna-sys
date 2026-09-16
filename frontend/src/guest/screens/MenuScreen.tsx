import { type ReactElement, useEffect, useState } from 'react';

import { formatINR } from '@shared/money';

import { type GuestItem, type GuestMenu, fetchMenu } from '../api';
import { strings } from '../strings';

/**
 * The menu, as a diner reads it.
 *
 * **One filter, and it is veg-only** (`docs/ui/brand.md` §7.1, from the competitor research the
 * backlog asked for before this module). A vegetarian scrolling a long menu is not reading labels,
 * they are looking for what they can eat — and both major Indian delivery apps give that as a
 * control rather than only as a mark. A second filter is where a three-tap surface becomes an app.
 *
 * **The food-type mark is not the filter.** It sits beside every dish name, in a shape and a word,
 * because `docs/compliance-rules.md` §A1 requires the mark and because colour never carries meaning
 * alone.
 *
 * **Nothing internal is here, and that is structural rather than careful**: this screen renders
 * `app/schemas/guest.py`, and suite 5 refuses any field named like an internal one — which is how
 * two leaks that had been in the schema since M03 were found.
 */
export function MenuScreen(): ReactElement {
  const [menu, setMenu] = useState<GuestMenu | null>(null);
  const [failed, setFailed] = useState(false);
  const [vegOnly, setVegOnly] = useState(false);

  useEffect(() => {
    fetchMenu()
      .then(setMenu)
      .catch(() => {
        setFailed(true);
      });
  }, []);

  if (failed) {
    return <p className="text-base text-muted-foreground">{strings.scan.offlineBody}</p>;
  }
  if (menu === null) {
    return <p className="text-base text-muted-foreground">{strings.menu.loading}</p>;
  }
  if (menu.categories.length === 0) {
    return <p className="text-base text-muted-foreground">{strings.menu.empty}</p>;
  }

  return (
    <section className="flex flex-col gap-6">
      <label className="flex min-h-target items-center gap-3 text-base">
        <input
          type="checkbox"
          className="size-5"
          checked={vegOnly}
          onChange={(event) => {
            setVegOnly(event.target.checked);
          }}
        />
        {strings.menu.vegOnly}
      </label>

      {menu.categories.map((category) => {
        const items = vegOnly
          ? category.items.filter((item) => item.food_type === 'veg')
          : category.items;
        if (items.length === 0) {
          return null;
        }
        return (
          <div key={category.id} className="flex flex-col gap-3">
            <h2 className="text-lg font-semibold">{category.name}</h2>
            {items.map((item) => (
              <Dish key={item.id} item={item} />
            ))}
          </div>
        );
      })}
    </section>
  );
}

function Dish({ item }: { item: GuestItem }): ReactElement {
  return (
    <article className="flex flex-col gap-1 border-b border-border pb-3">
      <div className="flex items-start justify-between gap-3">
        <h3 className="flex items-center gap-2 text-base font-medium">
          <FoodTypeMark type={item.food_type} />
          {item.name}
        </h3>
        <span className="shrink-0 whitespace-nowrap text-base tabular-nums">
          {formatINR(item.variants[0]?.price ?? '0.00')}
        </span>
      </div>
      {item.description === null ? null : (
        <p className="text-sm text-muted-foreground">{item.description}</p>
      )}
      {item.allergen_statement === null ? null : (
        <p className="text-sm">
          <span className="font-medium">{strings.menu.allergenHeading}: </span>
          {item.allergen_statement}
        </p>
      )}
      {item.calories_kcal === null ? null : (
        <p className="text-sm text-muted-foreground tabular-nums">
          {strings.menu.caloriesLabel(item.calories_kcal, item.serving_size)}
        </p>
      )}
      {item.variants.length > 1 ? (
        <ul className="flex flex-col gap-1 pt-1">
          {item.variants.map((variant) => (
            <li key={variant.id} className="flex justify-between text-sm">
              <span>{variant.name}</span>
              <span className="tabular-nums">{formatINR(variant.price)}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </article>
  );
}

/**
 * The mark `docs/compliance-rules.md` §A1 requires: a square for vegetarian, a triangle for
 * non-vegetarian, in the locked colours — with the word alongside for a screen-reader and for
 * anybody who does not read the shape.
 */
function FoodTypeMark({ type }: { type: 'veg' | 'non_veg' | 'egg' }): ReactElement {
  const tone =
    type === 'veg' ? 'border-success text-success' : type === 'egg' ? 'border-caution text-caution' : 'border-critical text-critical';
  return (
    <span
      className={`inline-flex size-4 shrink-0 items-center justify-center rounded-sm border-2 ${tone}`}
      aria-label={strings.menu.foodType[type]}
      title={strings.menu.foodType[type]}
    >
      <span className="size-1.5 rounded-full bg-current" />
    </span>
  );
}
