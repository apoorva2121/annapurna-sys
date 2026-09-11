import { type FormEvent, type ReactElement, useState } from 'react';

import { Button } from '@shared/ui/button';
import { Label } from '@shared/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@shared/ui/select';
import { Switch } from '@shared/ui/switch';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@shared/ui/table';
import { Field } from '@staff/components/Field';
import { Notice } from '@staff/components/Notice';
import { QueryState } from '@staff/components/QueryState';
import { errorProps } from '@staff/components/errorProps';
import { strings } from '@staff/strings';
import {
  type DiningArea,
  type RestaurantTable,
  useCreateDiningArea,
  useCreateTable,
  useDiningAreas,
  useTables,
  useUpdateDiningArea,
  useUpdateTable,
} from '@staff/api/setup';

const TABLE_STATUSES: RestaurantTable['status'][] = [
  'free',
  'occupied',
  'reserved',
  'cleaning',
  'out_of_service',
];

/**
 * The floor: dining areas, and the tables in them.
 *
 * **Reordering is buttons, not drag.** The spec says "drag to reorder" and this deliberately does
 * not, for now — recorded in `docs/backlog.md` rather than done quietly. Drag needs a library, and
 * needs a keyboard path built alongside it to be usable at all; buttons are that keyboard path,
 * work with a glove and a steamed-up screen, and reorder the same `seq` the server already
 * understands. Adding drag later is additive and changes no data.
 *
 * Areas are deactivated, never deleted (ADR 0008). The server refuses to deactivate one that still
 * has tables and says how many, so this screen does not need to guess — it shows what came back.
 */
export default function FloorPlanScreen(): ReactElement {
  const [showInactive, setShowInactive] = useState(false);
  const areas = useDiningAreas(showInactive);
  const [selectedArea, setSelectedArea] = useState<string | null>(null);

  const items = areas.data?.items ?? [];
  // The area whose tables are shown. Falls back to the first, so the screen is never empty-looking
  // when there is something to show.
  const current = selectedArea ?? items[0]?.id ?? null;

  return (
    <div className="space-y-page">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold">{strings.setup.floor.title}</h1>
        <div className="flex items-center gap-2">
          <Switch id="show-inactive" checked={showInactive} onCheckedChange={setShowInactive} />
          <Label htmlFor="show-inactive">{strings.setup.floor.showInactive}</Label>
        </div>
      </div>

      <p className="text-sm text-muted-foreground">{strings.setup.floor.neverDeleted}</p>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">{strings.setup.floor.areasTitle}</h2>
        <QueryState
          isPending={areas.isPending}
          error={areas.error}
          pendingLabel={strings.setup.floor.areasTitle}
        >
          {items.length === 0 ? (
            <p className="text-muted-foreground">{strings.setup.floor.areasEmpty}</p>
          ) : (
            <ul className="divide-y rounded-md border">
              {items.map((area, index) => (
                <AreaRow
                  key={area.id}
                  area={area}
                  isFirst={index === 0}
                  isLast={index === items.length - 1}
                  previous={items[index - 1]}
                  next={items[index + 1]}
                  isSelected={area.id === current}
                  onSelect={() => {
                    setSelectedArea(area.id);
                  }}
                />
              ))}
            </ul>
          )}
        </QueryState>
        <AddArea />
      </section>

      {current !== null && <TablesSection areaId={current} areas={items} />}
    </div>
  );
}

function AreaRow({
  area,
  isFirst,
  isLast,
  previous,
  next,
  isSelected,
  onSelect,
}: {
  area: DiningArea;
  isFirst: boolean;
  isLast: boolean;
  previous: DiningArea | undefined;
  next: DiningArea | undefined;
  isSelected: boolean;
  onSelect: () => void;
}): ReactElement {
  const update = useUpdateDiningArea();

  /** Swap this row's `seq` with its neighbour's. Two writes, because `seq` is not unique and the
   *  server has no "move" verb — the neighbour has to take this row's place. */
  function swapWith(other: DiningArea | undefined): void {
    if (other === undefined) {
      return;
    }
    update.mutate({ id: area.id, changes: { seq: other.seq } });
    update.mutate({ id: other.id, changes: { seq: area.seq } });
  }

  return (
    <li className="flex flex-wrap items-center gap-2 p-2">
      <button
        type="button"
        onClick={onSelect}
        // Colour is not the only signal: the selected row is also the one whose tables are shown
        // below, and it is announced (restaurant-ui rule 5).
        aria-current={isSelected ? 'true' : undefined}
        className={`min-h-target flex-1 rounded-md px-2 text-left ${
          isSelected ? 'bg-accent text-accent-foreground' : ''
        }`}
      >
        {area.name}
        {!area.is_active && (
          <span className="ml-2 rounded-sm bg-neutral-soft px-1.5 py-0.5 text-xs text-neutral">
            {strings.setup.floor.inactive}
          </span>
        )}
      </button>

      <Button
        variant="ghost"
        size="icon"
        aria-label={`${strings.setup.floor.moveUp}: ${area.name}`}
        disabled={isFirst || update.isPending}
        onClick={() => {
          swapWith(previous);
        }}
      >
        ↑
      </Button>
      <Button
        variant="ghost"
        size="icon"
        aria-label={`${strings.setup.floor.moveDown}: ${area.name}`}
        disabled={isLast || update.isPending}
        onClick={() => {
          swapWith(next);
        }}
      >
        ↓
      </Button>
      <Button
        variant="ghost"
        onClick={() => {
          update.mutate({ id: area.id, changes: { is_active: !area.is_active } });
        }}
        disabled={update.isPending}
      >
        {area.is_active ? strings.setup.floor.deactivate : strings.setup.floor.reactivate}
      </Button>

      {update.isError && (
        <div className="w-full">
          <Notice tone="critical" {...errorProps(update.error)} />
        </div>
      )}
    </li>
  );
}

