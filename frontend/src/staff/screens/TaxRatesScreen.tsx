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
import {
  type TaxGroup,
  type TaxRate,
  useAddTaxRate,
  useCreateTaxGroup,
  useTaxGroups,
} from '@staff/api/setup';

/**
 * GST groups and the rates they have charged.
 *
 * **A group is an identity; a rate is a dated row beneath it** (M03 spec decision 1). A menu item
 * points at the group, so changing what it charges never means re-tagging the menu. The screen is
 * shaped to teach that: one card per group, its rate history inside it.
 *
 * **Superseded rates are shown, not hidden.** An invoice from March cites the rate that was
 * effective in March, and someone checking that invoice has to be able to see it. A screen that
 * listed only the current rate would look tidier and make the audit impossible.
 *
 * **There is no edit control on a rate**, because there is no such operation: the rate is copied
 * onto every order line and cited by an invoice, so changing one in place would silently restate tax
 * already charged and reported. Adding the next one is the only path — it closes the current rate
 * the day before the new one starts, in one request, so the two periods cannot drift apart.
 *
 * The date field defaults to the *restaurant's* today, not the browser's. At 01:00 in Pune those are
 * different days, and the server validates against the restaurant's.
 */
export default function TaxRatesScreen(): ReactElement {
  const { session } = useAuth();
  const taxes = useTaxGroups();
  const items = taxes.data?.items ?? [];
  const today =
    session === null || session === undefined
      ? new Date().toISOString().slice(0, 10)
      : businessToday(session.restaurant.timezone, session.restaurant.business_day_start);

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
          <div className="space-y-4">
            {items.map((group) => (
              <TaxGroupCard key={group.id} group={group} today={today} />
            ))}
          </div>
        )}
      </QueryState>

      <AddTaxGroup today={today} />
    </div>
  );
}

function TaxGroupCard({ group, today }: { group: TaxGroup; today: string }): ReactElement {
  const [changing, setChanging] = useState(false);
  // Newest first from the server. The live rate is the one with no end date — there is at most one,
  // enforced by an exclusion constraint rather than by this component's arithmetic.
  const live = group.rates.find((rate) => rate.effective_to === null);

  return (
    <section className="space-y-3 rounded-md border p-page">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold">{group.name}</h2>
          {/* The code is what menu items join on, so it is shown rather than hidden — a person
              reading a recipe or a seed file will see this string and needs to recognise it. */}
          <p className="font-mono text-xs text-muted-foreground">{group.code}</p>
        </div>
        <p className="text-right">
          <span className="font-mono text-2xl">{live === undefined ? '—' : asPercent(live.rate)}</span>
          <span className="ml-2 text-sm text-muted-foreground">
            {live === undefined ? strings.setup.tax.noRates : strings.setup.tax.current}
          </span>
        </p>
      </header>

      <h3 className="text-sm font-medium text-muted-foreground">{strings.setup.tax.history}</h3>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="text-right">{strings.setup.tax.rate}</TableHead>
            <TableHead>{strings.setup.tax.effectiveFrom}</TableHead>
            <TableHead>{strings.setup.tax.effectiveTo}</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {group.rates.map((rate) => (
            <RateRow key={rate.id} rate={rate} />
          ))}
        </TableBody>
      </Table>

      {changing ? (
        <AddTaxRate
          group={group}
          today={today}
          onDone={() => {
            setChanging(false);
          }}
        />
      ) : (
        <Button
          variant="secondary"
          onClick={() => {
            setChanging(true);
          }}
        >
          {strings.setup.tax.supersede}
        </Button>
      )}
    </section>
  );
}

function RateRow({ rate }: { rate: TaxRate }): ReactElement {
  const isCurrent = rate.effective_to === null;

  return (
    <TableRow>
      {/* Right-aligned and tabular: a column of rates is read down. The arithmetic is display-only —
          the rupee value is never computed here (CLAUDE.md invariant 3). */}
      <TableCell className="text-right font-mono">
        {asPercent(rate.rate)}
        {/* Colour is never the only signal (restaurant-ui rule 5) — the state is a word. */}
        <span
          className={`ml-2 rounded-sm px-1.5 py-0.5 text-xs ${
            isCurrent ? 'bg-success-soft text-success' : 'bg-neutral-soft text-neutral'
          }`}
        >
          {isCurrent ? strings.setup.tax.current : strings.setup.tax.superseded}
        </span>
      </TableCell>
      <TableCell className="font-mono">{rate.effective_from}</TableCell>
      <TableCell className="font-mono">{rate.effective_to ?? '—'}</TableCell>
      <TableCell>{rate.is_inclusive ? strings.setup.tax.inclusive : ''}</TableCell>
    </TableRow>
  );
}

