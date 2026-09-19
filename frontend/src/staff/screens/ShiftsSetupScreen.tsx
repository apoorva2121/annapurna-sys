import { type FormEvent, type ReactElement, useState } from 'react';

import { Button } from '@shared/ui/button';
import { Field } from '@staff/components/Field';
import { Notice } from '@staff/components/Notice';
import { QueryState } from '@staff/components/QueryState';
import { errorProps } from '@staff/components/errorProps';
import { useCreateShift, useShifts } from '@staff/api/shifts';
import { strings } from '@staff/strings';

/**
 * The shifts a restaurant runs. Morning, Evening, and whatever else it works.
 *
 * **This screen did not exist until 2026-09-19, and its absence stopped the product being usable
 * by a new restaurant.** `POST /shifts` was built in M12 and `useCreateShift` was written to call
 * it; nothing ever rendered either. The owner found it by trying to put somebody on a shift and
 * getting a button that would not press: with no shifts, the shift list on the roster is empty,
 * so no shift can be chosen, so the button can never enable — and no error appears, because no
 * request is ever made.
 *
 * **The seed hid it from everybody who had looked at this module.** `seed/operations.yaml` creates
 * `MORNING` and `EVENING`, so every test and every demo has shifts. A real restaurant signing up
 * gets none, and had no way to make any. The owner saw it only because their local database had
 * not been fully seeded, which put them accidentally in a new restaurant's position.
 *
 * It matters beyond this screen. **No shift → no roster → no hours worked → no workload score**:
 * `PerformanceRepository.worked()` reads hours from `shift_assignment`, so M12 was unusable and
 * M17 uncomputable, for a reason that is neither module's fault.
 *
 * **A shift may end before it starts**, and that is not an error: an evening shift in a place that
 * closes at two is 17:30 to 00:30 (ADR 0004). The server derives `crosses_midnight` so no screen
 * has to compare two times to know how to say it.
 */
export default function ShiftsSetupScreen(): ReactElement {
  const shifts = useShifts();
  const items = shifts.data?.items ?? [];

  return (
    <div className="max-w-2xl space-y-page">
      <div>
        <h1 className="text-2xl font-semibold">{strings.shifts.setupTitle}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{strings.shifts.setupIntro}</p>
      </div>

      <QueryState
        isPending={shifts.isPending}
        error={shifts.error}
        pendingLabel={strings.shifts.setupTitle}
      >
        {items.length === 0 ? (
          // An empty state that says what will appear and how to make it appear
          // (docs/ui/conventions.md) — the half of the rule the roster screen was missing.
          <Notice tone="info" title={strings.shifts.setupEmpty} />
        ) : (
          <ul className="divide-y rounded-md border">
            {items.map((shift) => (
              <li
                key={shift.id}
                className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 p-3"
              >
                <span className="font-medium">{shift.name}</span>
                <span className="flex flex-wrap items-baseline gap-2">
                  <span className="font-mono text-sm tabular-nums">
                    {shift.start_time.slice(0, 5)}–{shift.end_time.slice(0, 5)}
                  </span>
                  {shift.crosses_midnight && (
                    <span className="rounded-full bg-neutral-soft px-2 py-0.5 text-xs font-medium text-neutral">
                      {strings.shifts.crossesMidnight}
                    </span>
                  )}
                  {!shift.is_active && (
                    <span className="rounded-full bg-neutral-soft px-2 py-0.5 text-xs font-medium text-neutral">
                      {strings.shifts.notInUse}
                    </span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </QueryState>

      <AddShift />
    </div>
  );
}

function AddShift(): ReactElement {
  const create = useCreateShift();
  const [name, setName] = useState('');
  const [startTime, setStartTime] = useState('');
  const [endTime, setEndTime] = useState('');

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    create.mutate(
      { name: name.trim(), startTime, endTime },
      {
        onSuccess: () => {
          setName('');
          setStartTime('');
          setEndTime('');
        },
      },
    );
  }

  const ready = name.trim() !== '' && startTime !== '' && endTime !== '';

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-3 rounded-md border p-page">
      <h2 className="text-lg font-semibold">{strings.shifts.addTitle}</h2>
      <p className="text-sm text-muted-foreground">{strings.shifts.addHint}</p>

      <div className="flex flex-wrap items-end gap-3">
        <Field
          label={strings.shifts.shiftName}
          value={name}
          onChange={(event) => {
            setName(event.target.value);
          }}
          required
        />
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium" htmlFor="shift-start">
            {strings.shifts.startsAt}
          </label>
          <input
            id="shift-start"
            type="time"
            className="min-h-target rounded-md border border-border bg-background px-3 text-base"
            value={startTime}
            onChange={(event) => {
              setStartTime(event.target.value);
            }}
            required
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium" htmlFor="shift-end">
            {strings.shifts.endsAt}
          </label>
          <input
            id="shift-end"
            type="time"
            className="min-h-target rounded-md border border-border bg-background px-3 text-base"
            value={endTime}
            onChange={(event) => {
              setEndTime(event.target.value);
            }}
            required
          />
        </div>
      </div>

      {create.isError && <Notice tone="critical" {...errorProps(create.error)} />}
      {create.isSuccess && <Notice tone="success" title={strings.shifts.added} />}

      <Button type="submit" disabled={!ready || create.isPending} className="self-start">
        {create.isPending ? strings.shifts.adding : strings.shifts.addShift}
      </Button>
    </form>
  );
}