function AddArea(): ReactElement {
  const create = useCreateDiningArea();
  const [name, setName] = useState('');

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    create.mutate(
      { name },
      {
        onSuccess: () => {
          setName('');
        },
      },
    );
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-wrap items-end gap-2" noValidate>
      <Field
        label={strings.setup.floor.areaName}
        placeholder={strings.setup.floor.areaNamePlaceholder}
        value={name}
        onChange={(event) => {
          setName(event.target.value);
        }}
        required
      />
      <Button type="submit" disabled={create.isPending || name.trim() === ''}>
        {create.isPending ? strings.setup.floor.creating : strings.setup.floor.addArea}
      </Button>
      {create.isError && (
        <div className="w-full">
          <Notice tone="critical" {...errorProps(create.error)} />
        </div>
      )}
    </form>
  );
}

function TablesSection({ areaId, areas }: { areaId: string; areas: DiningArea[] }): ReactElement {
  const tables = useTables(areaId);
  const items = tables.data?.items ?? [];

  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">{strings.setup.floor.tablesTitle}</h2>
      <QueryState
        isPending={tables.isPending}
        error={tables.error}
        pendingLabel={strings.setup.floor.tablesTitle}
      >
        {items.length === 0 ? (
          <p className="text-muted-foreground">{strings.setup.floor.tablesEmpty}</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{strings.setup.floor.tableCode}</TableHead>
                {/* Numbers right-aligned and tabular, so a column of them can be read down. */}
                <TableHead className="text-right">{strings.setup.floor.seats}</TableHead>
                <TableHead>{strings.setup.floor.status}</TableHead>
                <TableHead>{strings.setup.floor.inArea}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((table) => (
                <TableRowEditor key={table.id} table={table} areas={areas} />
              ))}
            </TableBody>
          </Table>
        )}
      </QueryState>
      <AddTable areaId={areaId} />
    </section>
  );
}

function TableRowEditor({
  table,
  areas,
}: {
  table: RestaurantTable;
  areas: DiningArea[];
}): ReactElement {
  const update = useUpdateTable();

  return (
    <TableRow>
      <TableCell className="font-medium">{table.code}</TableCell>
      <TableCell className="text-right font-mono">{table.seats}</TableCell>
      <TableCell>
        <Select
          value={table.status}
          onValueChange={(status) => {
            update.mutate({
              id: table.id,
              changes: { status: status as RestaurantTable['status'] },
            });
          }}
        >
          <SelectTrigger aria-label={`${strings.setup.floor.status}: ${table.code}`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {TABLE_STATUSES.map((status) => (
              <SelectItem key={status} value={status}>
                {status.replace(/_/g, ' ')}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </TableCell>
      <TableCell>
        <Select
          value={table.dining_area_id}
          onValueChange={(dining_area_id) => {
            update.mutate({ id: table.id, changes: { dining_area_id } });
          }}
        >
          <SelectTrigger aria-label={`${strings.setup.floor.inArea}: ${table.code}`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {areas.map((area) => (
              <SelectItem key={area.id} value={area.id}>
                {area.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {update.isError && <Notice tone="critical" {...errorProps(update.error)} />}
      </TableCell>
    </TableRow>
  );
}

function AddTable({ areaId }: { areaId: string }): ReactElement {
  const create = useCreateTable();
  const [code, setCode] = useState('');
  const [seats, setSeats] = useState('4');

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    create.mutate(
      { dining_area_id: areaId, code, seats: Number(seats) },
      {
        onSuccess: () => {
          setCode('');
        },
      },
    );
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-wrap items-end gap-2" noValidate>
      <Field
        label={strings.setup.floor.tableCode}
        placeholder={strings.setup.floor.tableCodePlaceholder}
        value={code}
        onChange={(event) => {
          setCode(event.target.value);
        }}
        required
      />
      <Field
        label={strings.setup.floor.seats}
        type="number"
        min={1}
        max={100}
        value={seats}
        onChange={(event) => {
          setSeats(event.target.value);
        }}
        required
      />
      <Button type="submit" disabled={create.isPending || code.trim() === ''}>
        {create.isPending ? strings.setup.floor.creating : strings.setup.floor.addTable}
      </Button>
      {create.isError && (
        <div className="w-full">
          <Notice tone="critical" {...errorProps(create.error)} />
        </div>
      )}
    </form>
  );
}
