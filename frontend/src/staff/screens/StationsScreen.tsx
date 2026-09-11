import { type FormEvent, type ReactElement, useState } from 'react';

import { Button } from '@shared/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@shared/ui/table';
import { Field } from '@staff/components/Field';
import { Notice } from '@staff/components/Notice';
import { QueryState } from '@staff/components/QueryState';
import { errorProps } from '@staff/components/errorProps';
import { strings } from '@staff/strings';
import { type Station, useCreateStation, useStations, useUpdateStation } from '@staff/api/setup';

/**
 * The kitchen sections a ticket can be routed to.
 *
 * The screen's whole job is to make one distinction visible: **`code` is permanent and `name` is
 * not.** `seed/menu.yaml` already routes dishes by `tandoor` and `main_kitchen`, and M08 will render
 * one column per station, so renaming a code orphans the routing that points at it. The server has
 * no field to change it; this screen shows the code as text and the name as an input, which is the
 * same rule expressed where someone can see it.
 */
export default function StationsScreen(): ReactElement {
  const stations = useStations(true);
  const items = stations.data?.items ?? [];

  return (
    <div className="max-w-3xl space-y-page">
      <h1 className="text-2xl font-semibold">{strings.setup.stations.title}</h1>

      <QueryState
        isPending={stations.isPending}
        error={stations.error}
        pendingLabel={strings.setup.stations.title}
      >
        {items.length === 0 ? (
          <p className="text-muted-foreground">{strings.setup.stations.empty}</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{strings.setup.stations.code}</TableHead>
                <TableHead>{strings.setup.stations.name}</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((station) => (
                <StationRow key={station.id} station={station} />
              ))}
            </TableBody>
          </Table>
        )}
      </QueryState>

      <AddStation />
    </div>
  );
}

function StationRow({ station }: { station: Station }): ReactElement {
  const update = useUpdateStation();
  const [name, setName] = useState(station.name);
  const changed = name.trim() !== station.name && name.trim() !== '';

  return (
    <TableRow>
      {/* Text, not an input. The code is a contract with the menu — there is no field for it on the
          server either, so an editable-looking box here would be a lie. */}
      <TableCell className="font-mono">{station.code}</TableCell>
      <TableCell>
        <Field
          label={strings.setup.stations.name}
          value={name}
          onChange={(event) => {
            setName(event.target.value);
          }}
        />
      </TableCell>
      <TableCell>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            disabled={!changed || update.isPending}
            onClick={() => {
              update.mutate({ id: station.id, changes: { name: name.trim() } });
            }}
          >
            {strings.setup.tax.renameOnly}
          </Button>
          <Button
            variant="ghost"
            disabled={update.isPending}
            onClick={() => {
              update.mutate({ id: station.id, changes: { is_active: !station.is_active } });
            }}
          >
            {station.is_active ? strings.setup.floor.deactivate : strings.setup.floor.reactivate}
          </Button>
        </div>
        {update.isError && <Notice tone="critical" {...errorProps(update.error)} />}
      </TableCell>
    </TableRow>
  );
}

function AddStation(): ReactElement {
  const create = useCreateStation();
  const [code, setCode] = useState('');
  const [name, setName] = useState('');

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    create.mutate(
      { code, name },
      {
        onSuccess: () => {
          setCode('');
          setName('');
        },
      },
    );
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-wrap items-end gap-2">
      <Field
        label={strings.setup.stations.code}
        hint={strings.setup.stations.codeHint}
        value={code}
        onChange={(event) => {
          // Nudged into shape as it is typed rather than refused on submit: the server's pattern is
          // lower case with underscores, and "Main Kitchen" is what a person naturally types.
          setCode(event.target.value.toLowerCase().replace(/\s+/g, '_'));
        }}
        required
      />
      <Field
        label={strings.setup.stations.name}
        hint={strings.setup.stations.nameHint}
        value={name}
        onChange={(event) => {
          setName(event.target.value);
        }}
        required
      />
      <Button type="submit" disabled={create.isPending || code.trim() === '' || name.trim() === ''}>
        {create.isPending ? strings.setup.floor.creating : strings.setup.stations.add}
      </Button>
      {create.isError && (
        <div className="w-full">
          <Notice tone="critical" {...errorProps(create.error)} />
        </div>
      )}
    </form>
  );
}
