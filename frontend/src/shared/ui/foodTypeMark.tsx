import type { ReactElement } from 'react';

/**
 * The veg / non-veg / egg mark that Indian menus are legally required to carry.
 *
 * FSSAI mandates the declaration, and every diner in India reads it before reading the dish name.
 * A dropdown that says "veg" is not what the regulation means and is not what a customer looks
 * for: the mark is a coloured shape inside a bordered square.
 *
 * The Food Safety and Standards (Labelling and Display) Regulations, 2020 prescribe **green for
 * vegetarian and brown for non-vegetarian** — the brown triangle replaced the older red circle.
 * This component adopted the new shape but kept the old colour for some time, painting the mark
 * from `--critical` (hue 0, pure red) until an audit against the 2020 regulations caught it. The
 * colours now come from their own locked `--food-*` tokens: prescribed by regulation, not ours to
 * theme, and not the alert set, because a chicken biryani is not an error.
 *
 * The **egg** mark is rendered in amber by convention so a vegetarian who does not eat egg can
 * tell at a glance. Treat that as a product decision, not a statutory one: a distinct egg mark has
 * been the subject of FSSAI proposals, but its notified status could not be confirmed, so no
 * amendment is cited here. The three-value enum is right regardless — the need is real.
 *
 * **Colour is never the only signal** (`docs/ui/conventions.md`, restaurant-ui rule 5). Commercial
 * kitchens are full of colour-blind men and steamed-up screens, and this mark in particular is one
 * a colour-blind diner has a real stake in. So it carries an accessible label as well, and all
 * three shapes differ: a circle for veg, a triangle for non-veg, a square for egg. Red-green
 * colour blindness is precisely the axis this mark sits on, which makes shape non-optional here
 * rather than a nicety — and veg and egg shared a shape until the M03/M04 review, which left the
 * one distinction a vegetarian most needs carried by hue alone.
 */

export type FoodType = 'veg' | 'non_veg' | 'egg';

const MARKS: Record<FoodType, { label: string; border: string; fill: string; shape: string }> = {
  veg: {
    label: 'Vegetarian',
    border: 'border-food-veg',
    fill: 'bg-food-veg',
    shape: 'rounded-full',
  },
  non_veg: {
    label: 'Non-vegetarian',
    border: 'border-food-nonveg',
    fill: 'bg-food-nonveg',
    // A triangle, so the mark is distinguishable without colour at all.
    shape: '[clip-path:polygon(50%_0%,100%_100%,0%_100%)]',
  },
  egg: {
    label: 'Contains egg',
    border: 'border-food-egg',
    fill: 'bg-food-egg',
    // **A square, because a circle was already taken.** Veg and egg were both `rounded-full` and
    // differed only in hue — green against amber, which is the one axis red-green colour blindness
    // removes. So the distinction a vegetarian who does not eat egg most needs was the distinction
    // this mark could not make, on a mark whose whole purpose is to make it. Found by the M03/M04
    // review. Three meanings, three shapes: circle, triangle, square.
    shape: 'rounded-none',
  },
};

export function FoodTypeMark({
  foodType,
  className = '',
}: {
  foodType: FoodType;
  className?: string;
}): ReactElement {
  const mark = MARKS[foodType];
  return (
    <span
      // `title` for a mouse, `aria-label` for a screen reader, and `role="img"` so the label is
      // read as the thing it is rather than skipped as decoration.
      role="img"
      aria-label={mark.label}
      title={mark.label}
      className={`inline-flex h-4 w-4 shrink-0 items-center justify-center border ${mark.border} ${className}`}
    >
      <span className={`h-2 w-2 ${mark.fill} ${mark.shape}`} />
    </span>
  );
}
