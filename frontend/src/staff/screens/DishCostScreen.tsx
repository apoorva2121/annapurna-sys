import { type ReactElement, useState } from 'react';

import { formatINR } from '@shared/money';
import { Button } from '@shared/ui/button';
import { Link } from 'react-router-dom';

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@shared/ui/table';
import { QueryState } from '@staff/components/QueryState';
import { strings } from '@staff/strings';
import { type MenuCostRow, useDishCost, useMenuCosts } from '@staff/api/stock';

/**
 * What every dish costs, and what it earns. **The day-1 screen.**
 *
 * `docs/audit/2026-09-11-findings.md`: *"Build the day-1 dish-margin screen in M04, not M13."* It is
 * the first thing this product can tell an owner that they did not already know, and it needs no
 * orders, no history and no machine learning — only a menu and a recipe. The demo rests on it: the
 * seed plants Chilli Paneer at ~46% food cost precisely so this screen has something to find.
 *
 * **Worst first, never alphabetical.** Somebody opening this is looking for the dish that is losing
 * money. An alphabetical list makes them read all thirty-six rows to find it.
 *
 * **A dish with no recipe says so, and does not say ₹0.00.** A zero reads as a dish that is free to
 * make, which is both wrong and the opposite of the truth — an uncosted dish is the one nobody can
 * make a decision about.
 *
 * **A cost computed from an unconfirmed recipe is labelled.** `library/PROVENANCE.md` is explicit
 * that most of the starter library is `estimated`: a chef has not checked those quantities. A screen
 * that presented a matched recipe's cost with the same confidence as a chef-written one would be
 * stating a number nobody has earned.
 */
export default function DishCostScreen(): ReactElement {
  const costs = useMenuCosts();
  const [open, setOpen] = useState<string | null>(null);
  const rows = costs.data?.rows ?? [];

  return (
    <div className="space-y-page">
      <h1 className="text-2xl font-semibold">{strings.cost.title}</h1>
      <p className="text-sm text-muted-foreground">{strings.cost.intro}</p>

      <QueryState isPending={costs.isPending} error={costs.error} pendingLabel={strings.cost.title}>
        {rows.length === 0 ? (
          <p className="text-muted-foreground">{strings.cost.empty}</p>
        ) : (
          <>
            <Summary
              average={costs.data?.average_food_cost_percent ?? null}
              dishes={rows.length}
              uncosted={costs.data?.uncosted ?? 0}
            />

            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{strings.cost.dish}</TableHead>
                  <TableHead className="text-right">{strings.cost.price}</TableHead>
                  <TableHead className="text-right">{strings.cost.cost}</TableHead>
                  <TableHead className="text-right">{strings.cost.foodCost}</TableHead>
                  <TableHead className="text-right">{strings.cost.margin}</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) => (
                  <CostRow
                    key={row.menu_item_variant_id}
                    row={row}
                    isOpen={open === row.menu_item_variant_id}
                    onToggle={() => {
                      setOpen(open === row.menu_item_variant_id ? null : row.menu_item_variant_id);
                    }}
                  />
                ))}
              </TableBody>
            </Table>
          </>
        )}
      </QueryState>
    </div>
  );
}

function Summary({
  average,
  dishes,
  uncosted,
}: {
  average: string | null;
  dishes: number;
  uncosted: number;
}): ReactElement {
  return (
    <div className="flex flex-wrap gap-6 rounded-md border p-page">
      <Figure label={strings.cost.averageFoodCost} value={average === null ? '—' : `${average}%`} />
      <Figure label={strings.cost.dishesCosted} value={String(dishes)} />
      <Figure
        label={strings.cost.uncosted}
        value={String(uncosted)}
        tone={uncosted > 0 ? 'warning' : undefined}
      />
    </div>
  );
}

function Figure({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: 'warning' | undefined;
}): ReactElement {
  return (
    <div>
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className={`font-mono text-2xl tabular-nums ${tone === 'warning' ? 'text-warning' : ''}`}>
        {value}
      </p>
    </div>
  );
}

/**
 * Above this, a dish is losing more of its price to ingredients than a restaurant can carry.
 *
 * 35% is the line `seed/validate.py` and `docs/seed-data.md` work to: a target around 26% with
 * anything past 40 flagged outright. It is a rule of thumb and it is stated as one — the row says
 * "high", not "bad", because a loss-leader can be deliberate and the screen does not know which.
 */
const HIGH_FOOD_COST = 35;
// Above this a dish costs more to make than it is sold for, which is a different kind of news
// from an expensive dish and says so in a different word (owner defect sheet row 23).
const SOLD_AT_A_LOSS = 100;

