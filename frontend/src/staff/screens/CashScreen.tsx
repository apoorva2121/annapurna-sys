import { Fragment, type ReactElement, useState } from 'react';

import { formatINR, parseAmount } from '@shared/money';
import { Button } from '@shared/ui/button';
import { useIdempotencyKey } from '@shared/useIdempotencyKey';
import { Field } from '@staff/components/Field';
import { Notice } from '@staff/components/Notice';
import { QueryState } from '@staff/components/QueryState';
import { errorProps } from '@staff/components/errorProps';
import { strings } from '@staff/strings';
import {
  type CashCount,
  type Till,
  type TillSummary,
  useAdjustment,
  useCashOutsideTill,
  useCloseTill,
  useOpenTill,
  usePayout,
  useTills,
} from '@staff/api/cash';
import { type Person, describePerson } from '@staff/api/people';

/**
 * The till, on the manager's tablet: open it, pay out of it, count it, and correct it afterwards.
 *
 * **The count is blind.** While a till is open this screen shows the float and what was paid out —
 * things the person at the drawer did themselves — and not what the till *should* hold. Expected
 * cash and the variance appear only once the count is recorded. `GoodsReceiptScreen` holds the same
 * rule for weights, for the reason `docs/waste-model.md` gives: a figure to aim at, shown while
 * somebody is still counting, is a figure some people will count towards.
 *
 * **Every figure is the server's.** Expected cash, the variance and the adjusted variance arrive as
 * strings and are shown; "short" or "over" is read from the variance's sign, never from a subtraction
 * here (CLAUDE.md invariant 3). What this screen sends is only what somebody counted or handed out.
 *
 * **A shortfall is never corrected away.** An adjustment is a new row, recorded by somebody other than
 * whoever closed the till, and the original variance stays on screen beside the adjusted one.
 */
export default function CashScreen(): ReactElement {
  const tills = useTills();
  const [justClosed, setJustClosed] = useState<Till | null>(null);
  const items = tills.data?.items ?? [];
  const open = items.find((till) => till.status === 'open');
  const closed = items.filter((till) => till.status === 'closed');
  // Newest first and one open till at a time, so the open till is always on this first page. Older
  // closed tills may not be, and the screen says so rather than letting the list look complete.
  const older = (tills.data?.next_cursor ?? null) !== null;
  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <h1 className="text-2xl font-semibold">{strings.cash.title}</h1>
      <OutsideTill />
      {justClosed !== null && justClosed.variance !== null && (
        <Notice tone="success" title={strings.cash.closedNotice}>
          {`${strings.cash.countedAgainst(
            formatINR(justClosed.counted_cash),
            formatINR(justClosed.expected_cash),
          )} · ${varianceWord(justClosed.variance)}`}
        </Notice>
      )}
      <QueryState
        isPending={tills.isPending}
        error={tills.error}
        pendingLabel={strings.cash.loading}
      >
        {open === undefined ? (
          <OpenTill
            onOpened={() => {
              setJustClosed(null);
            }}
          />
        ) : (
          <OpenTillPanel till={open} onClosed={setJustClosed} />
        )}
        {closed.length > 0 && <ClosedTills tills={closed} />}
        {older && <p className="text-sm text-muted-foreground">{strings.cash.olderTills}</p>}
      </QueryState>
    </div>
  );
}

const ZERO = /^-?0+(\.0+)?$/;

/** "Short by ₹400.00", "Over by ₹20.00" or "Exact", read from the sign of the server's figure. */
function varianceWord(variance: string): string {
  if (ZERO.test(variance)) {
    return strings.cash.exact;
  }
  return variance.startsWith('-')
    ? strings.cash.short(formatINR(variance.slice(1)))
    : strings.cash.over(formatINR(variance));
}

function OpenTill({ onOpened }: { onOpened: () => void }): ReactElement {
  const openTill = useOpenTill();
  const [float, setFloat] = useState('');
  const [problem, setProblem] = useState<string | null>(null);

  function onOpen(): void {
    const amount = parseAmount(float);
    setProblem(amount === null ? strings.cash.floatNeeded : null);
    if (amount === null) {
      return;
    }
    openTill.mutate({ openingFloat: amount }, { onSuccess: onOpened });
  }

  return (
    <section className="flex flex-col gap-3">
      <p className="text-muted-foreground">{strings.cash.noneOpen}</p>
      {problem !== null && <Notice tone="critical" title={problem} />}
      {openTill.isError && <Notice tone="critical" {...errorProps(openTill.error)} />}
      <Field
        label={strings.cash.openingFloat}
        hint={strings.cash.openingFloatHint}
        inputMode="decimal"
        value={float}
        onChange={(event) => {
          setFloat(event.target.value);
        }}
      />
      <div className="flex justify-end">
        <Button size="lg" disabled={openTill.isPending} onClick={onOpen}>
          {openTill.isPending ? strings.cash.opening : strings.cash.open}
        </Button>
      </div>
    </section>
  );
}

