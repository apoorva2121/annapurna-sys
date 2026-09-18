import type { ReactElement } from 'react';

import { Button } from '@shared/ui/button';
import { Notice } from '@staff/components/Notice';
import { QueryState } from '@staff/components/QueryState';
import { WaiterSurface } from '@staff/components/WaiterSurface';
import { errorProps } from '@staff/components/errorProps';
import { strings } from '@staff/strings';
import { type Assignment, useClock, useMyShifts } from '@staff/api/shifts';

/**
 * Your own shifts, and the button this module exists for.
 *
 * **Waiter surface**: a phone, one hand, somebody walking in at eleven in the morning. One primary
 * action — *Clock in* — and it is the largest thing on the screen.
 *
 * **There is no person to choose.** The button acts on your own assignment and the API has no
 * field for anybody else's, which is the module's whole answer to buddy punching: not a permission
 * that could be granted by mistake, but an absence.
 *
 * **A shift that was never clocked out says so and stays open.** Nothing closes it at a guessed
 * time, because M17 normalises per hour worked and a wrong denominator is worse than a missing one
 * — so the screen shows the truth rather than a tidy figure.
 *
 * **The status is the server's word, not this screen's arithmetic.** Late is decided once, at
 * clock-in, against the restaurant's own grace period; a browser comparing two times would be a
 * second implementation of a rule whose point is having one.
 */
export default function MyShiftsScreen(): ReactElement {
  const mine = useMyShifts();

  return (
    <WaiterSurface>
      <div className="flex flex-col gap-page p-page">
        <h1 className="text-xl font-semibold md:text-2xl">{strings.shifts.mineTitle}</h1>
        <QueryState
          isPending={mine.isPending}
          error={mine.error}
          pendingLabel={strings.shifts.loading}
        >
          {mine.data === undefined ? null : mine.data.items.length === 0 ? (
            <p className="text-sm text-muted-foreground">{strings.shifts.mineEmpty}</p>
          ) : (
            <ul className="flex flex-col gap-page">
              {mine.data.items.map((assignment) => (
                <Row
                  key={assignment.id}
                  assignment={assignment}
                  today={mine.data.since}
                />
              ))}
            </ul>
          )}
        </QueryState>
      </div>
    </WaiterSurface>
  );
}

const STATUS_TONE: Record<string, string> = {
  scheduled: 'bg-info-soft text-info',
  present: 'bg-success-soft text-success',
  late: 'bg-warning-soft text-warning',
  absent: 'bg-critical-soft text-critical',
  leave: 'bg-info-soft text-info',
};

function Row({ assignment, today }: { assignment: Assignment; today: string }): ReactElement {
  const clock = useClock();
  // Only today's shift has a button. Clocking in to tomorrow's is refused by the server, and a
  // control that always fails is worse than no control.
  const isToday = assignment.business_date === today;
  const notStarted = assignment.clock_in_at === null;

  return (
    <li className="flex flex-col gap-2 border-b border-border pb-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{assignment.shift_name}</span>
        <span className="text-sm text-muted-foreground tabular-nums">
          {strings.shifts.between(assignment.start_time, assignment.end_time)}
        </span>
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_TONE[assignment.status] ?? ''}`}
        >
          {strings.shifts.status[assignment.status]}
        </span>
        {assignment.is_open ? (
          <span className="rounded-full bg-caution-soft px-2 py-0.5 text-xs font-medium text-caution">
            {strings.shifts.stillOpen}
          </span>
        ) : null}
      </div>
      <p className="text-sm text-muted-foreground tabular-nums">
        {assignment.business_date}
      </p>

      {isToday ? (
        <Button
          disabled={clock.isPending || assignment.clock_out_at !== null}
          onClick={() => {
            clock.mutate({
              assignmentId: assignment.id,
              direction: notStarted ? 'in' : 'out',
            });
          }}
        >
          {clock.isPending
            ? strings.shifts.clocking
            : assignment.clock_out_at !== null
              ? strings.shifts.done
              : notStarted
                ? strings.shifts.clockIn
                : strings.shifts.clockOut}
        </Button>
      ) : null}

      {clock.error === null ? null : <Notice tone="critical" {...errorProps(clock.error)} />}
    </li>
  );
}
