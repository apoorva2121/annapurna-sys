import { type ReactElement, useState } from 'react';

import { Permission } from '@shared/permissions';
import { Button } from '@shared/ui/button';
import { Notice } from '@staff/components/Notice';
import { QueryState } from '@staff/components/QueryState';
import { errorProps } from '@staff/components/errorProps';
import { strings } from '@staff/strings';
import { useAuth } from '@staff/auth/AuthContext';
import { useEmployees } from '@staff/api/staff';
import { useDiningAreas } from '@staff/api/setup';
import {
  type Assignment,
  useAssign,
  useOnNow,
  useRoster,
  useSetAssignmentStatus,
  useShifts,
} from '@staff/api/shifts';

/**
 * Who is on, and who is on *now*.
 *
 * **Manager surface**: a tablet, interrupted, twenty seconds before service. Two questions on one
 * screen because they are the same person at the same moment — *is tonight covered* and *is it
 * covered right now* — and making them two screens would mean checking one and forgetting the
 * other.
 *
 * **Who is on now comes first**, because a wrong roster is only expensive if it is discovered
 * after service rather than before it. It is also the thing that makes the auto-assigned waiter on
 * an order explicable: the section with one name against it is the one that will be filled in.
 *
 * **"Did not clock in" is rendered as itself.** Somebody who never clocked in stays `scheduled`,
 * and the screen says so rather than inventing an absence — an `absent` nobody asserted is a
 * disciplinary fact with no author, which is why only a person can set one here.
 *
 * **A day is a row of taps.** Filling a week is the job; a form per assignment is how a roster
 * stops being filled in, and a roster nobody fills in is a module that does nothing for M17.
 */