function OpenTillPanel({
  till,
  onClosed,
}: {
  till: TillSummary;
  onClosed: (till: Till) => void;
}): ReactElement {
  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-lg font-semibold">{strings.cash.openFor(till.business_date)}</h2>
      <dl className="grid grid-cols-2 gap-y-2">
        {[
          { label: strings.cash.openingFloat, value: till.opening_float },
          { label: strings.cash.payoutsSoFar, value: till.payouts },
        ].map((row) => (
          <Fragment key={row.label}>
            <dt>{row.label}</dt>
            <dd className="text-right font-mono tabular-nums">{formatINR(row.value)}</dd>
          </Fragment>
        ))}
      </dl>
      <p className="text-sm text-muted-foreground">{strings.cash.blindNote}</p>
      <MovementForm tillId={till.id} kind="payout" />
      <CloseForm tillId={till.id} onClosed={onClosed} />
    </section>
  );
}

function MovementForm({
  tillId,
  kind,
}: {
  tillId: string;
  kind: 'payout' | 'adjustment';
}): ReactElement {
  const payout = usePayout();
  const adjustment = useAdjustment();
  const mutation = kind === 'payout' ? payout : adjustment;
  // One key per movement: kept across a second tap, renewed once the movement is recorded.
  const submission = useIdempotencyKey();
  const text = kind === 'payout' ? strings.cash.payout : strings.cash.adjustment;
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState('');
  const [problem, setProblem] = useState<string | null>(null);
  const [recorded, setRecorded] = useState(false);
  // Decision D18: found or missing is a choice, and the amount is always typed as a positive figure.
  const [direction, setDirection] = useState<'found' | 'missing'>('found');

  function onRecord(): void {
    const typed = parseAmount(amount);
    const parsed =
      typed !== null && kind === 'adjustment' && direction === 'missing' ? `-${typed}` : typed;
    const found =
      parsed === null
        ? text.amountProblem
        : reason.trim().length < 3
          ? strings.cash.reasonNeeded
          : null;
    setProblem(found);
    if (parsed === null || found !== null) {
      return;
    }
    mutation.mutate(
      { tillId, amount: parsed, reason: reason.trim(), idempotencyKey: submission.key },
      {
        onSuccess: () => {
          submission.renew();
          setAmount('');
          setReason('');
          setRecorded(true);
        },
      },
    );
  }

  return (
    <section className="flex flex-col gap-2 rounded-lg border border-border p-4">
      <h3 className="font-semibold">{text.title}</h3>
      <p className="text-sm text-muted-foreground">{text.hint}</p>
      {problem !== null && <Notice tone="critical" title={problem} />}
      {mutation.isError && <Notice tone="critical" {...errorProps(mutation.error)} />}
      {recorded && <Notice tone="success" title={text.recorded} />}
      {kind === 'adjustment' && (
        <fieldset className="flex flex-col">
          <legend className="text-sm font-medium">{strings.cash.adjustment.which}</legend>
          {(['found', 'missing'] as const).map((choice) => (
            <label key={choice} className="flex min-h-target items-center gap-3">
              <input
                type="radio"
                name={`adjustment-${tillId}`}
                checked={direction === choice}
                onChange={() => {
                  setDirection(choice);
                }}
              />
              {choice === 'found' ? strings.cash.adjustment.found : strings.cash.adjustment.missing}
            </label>
          ))}
        </fieldset>
      )}
      <Field
        label={text.amount}
        inputMode="decimal"
        value={amount}
        onChange={(event) => {
          setRecorded(false);
          setAmount(event.target.value);
        }}
      />
      <Field
        label={strings.cash.reason}
        value={reason}
        onChange={(event) => {
          setRecorded(false);
          setReason(event.target.value);
        }}
      />
      <div className="flex justify-end">
        <Button variant="secondary" disabled={mutation.isPending} onClick={onRecord}>
          {mutation.isPending ? strings.cash.recording : text.record}
        </Button>
      </div>
    </section>
  );
}

// Rupee notes and coins, largest first. The server accepts any denomination up to ₹2,000; these are
// the boxes offered so nobody has to type one.
const DENOMINATIONS = ['2000', '500', '200', '100', '50', '20', '10', '5', '2', '1'];

const WHOLE = /^\d+$/;