function CostRow({
  row,
  isOpen,
  onToggle,
}: {
  row: MenuCostRow;
  isOpen: boolean;
  onToggle: () => void;
}): ReactElement {
  return (
    <>
      <TableRow>
        <TableCell>
          {row.menu_item_name}
          <span className="ml-2 text-sm text-muted-foreground">{row.variant_name}</span>
          {!row.recipe_confirmed && row.has_recipe && (
            // The label `library/PROVENANCE.md` requires. A cost from an unchecked recipe is a
            // proposal, and saying so is the difference between a number and a claim.
            <span className="ml-2 whitespace-nowrap rounded-sm bg-caution-soft px-1.5 py-0.5 text-xs text-caution">
              {strings.cost.unconfirmed}
            </span>
          )}
        </TableCell>
        <TableCell className="text-right font-mono tabular-nums">{formatINR(row.price)}</TableCell>
        <TableCell className="text-right font-mono tabular-nums">
          {row.has_recipe ? formatINR(row.cost) : '—'}
        </TableCell>
        <TableCell className="text-right font-mono tabular-nums">
          <FoodCost value={row.food_cost_percent} />
        </TableCell>
        {/* A loss printed its minus sign on one line and its figure on the next, which reads as
            a positive number under a stray dash. The sign belongs to the number. */}
        <TableCell className="whitespace-nowrap text-right font-mono tabular-nums">
          {row.has_recipe ? formatINR(row.margin) : '—'}
        </TableCell>
        <TableCell>
          {/* One row, not two: Breakdown and Recipe wrapped out of line with each other. */}
          <div className="flex flex-nowrap items-center gap-2">
            {row.has_recipe && (
              <Button variant="ghost" onClick={onToggle} aria-expanded={isOpen}>
                {isOpen ? strings.cost.hideBreakdown : strings.cost.showBreakdown}
              </Button>
            )}
            {/* The one action this screen should offer. An owner reading a worst-first margin list
                wants to change the dish that is losing money, and the recipe is where that starts —
                a dish with no recipe most of all, which is why the link is not conditional. */}
            <Link
              className="self-center text-info underline"
              to={`/recipes/${row.menu_item_variant_id}`}
            >
              {strings.cost.openRecipe}
            </Link>
          </div>
        </TableCell>
      </TableRow>
      {isOpen && <BreakdownRow variantId={row.menu_item_variant_id} />}
    </>
  );
}

function FoodCost({ value }: { value: string | null }): ReactElement {
  const percent = value === null ? null : Number(value);
  const atALoss = percent !== null && percent > SOLD_AT_A_LOSS;
  const isHigh = percent !== null && percent > HIGH_FOOD_COST && !atALoss;
  if (percent === null) {
    // Never "0%" — that reads as a dish that is free to make, which is the opposite of what an
    // uncosted dish means.
    return <span className="text-muted-foreground">{strings.cost.noRecipe}</span>;
  }
  return (
    <>
      {percent}%{/* Colour is not the only signal (restaurant-ui rule 5) — "high" is a word. */}
      {isHigh && (
        <span className="ml-2 whitespace-nowrap rounded-sm bg-critical-soft px-1.5 py-0.5 text-xs text-critical">
          {strings.cost.high}
        </span>
      )}
      {atALoss && (
        <span className="ml-2 whitespace-nowrap rounded-sm bg-critical-soft px-1.5 py-0.5 text-xs text-critical">
          {strings.cost.atALoss}
        </span>
      )}
    </>
  );
}

function BreakdownRow({ variantId }: { variantId: string }): ReactElement {
  const cost = useDishCost(variantId);

  return (
    <TableRow>
      <TableCell colSpan={6} className="bg-muted/40">
        <QueryState
          isPending={cost.isPending}
          error={cost.error}
          pendingLabel={strings.cost.breakdown}
        >
          {/* The breakdown is the product. "₹126.70" is not actionable; "₹63 of it is the chicken
              tikka" is what an owner uses when the price of chicken moves. */}
          <ul className="space-y-1">
            {(cost.data?.lines ?? []).map((line) => (
              <li key={line.component_id} className="flex justify-between gap-4 text-sm">
                {/* The name, not the code. This line used to read `PREP_CHICKEN_TIKKA`, while
                    the comment above said the point was "₹63 of it is the chicken tikka" — the one
                    sentence a code cannot say. Found on 2026-09-20 by the test written for F11,
                    which flagged this screen and was then told to exempt it; the exemption said
                    the API sent no name. It does now. */}
                <span>{line.name}</span>
                <span className="text-muted-foreground">{line.quantity}</span>
                <span className="font-mono tabular-nums">{formatINR(line.cost)}</span>
              </li>
            ))}
          </ul>
        </QueryState>
      </TableCell>
    </TableRow>
  );
}