export default function RosterScreen(): ReactElement {
  const { can } = useAuth();
  const roster = useRoster();
  const now = useOnNow();
  const mayManage = can(Permission.SHIFT_MANAGE);

  return (
    <div className="flex flex-col gap-page p-page">
      <h1 className="text-xl font-semibold md:text-2xl">{strings.shifts.rosterTitle}</h1>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-medium">{strings.shifts.onNowTitle}</h2>
        <QueryState isPending={now.isPending} error={now.error} pendingLabel={strings.shifts.loading}>
          {now.data === undefined ? null : now.data.items.length === 0 ? (
            <p className="text-sm text-muted-foreground">{strings.shifts.onNowEmpty}</p>
          ) : (
            <ul className="flex flex-col">
              {now.data.items.map((entry) => (
                <li
                  key={entry.assignment_id}
                  className="flex min-h-target items-center gap-2 border-b border-border"
                >
                  <span className="flex-1 font-medium">{entry.employee_name ?? ''}</span>
                  <span className="text-sm text-muted-foreground">{entry.shift_name}</span>
                  <span className="text-sm text-muted-foreground">
                    {entry.dining_area_id === null ? strings.shifts.noSection : ''}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </QueryState>
      </section>

      {mayManage ? <StaffIt /> : null}

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-medium">{strings.shifts.weekTitle}</h2>
        <QueryState
          isPending={roster.isPending}
          error={roster.error}
          pendingLabel={strings.shifts.loading}
        >
          {roster.data === undefined ? null : roster.data.items.length === 0 ? (
            <p className="text-sm text-muted-foreground">{strings.shifts.rosterEmpty}</p>
          ) : (
            <ul className="flex flex-col">
              {roster.data.items.map((assignment) => (
                <Row key={assignment.id} assignment={assignment} mayManage={mayManage} />
              ))}
            </ul>
          )}
        </QueryState>
      </section>
    </div>
  );
}

const STATUS_TONE: Record<string, string> = {
  scheduled: 'bg-info-soft text-info',
  present: 'bg-success-soft text-success',
  late: 'bg-warning-soft text-warning',
  absent: 'bg-critical-soft text-critical',
  leave: 'bg-info-soft text-info',
};

function Row({
  assignment,
  mayManage,
}: {
  assignment: Assignment;
  mayManage: boolean;
}): ReactElement {
  const mark = useSetAssignmentStatus();
  // The truth, rather than an absence nobody asserted: the day is over, the person was rostered,
  // and no clock-in exists.
  const neverArrived = assignment.status === 'scheduled' && assignment.clock_in_at === null;

  return (
    <li className="flex flex-wrap items-center gap-2 border-b border-border py-3">
      <span className="min-w-24 text-sm text-muted-foreground tabular-nums">
        {assignment.business_date}
      </span>
      <span className="flex-1 font-medium">{assignment.employee_name ?? ''}</span>
      <span className="text-sm text-muted-foreground">{assignment.shift_name}</span>
      <span
        className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_TONE[assignment.status] ?? ''}`}
      >
        {neverArrived ? strings.shifts.didNotClockIn : strings.shifts.status[assignment.status]}
      </span>
      {assignment.is_open ? (
        <span className="rounded-full bg-caution-soft px-2 py-0.5 text-xs font-medium text-caution">
          {strings.shifts.stillOpen}
        </span>
      ) : null}

      {mayManage && assignment.clock_in_at === null ? (
        <Button
          variant="ghost"
          disabled={mark.isPending}
          onClick={() => {
            mark.mutate({ assignmentId: assignment.id, status: 'absent' });
          }}
        >
          {strings.shifts.markAbsent}
        </Button>
      ) : null}

      {mark.error === null ? null : <Notice tone="critical" {...errorProps(mark.error)} />}
    </li>
  );
}

/** Everything the form needs before it can be submitted. */
function ready(employeeId: string | null, shiftId: string | null, day: string): boolean {
  return employeeId !== null && shiftId !== null && day !== '';
}

/** Anything with an id and a name, as something to choose between. */
function named(
  rows: { id: string; name?: string; full_name?: string }[],
): { id: string; name: string }[] {
  return rows.map((row) => ({ id: row.id, name: row.name ?? row.full_name ?? '' }));
}

/**
 * A row of named things to choose between.
 *
 * Four of these make up the staffing form, and writing them out four times put `StaffIt` over the
 * complexity budget — which is the budget doing its job: choosing a person, a shift and a section
 * are the same act three times, and only the day is different.
 */
function Choices({
  label,
  options,
  chosen,
  onChoose,
}: {
  label: string;
  options: { id: string | null; name: string }[];
  chosen: string | null;
  onChoose: (id: string | null) => void;
}): ReactElement {
  return (
    <>
      <p className="text-sm font-medium">{label}</p>
      <div className="flex flex-wrap gap-2">
        {options.map((option) => (
          <Button
            key={option.id ?? 'none'}
            variant={chosen === option.id ? 'primary' : 'secondary'}
            onClick={() => { onChoose(option.id); }}
          >
            {option.name}
          </Button>
        ))}
      </div>
    </>
  );
}

/**
 * Open it, or show the button that opens it.
 *
 * Split from the form itself because the two together were over the complexity budget — and the
 * split is the honest one: this decides whether the form is on screen, and the form decides what
 * goes in it.
 */
function StaffIt(): ReactElement {
  const [open, setOpen] = useState(false);
  if (!open) {
    return (
      <Button variant="secondary" onClick={() => { setOpen(true); }}>
        {strings.shifts.staffTitle}
      </Button>
    );
  }
  return <StaffForm />;
}

/**
 * Why the button below cannot be pressed.
 *
 * The button is disabled until a person, a shift and a day are all chosen — correct, and it was
 * silent. With no shifts defined the shift list is empty, `shiftId` stays `null`, and the button
 * can never be enabled: clicking did nothing and no error appeared, because no request was ever
 * made. An owner spent an evening on that on 2026-09-19.
 *
 * Its own component because `StaffForm` went over eslint's complexity budget the moment two
 * conditions were added — the budget doing its job rather than an inconvenience.
 *
 * `docs/ui/conventions.md`: an empty state says what will appear and how to make it appear. A
 * disabled control is only honest if something on screen explains it.
 */
type ListState = { ready: boolean; any: boolean };

function WhyNothingCanBeStaffed({
  shifts,
  staff,
}: {
  shifts: ListState;
  staff: ListState;
}): ReactElement {
  // Each list answers for itself as soon as *it* has loaded, rather than both waiting on the
  // slower one — a notice that appears late reads as a flicker.
  const missing = shifts.ready && !shifts.any;
  const nobody = staff.ready && !staff.any;
  return (
    <>
      {missing ? <Notice tone="info" title={strings.shifts.noShiftsYet} /> : null}
      {nobody ? <Notice tone="info" title={strings.shifts.noStaffYet} /> : null}
    </>
  );
}

/** One row of taps: a person, a shift, a day, a section. */
function StaffForm(): ReactElement {
  const [employeeId, setEmployeeId] = useState<string | null>(null);
  const [shiftId, setShiftId] = useState<string | null>(null);
  const [areaId, setAreaId] = useState<string | null>(null);
  const [day, setDay] = useState('');
  const shifts = useShifts();
  const areas = useDiningAreas();
  const people = useEmployees(false);
  const assign = useAssign();

  const staff = named((people.data?.pages ?? []).flatMap((page) => page.items));
  const shiftOptions = named(shifts.data?.items ?? []);
  const sections = [
    { id: null, name: strings.shifts.noSection },
    ...named(areas.data?.items ?? []),
  ];

  return (
    <section className="flex flex-col gap-2 border-b border-border pb-4">
      <h2 className="text-lg font-medium">{strings.shifts.staffTitle}</h2>

      <WhyNothingCanBeStaffed
        shifts={{ ready: !shifts.isPending, any: shiftOptions.length > 0 }}
        staff={{ ready: !people.isPending, any: staff.length > 0 }}
      />

      <Choices
        label={strings.shifts.whoLabel}
        options={staff}
        chosen={employeeId}
        onChoose={setEmployeeId}
      />
      <Choices
        label={strings.shifts.whichShiftLabel}
        options={shiftOptions}
        chosen={shiftId}
        onChoose={setShiftId}
      />
      <Choices
        label={strings.shifts.sectionLabel}
        options={sections}
        chosen={areaId}
        onChoose={setAreaId}
      />

      <label className="text-sm font-medium" htmlFor="roster-day">
        {strings.shifts.dayLabel}
      </label>
      <input
        id="roster-day"
        type="date"
        className="min-h-target rounded-md border border-border bg-background px-3 text-base"
        value={day}
        onChange={(event) => { setDay(event.target.value); }}
      />
      {/* Invariant 4, said to a person rather than to a reader of the schema. */}
      <p className="text-xs text-muted-foreground">{strings.shifts.dayHint}</p>

      <Button
        // Disabled at its limit rather than hidden, so nothing shifts under a thumb.
        disabled={!ready(employeeId, shiftId, day) || assign.isPending}
        onClick={() => {
          if (employeeId === null || shiftId === null) {
            return;
          }
          assign.mutate(
            { shiftId, employeeId, businessDate: day, diningAreaId: areaId },
            { onSuccess: () => { setEmployeeId(null); } },
          );
        }}
      >
        {assign.isPending ? strings.shifts.staffing : strings.shifts.staff}
      </Button>

      {assign.error === null ? null : <Notice tone="critical" {...errorProps(assign.error)} />}
    </section>
  );
}