/** The counts to send, or the problem to show instead. A box left empty means none of that kind. */
function countsOrProblem(typed: Record<string, string>): CashCount[] | string {
  const entered = DENOMINATIONS.filter((denomination) => (typed[denomination] ?? '').trim() !== '');
  if (entered.length === 0) {
    return strings.cash.countNeeded;
  }
  const counts: CashCount[] = [];
  for (const denomination of entered) {
    const count = (typed[denomination] ?? '').trim();
    if (!WHOLE.test(count)) {
      return strings.cash.wholeCount(denomination);
    }
    // A count of notes, not an amount of money: converting it to a number is safe.
    counts.push({ denomination: `${denomination}.00`, quantity: Number(count) });
  }
  return counts;
}

function CloseForm({
  tillId,
  onClosed,
}: {
  tillId: string;
  onClosed: (till: Till) => void;
}): ReactElement {
  const close = useCloseTill();
  const [typed, setTyped] = useState<Record<string, string>>({});
  const [problem, setProblem] = useState<string | null>(null);

  function onClose(): void {
    const counts = countsOrProblem(typed);
    if (typeof counts === 'string') {
      setProblem(counts);
      return;
    }
    setProblem(null);
    close.mutate({ tillId, counts }, { onSuccess: onClosed });
  }

  return (
    <section className="flex flex-col gap-2 rounded-lg border border-border p-4">
      <h3 className="font-semibold">{strings.cash.closeTitle}</h3>
      <p className="text-sm text-muted-foreground">{strings.cash.closeHint}</p>
      {problem !== null && <Notice tone="critical" title={problem} />}
      {close.isError && <Notice tone="critical" {...errorProps(close.error)} />}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {DENOMINATIONS.map((denomination) => (
          <Field
            key={denomination}
            label={strings.cash.countOf(denomination)}
            inputMode="numeric"
            value={typed[denomination] ?? ''}
            onChange={(event) => {
              setTyped((current) => ({ ...current, [denomination]: event.target.value }));
            }}
          />
        ))}
      </div>
      <div className="flex justify-end">
        <Button size="lg" disabled={close.isPending} onClick={onClose}>
          {close.isPending ? strings.cash.closing : strings.cash.close}
        </Button>
      </div>
    </section>
  );
}

function ClosedTills({ tills }: { tills: TillSummary[] }): ReactElement {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold">{strings.cash.closedTitle}</h2>
      <ul className="flex flex-col gap-3">
        {tills.map((till) => (
          <ClosedTill key={till.id} till={till} />
        ))}
      </ul>
    </section>
  );
}

function ClosedTill({ till }: { till: TillSummary }): ReactElement {
  const [adjusting, setAdjusting] = useState(false);
  const adjusted = till.adjusted_variance !== null && !ZERO.test(till.adjustments);
  return (
    <li className="flex flex-col gap-2 rounded-lg border border-border p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-semibold">{strings.cash.businessDay(till.business_date)}</p>
          <p className="text-sm">
            {strings.cash.countedAgainst(
              formatINR(till.counted_cash),
              formatINR(till.expected_cash),
            )}
          </p>
          {(till.closed_by_person ?? null) !== null && (
            <p className="text-sm text-muted-foreground">
              {strings.cash.closedBy(describePerson(till.closed_by_person as Person))}
            </p>
          )}
          {(till.adjusted_by ?? []).map((person) => (
            <p key={person.employee_code} className="text-sm text-muted-foreground">
              {strings.cash.adjustedBy(describePerson(person), person.by_closer)}
            </p>
          ))}
        </div>
        <div className="text-right">
          {till.variance !== null && <p className="font-semibold">{varianceWord(till.variance)}</p>}
          {adjusted && till.adjusted_variance !== null && (
            <p className="text-sm">
              {strings.cash.afterAdjustments(varianceWord(till.adjusted_variance))}
            </p>
          )}
        </div>
      </div>
      {adjusting ? (
        <MovementForm tillId={till.id} kind="adjustment" />
      ) : (
        <Button
          variant="ghost"
          onClick={() => {
            setAdjusting(true);
          }}
        >
          {strings.cash.adjust}
        </Button>
      )}
    </li>
  );
}

/** Decision D3 (backlog-issues B7). Said only when there is some: an empty line every evening would
 *  teach people to stop reading it. */
function OutsideTill(): ReactElement | null {
  const outside = useCashOutsideTill();
  const payments = outside.data?.payments ?? 0;
  if (outside.data === undefined || payments === 0) {
    return null;
  }
  return (
    <Notice tone="info" title={strings.cash.outsideTill(formatINR(outside.data.cash_taken))}>
      {strings.cash.outsideTillHint(payments)}
    </Notice>
  );
}
