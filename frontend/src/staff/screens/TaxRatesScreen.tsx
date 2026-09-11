import { type FormEvent, type ReactElement, useState } from 'react';

import { businessToday } from '@shared/businessDay';
import { Button } from '@shared/ui/button';
import { Label } from '@shared/ui/label';
import { Switch } from '@shared/ui/switch';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@shared/ui/table';
import { Field } from '@staff/components/Field';
import { Notice } from '@staff/components/Notice';
import { QueryState } from '@staff/components/QueryState';
import { errorProps } from '@staff/components/errorProps';
import { useAuth } from '@staff/auth/AuthContext';
import { strings } from '@staff/strings';
import { type TaxGroup, useCreateTaxGroup, useTaxGroups } from '@staff/api/setup';

/**
 * GST rates, past and present.
 *
 * **Superseded rows are shown, not hidden.** An invoice from March cites the rate that was effective
 * in March, and someone checking that invoice has to be able to see it. A screen that listed only
 * the current rate would look tidier and make the audit impossible.
 *
 * **There is no edit control on a rate**, because there is no such operation: the rate is copied
 * onto every order line and cited by an invoice, so changing one in place would silently restate tax
 * already charged and reported. Replacing is the only path — it closes the old row the day before
 * the new one starts, in one request, so the two periods cannot drift apart.
 *
 * The date field defaults to the *restaurant's* today, not the browser's. At 01:00 in Pune those are
 * different days, and the server validates against the restaurant's.
 */
export default function TaxRatesScreen(): ReactElement {
  const { session } = useAuth();
  const taxes = useTaxGroups();
  const [supersede, setSupersede] = useState<TaxGroup | null>(null);
  const items = taxes.data?.items ?? [];

  return (
    <div className="max-w-3xl space-y-page">
      <h1 className="text-2xl font-semibold">{strings.setup.tax.title}</h1>
      <p className="text-sm text-muted-foreground">{strings.setup.tax.immutable}</p>

      <QueryState
        isPending={taxes.isPending}
        error={taxes.error}
        pendingLabel={strings.setup.tax.title}
      >
        {items.length === 0 ? (
          <p className="text-muted-foreground">{strings.setup.tax.empty}</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{strings.setup.tax.name}</TableHead>
                <TableHead className="text-right">{strings.setup.tax.rate}</TableHead>
                <TableHead>{strings.setup.tax.effectiveFrom}</TableHead>
                <TableHead>{strings.setup.tax.effectiveTo}</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((group) => (
                <TaxRow
                  key={group.id}
                  group={group}
                  onSupersede={() => {
                    setSupersede(group);
                  }}
                />
              ))}
            </TableBody>
          </Table>
        )}
      </QueryState>

      <AddTaxRate
        supersedes={supersede}
        today={
          session === null || session === undefined
            ? new Date().toISOString().slice(0, 10)
            : businessToday(session.restaurant.timezone, session.restaurant.business_day_start)
        }
        onDone={() => {
          setSupersede(null);
        }}
      />
    </div>
  );
}

function TaxRow({
  group,
  onSupersede,
}: {
  group: TaxGroup;
  onSupersede: () => void;
}): ReactElement {
  const isCurrent = group.effective_to === null;

  return (
    <TableRow>
      <TableCell className="font-medium">
        {group.name}
        {/* Colour is never the only signal (restaurant-ui rule 5) — the state is a word. */}
        <span
          className={`ml-2 rounded-sm px-1.5 py-0.5 text-xs ${
            isCurrent ? 'bg-success-soft text-success' : 'bg-neutral-soft text-neutral'
          }`}
        >
          {isCurrent ? strings.setup.tax.current : strings.setup.tax.superseded}
        </span>
      </TableCell>
      {/* Right-aligned and tabular: a column of rates is read down. The arithmetic is display-only —
          the rupee value is never computed here (CLAUDE.md invariant 3). */}
      <TableCell className="text-right font-mono">{asPercent(group.rate)}</TableCell>
      <TableCell className="font-mono">{group.effective_from}</TableCell>
      <TableCell className="font-mono">{group.effective_to ?? '—'}</TableCell>
      <TableCell>
        {isCurrent && (
          <Button variant="secondary" onClick={onSupersede}>
            {strings.setup.tax.supersede}
          </Button>
        )}
      </TableCell>
    </TableRow>
  );
}

/** `"0.0500"` → `"5%"`. Display only, and on a string the server sent — never a rupee amount. */
function asPercent(rate: string): string {
  const value = Number(rate) * 100;
  return `${String(Number(value.toFixed(2)))}%`;
}

function AddTaxRate({
  supersedes,
  today,
  onDone,
}: {
  supersedes: TaxGroup | null;
  today: string;
  onDone: () => void;
}): ReactElement {
  const create = useCreateTaxGroup();
  const [name, setName] = useState('');
  const [percent, setPercent] = useState('5');
  const [inclusive, setInclusive] = useState(false);
  const [from, setFrom] = useState(today);

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    // Parsed before anything else, and this is the most important guard on the screen.
    // `Number("")` is 0, so submitting with the rate box empty used to create a **0% tax rate** —
    // valid to the server, copied onto every order line, and then impossible to correct because a
    // rate can only be superseded, never edited. Found by external review.
    const parsed = Number(percent);
    if (!Number.isFinite(parsed) || parsed < 0 || parsed > 100 || percent.trim() === '') {
      return;
    }
    create.mutate(
      {
        name,
        // Percent in the UI, fraction on the wire, four decimal places because that is the column.
        // Built as a string: parsing to a float and back is how 5% becomes 0.05000000000000001.
        rate: (parsed / 100).toFixed(4),
        is_inclusive: inclusive,
        effective_from: from,
        ...(supersedes === null ? {} : { supersedes_id: supersedes.id }),
      },
      {
        onSuccess: () => {
          setName('');
          onDone();
        },
      },
    );
  }

  // No `noValidate`: `required`, `min`, `max` and `step` on the fields below are this form's only
  // validation, and suppressing the browser's check made them decorative — an empty rate box
  // parsed to 0 and created a 0% tax rate that could then never be edited.
  return (
    <form onSubmit={onSubmit} className="space-y-3 rounded-md border p-page">
      <h2 className="text-lg font-semibold">
        {supersedes === null ? strings.setup.tax.add : strings.setup.tax.supersede}
      </h2>
      {supersedes !== null && <Notice tone="info" title={strings.setup.tax.supersedeHint} />}

      <div className="flex flex-wrap items-end gap-2">
        <Field
          label={strings.setup.tax.name}
          value={name}
          onChange={(event) => {
            setName(event.target.value);
          }}
          required
        />
        <Field
          label={strings.setup.tax.ratePercent}
          hint={strings.setup.tax.rateHint}
          type="number"
          min={0}
          max={100}
          step="0.01"
          value={percent}
          onChange={(event) => {
            setPercent(event.target.value);
          }}
          required
        />
        <Field
          label={strings.setup.tax.effectiveFrom}
          type="date"
          value={from}
          min={today}
          onChange={(event) => {
            setFrom(event.target.value);
          }}
          required
        />
      </div>

      <div className="flex items-center gap-2">
        <Switch id="tax-inclusive" checked={inclusive} onCheckedChange={setInclusive} />
        <Label htmlFor="tax-inclusive">{strings.setup.tax.inclusive}</Label>
      </div>

      {create.isError && <Notice tone="critical" {...errorProps(create.error)} />}

      <Button type="submit" disabled={create.isPending || name.trim() === ''}>
        {create.isPending ? strings.setup.floor.creating : strings.setup.tax.add}
      </Button>
    </form>
  );
}