/** `"0.0500"` → `"5%"`. Display only, and on a string the server sent — never a rupee amount. */
function asPercent(rate: string): string {
  const value = Number(rate) * 100;
  return `${String(Number(value.toFixed(2)))}%`;
}

/**
 * Parsed before anything is sent, and this is the most important guard on either form.
 *
 * `Number("")` is 0, so submitting with the rate box empty used to create a **0% tax rate** — valid
 * to the server, copied onto every order line, and then impossible to correct because a rate can
 * only be superseded, never edited. Found by external review of M02.
 */
function asFraction(percent: string): string | null {
  const parsed = Number(percent);
  if (!Number.isFinite(parsed) || parsed < 0 || parsed > 100 || percent.trim() === '') {
    return null;
  }
  // Percent in the UI, fraction on the wire, four decimal places because that is the column.
  // Built as a string: parsing to a float and back is how 5% becomes 0.05000000000000001.
  return (parsed / 100).toFixed(4);
}

function AddTaxRate({
  group,
  today,
  onDone,
}: {
  group: TaxGroup;
  today: string;
  onDone: () => void;
}): ReactElement {
  const add = useAddTaxRate();
  const [percent, setPercent] = useState('5');
  const [inclusive, setInclusive] = useState(false);
  const [from, setFrom] = useState(today);

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const rate = asFraction(percent);
    if (rate === null) {
      return;
    }
    add.mutate(
      { id: group.id, body: { rate, is_inclusive: inclusive, effective_from: from } },
      { onSuccess: onDone },
    );
  }

  // No `noValidate`: `required`, `min`, `max` and `step` on the fields below are this form's only
  // validation, and suppressing the browser's check made them decorative — an empty rate box
  // parsed to 0 and created a 0% tax rate that could then never be edited.
  return (
    <form onSubmit={onSubmit} className="space-y-3 rounded-md border border-dashed p-page">
      <Notice tone="info" title={strings.setup.tax.supersedeHint} />

      <div className="flex flex-wrap items-end gap-2">
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
        <Switch
          id={`inclusive-${group.id}`}
          checked={inclusive}
          onCheckedChange={setInclusive}
        />
        <Label htmlFor={`inclusive-${group.id}`}>{strings.setup.tax.inclusive}</Label>
      </div>

      {add.isError && <Notice tone="critical" {...errorProps(add.error)} />}

      <div className="flex gap-2">
        <Button type="submit" disabled={add.isPending}>
          {add.isPending ? strings.setup.floor.creating : strings.setup.tax.supersede}
        </Button>
        <Button type="button" variant="secondary" onClick={onDone}>
          {strings.setup.tax.cancel}
        </Button>
      </div>
    </form>
  );
}

function AddTaxGroup({ today }: { today: string }): ReactElement {
  const create = useCreateTaxGroup();
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [percent, setPercent] = useState('5');
  const [inclusive, setInclusive] = useState(false);
  const [from, setFrom] = useState(today);

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const rate = asFraction(percent);
    if (rate === null) {
      return;
    }
    create.mutate(
      {
        // Uppercased here rather than refused: the server's pattern is `^[A-Z][A-Z0-9_]*$`, and
        // rejecting "gst5" for its case would be a rule the person has no way to know in advance.
        code: code.trim().toUpperCase(),
        name,
        rate,
        is_inclusive: inclusive,
        effective_from: from,
      },
      {
        onSuccess: () => {
          setCode('');
          setName('');
        },
      },
    );
  }

  return (
    <form onSubmit={onSubmit} className="space-y-3 rounded-md border p-page">
      <h2 className="text-lg font-semibold">{strings.setup.tax.add}</h2>
      <p className="text-sm text-muted-foreground">{strings.setup.tax.addGroupHint}</p>

      <div className="flex flex-wrap items-end gap-2">
        <Field
          label={strings.setup.tax.code}
          hint={strings.setup.tax.codeHint}
          value={code}
          onChange={(event) => {
            setCode(event.target.value);
          }}
          required
        />
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

      <Button
        type="submit"
        disabled={create.isPending || name.trim() === '' || code.trim() === ''}
      >
        {create.isPending ? strings.setup.floor.creating : strings.setup.tax.add}
      </Button>
    </form>
  );
}
