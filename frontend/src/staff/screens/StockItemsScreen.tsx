import { type ReactElement, useState } from 'react';

import { formatINR } from '@shared/money';
import { Permission } from '@shared/permissions';
import { Button } from '@shared/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@shared/ui/table';
import { useAuth } from '@staff/auth/AuthContext';
import { QueryState } from '@staff/components/QueryState';
import { strings } from '@staff/strings';
import { type StockItem, useStockItems, useUsedBy } from '@staff/api/stock';

/**
 * The ingredient and preparation master.
 *
 * **One list, not two**, because ADR 0006's whole move is that an ingredient and a preparation are
 * the same kind of thing: both hold stock, both expire, both have a cost, and a recipe line
 * references either without caring which. Splitting them into two screens would teach the opposite
 * of what the data model says, and a chef looking for "makhani gravy" would have to know in advance
 * which tab it lives on.
 *
 * The filter is there because the two *are* different to work with — a preparation has a batch and
 * a station, an ingredient has a supplier and a purchase unit — but the default is everything.
 *
 * **"What uses this" is the reason anyone opens this screen twice.** "Paneer went up 12%, which
 * dishes changed?" is the question an owner asks the moment a price moves, and it is transitive:
 * paneer is in makhani gravy and makhani gravy is in six dishes.
 */
export default function StockItemsScreen(): ReactElement {
  const [kind, setKind] = useState<'ingredient' | 'preparation' | undefined>(undefined);
  const items = useStockItems(kind);
  const [inspecting, setInspecting] = useState<string | null>(null);
  const rows = items.data?.items ?? [];
  const { can } = useAuth();
  const mayCost = can(Permission.COST_VIEW);

  return (
    <div className="space-y-page">
      <h1 className="text-2xl font-semibold">{strings.stock.title}</h1>
      <p className="text-sm text-muted-foreground">{strings.stock.intro}</p>

      <div className="flex flex-wrap gap-2">
        {(
          [
            [undefined, strings.stock.all],
            ['ingredient', strings.stock.ingredients],
            ['preparation', strings.stock.preparations],
          ] as const
        ).map(([value, label]) => (
          <Button
            key={label}
            variant={kind === value ? 'primary' : 'secondary'}
            aria-pressed={kind === value}
            onClick={() => {
              setKind(value);
            }}
          >
            {label}
          </Button>
        ))}
      </div>

      <QueryState
        isPending={items.isPending}
        error={items.error}
        pendingLabel={strings.stock.title}
      >
        {rows.length === 0 ? (
          <p className="text-muted-foreground">{strings.stock.empty}</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{strings.stock.code}</TableHead>
                <TableHead>{strings.stock.name}</TableHead>
                <TableHead>{strings.stock.baseUnit}</TableHead>
                {/* **Only for a `cost.view` holder.** The API stopped sending the price to a
                    chef, so this column was a row of em dashes for exactly the people
                    `seed/organization.yaml` says see grams and not rupees — noise standing where
                    a boundary is. */}
                {mayCost && <TableHead className="text-right">{strings.stock.unitCost}</TableHead>}
                <TableHead>{strings.stock.shelfLife}</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((item) => (
                <ItemRow
                  key={item.id}
                  item={item}
                  mayCost={mayCost}
                  onInspect={() => {
                    setInspecting(item.id);
                  }}
                />
              ))}
            </TableBody>
          </Table>
        )}
      </QueryState>

      {inspecting !== null && (
        <UsedByPanel
          itemId={inspecting}
          onClose={() => {
            setInspecting(null);
          }}
        />
      )}
    </div>
  );
}

function ItemRow({
  item,
  onInspect,
  mayCost,
}: {
  item: StockItem;
  onInspect: () => void;
  mayCost: boolean;
}): ReactElement {
  return (
    <TableRow>
      <TableCell className="font-mono text-sm">{item.code}</TableCell>
      <TableCell>
        {item.name}
        {/* Which kind it is, as a word. A preparation and an ingredient look identical in a list
            and behave differently in a recipe (ADR 0006 asks the recipe editor to make this
            obvious; the same reasoning applies here). */}
        <span className="ml-2 rounded-sm bg-neutral-soft px-1.5 py-0.5 text-xs text-neutral">
          {item.kind === 'preparation' ? strings.stock.preparations : strings.stock.ingredients}
        </span>
      </TableCell>
      <TableCell className="font-mono text-sm">{item.base_unit}</TableCell>
      {/* Per base unit — per gram, per ml, per piece — so the column is read down and compared. */}
      {mayCost && (
        <TableCell className="text-right font-mono tabular-nums">
          {formatINR(item.current_unit_cost)}
        </TableCell>
      )}
      <TableCell className="text-sm">
        {item.ingredient !== null
          ? strings.stock.days(item.ingredient.shelf_life_days)
          : item.preparation !== null
            ? // Hours, not days, and that is the point of the separate column: raw cream lasts a
              // week and the gravy made from it dies in thirty-six hours (ADR 0006).
              strings.stock.hours(item.preparation.shelf_life_hours)
            : '—'}
      </TableCell>
      <TableCell>
        <Button variant="ghost" onClick={onInspect}>
          {strings.stock.usedBy}
        </Button>
      </TableCell>
    </TableRow>
  );
}

function UsedByPanel({ itemId, onClose }: { itemId: string; onClose: () => void }): ReactElement {
  const usedBy = useUsedBy(itemId);
  const preparations = usedBy.data?.preparations ?? [];
  const dishes = usedBy.data?.dish_names ?? [];

  return (
    <section className="space-y-3 rounded-md border p-page">
      <header className="flex items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">{strings.stock.usedBy}</h2>
        <Button variant="secondary" onClick={onClose}>
          {strings.stock.close}
        </Button>
      </header>

      <QueryState
        isPending={usedBy.isPending}
        error={usedBy.error}
        pendingLabel={strings.stock.usedBy}
      >
        {preparations.length === 0 && dishes.length === 0 ? (
          <p className="text-muted-foreground">{strings.stock.usedByNone}</p>
        ) : (
          <div className="flex flex-wrap gap-8">
            {preparations.length > 0 && (
              <div>
                <h3 className="text-sm font-medium text-muted-foreground">
                  {strings.stock.usedByPreparations}
                </h3>
                <ul className="mt-1 space-y-1">
                  {preparations.map((preparation) => (
                    <li key={preparation.id} className="text-sm">
                      {preparation.name}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {dishes.length > 0 && (
              <div>
                <h3 className="text-sm font-medium text-muted-foreground">
                  {strings.stock.usedByDishes}
                </h3>
                {/* Including dishes that reach this only through a preparation — which is the whole
                    reason this is a walk rather than one query over `recipe_line`. */}
                <ul className="mt-1 space-y-1">
                  {dishes.map((name) => (
                    <li key={name} className="text-sm">
                      {name}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </QueryState>
    </section>
  );
}
