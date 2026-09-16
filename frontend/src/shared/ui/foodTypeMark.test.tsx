// The mark a diner reads before the dish name, and the rule it exists to satisfy.
//
// `docs/ui/conventions.md` rule 5: colour is never the only signal. That rule is load-bearing here
// rather than general — red-green colour blindness is exactly the axis a veg / non-veg mark sits
// on, and a vegetarian who does not eat egg is the person most let down when two of the three marks
// are the same shape in different colours. They were, until the M03/M04 review.

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { FoodTypeMark, type FoodType } from './foodTypeMark';

function shapeOf(foodType: FoodType): string {
  const { unmount } = render(<FoodTypeMark foodType={foodType} />);
  const mark = screen.getByRole('img');
  const inner = mark.querySelector('span');
  const className = inner?.className ?? '';
  unmount();
  // Everything that is not a colour: what is left is the shape.
  return className
    .split(' ')
    .filter((token) => !token.startsWith('bg-'))
    .join(' ');
}

describe('the FSSAI food type mark', () => {
  it('gives each of the three meanings its own shape', () => {
    const shapes = [shapeOf('veg'), shapeOf('non_veg'), shapeOf('egg')];

    expect(new Set(shapes).size).toBe(3);
  });

  it('names itself for a screen reader', () => {
    render(<FoodTypeMark foodType="egg" />);

    expect(screen.getByRole('img')).toHaveAccessibleName('Contains egg');
  });

  // The FSS (Labelling and Display) Regulations, 2020 replaced the older red circle for
  // non-vegetarian with a BROWN TRIANGLE. This codebase adopted the new shape and kept the old
  // colour: the mark was painted `critical`, which is hue 0 — pure red. Half a regulation change.
  //
  // Borrowing an alert token was the second defect underneath the first. `critical` means "this
  // has gone wrong" on all four surfaces (docs/ui/conventions.md). A chicken biryani is not an
  // error, and a kitchen that sees the failure colour on every non-veg ticket learns to read that
  // colour as noise — which is the one thing the locked alert set exists to prevent.
  it('paints each mark from the food tokens, not from the alert set', () => {
    for (const foodType of ['veg', 'non_veg', 'egg'] as const) {
      const { unmount } = render(<FoodTypeMark foodType={foodType} />);
      const mark = screen.getByRole('img');
      const classes = `${mark.className} ${mark.querySelector('span')?.className ?? ''}`;

      expect(classes).toContain(`food-${foodType === 'non_veg' ? 'nonveg' : foodType}`);
      for (const alert of ['critical', 'warning', 'caution', 'info', 'success', 'neutral']) {
        expect(classes).not.toContain(`-${alert}`);
      }
      unmount();
    }
  });
});
