import { type ReactElement, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import type { TaskStatus } from '@shared/enums';
import { Permission } from '@shared/permissions';
import { Button } from '@shared/ui/button';
import { AttachmentControl } from '@staff/components/AttachmentControl';
import { Notice } from '@staff/components/Notice';
import { QueryState } from '@staff/components/QueryState';
import { errorProps } from '@staff/components/errorProps';
import { strings } from '@staff/strings';
import { useAuth } from '@staff/auth/AuthContext';
import { type Task, type TaskEvent, useMoveTask, useTask } from '@staff/api/communication';

/**
 * One task, its history, and only the moves this person can actually make.
 *
 * **Nothing is rendered disabled-and-mysterious.** A button somebody cannot press, with no reason
 * given, teaches them the product is broken. So the screen computes the same three questions the
 * server asks — is it mine, may I assign, did I finish it myself — and renders the buttons that
 * would succeed, with a sentence where there are none.
 *
 * **The history reads as a history.** Every transition and every handover, oldest first, with who
 * did it. That is the module's whole reason to exist: a month later, "I never asked you to do
 * that" has an answer.
 *
 * **Sending completed work back asks for a note**, because a refusal with no words is the thing
 * that makes people stop marking work finished.
 */
export default function TaskScreen(): ReactElement {
  const { taskId = '' } = useParams();
  const detail = useTask(taskId);

  return (
    <div className="flex flex-col gap-page p-page">
      {/* Brand §8.7. */}
      <Link to="/tasks" className="text-sm text-muted-foreground" data-back>
        {strings.tasks.backToBoard}
      </Link>
      <QueryState
        isPending={detail.isPending}
        error={detail.error}
        pendingLabel={strings.tasks.detailLoading}
      >
        {detail.data === undefined ? null : (
          <>
            <Header task={detail.data.task} />
            <Moves task={detail.data.task} />
            <AttachmentControl
              ownerType="task"
              ownerId={detail.data.task.id}
              attachments={detail.data.task.attachments}
            />
            <History events={detail.data.events} />
          </>
        )}
      </QueryState>
    </div>
  );
}

function Header({ task }: { task: Task }): ReactElement {
  return (
    <header className="flex flex-col gap-2">
      <h1 className="text-xl font-semibold md:text-2xl">{task.title}</h1>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="rounded-full bg-info-soft px-2 py-0.5 text-xs font-medium text-info">
          {strings.tasks.status[task.status]}
        </span>
        {task.is_overdue ? (
          <span className="rounded-full bg-critical-soft px-2 py-0.5 text-xs font-medium text-critical">
            {strings.tasks.overdue}
          </span>
        ) : null}
        <span className="text-muted-foreground">
          {task.assigned_to_name === null
            ? strings.tasks.unassigned
            : strings.tasks.assignedTo(task.assigned_to_name)}
        </span>
      </div>
      {task.description === null ? null : (
        <p className="whitespace-pre-wrap">{task.description}</p>
      )}
    </header>
  );
}

/** What may follow what, mirrored from the service's own table so the screen offers no dead end. */
const NEXT: Record<TaskStatus, readonly TaskStatus[]> = {
  created: ['cancelled'],
  assigned: ['accepted', 'in_progress', 'cancelled'],
  accepted: ['in_progress', 'completed', 'cancelled'],
  in_progress: ['completed', 'cancelled'],
  completed: ['verified', 'in_progress', 'cancelled'],
  verified: [],
  cancelled: [],
};

/** The moves only the assignee makes. Nobody completes work on somebody else's behalf. */
const ASSIGNEE_ONLY: readonly TaskStatus[] = ['accepted', 'in_progress', 'completed'];

/**
 * The words on the button.
 *
 * `created` and `assigned` are absent on purpose: nothing in the lifecycle moves a task *to*
 * either — it arrives in one and leaves. A `Record` over every status would have needed two
 * sentences nobody would ever read.
 */
function label(to: TaskStatus): string {
  return to === 'created' || to === 'assigned'
    ? strings.tasks.status[to]
    : strings.tasks.move[to];
}

function Moves({ task }: { task: Task }): ReactElement {
  const { session, can } = useAuth();
  const [note, setNote] = useState('');
  const move = useMoveTask();

  const mine = task.assigned_to === session?.employeeId;
  const mayAssign = can(Permission.TASK_ASSIGN);
  const finishedItMyself = task.assigned_to === session?.employeeId;

  const allowed = NEXT[task.status].filter((to) => {
    // Sending completed work back is a refusal to sign it off, so it is the assigner's act rather
    // than the assignee resuming — the server draws the same line.
    if (task.status === 'completed' && to === 'in_progress') {
      return mayAssign;
    }
    if (ASSIGNEE_ONLY.includes(to)) {
      return mine;
    }
    if (to === 'verified') {
      return mayAssign && !finishedItMyself;
    }
    return mayAssign || task.assigned_by === session?.employeeId;
  });

  const sendingBack = task.status === 'completed';

  if (allowed.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        {task.status === 'completed' && finishedItMyself
          ? strings.tasks.verifiedBySomebodyElse
          : strings.tasks.nothingToDo}
      </p>
    );
  }

  return (
    <section className="flex flex-col gap-2">
      {sendingBack && mayAssign ? (
        <>
          <label className="text-sm font-medium" htmlFor="task-note">
            {strings.tasks.noteLabel}
          </label>
          <input
            id="task-note"
            className="min-h-target rounded-md border border-border bg-background px-3 text-base"
            value={note}
            onChange={(event) => { setNote(event.target.value); }}
          />
          <p className="text-xs text-muted-foreground">{strings.tasks.sendBackHint}</p>
        </>
      ) : null}

      <div className="flex flex-wrap gap-2">
        {allowed.map((to) => (
          <Button
            key={to}
            variant={to === 'cancelled' ? 'secondary' : 'primary'}
            disabled={move.isPending}
            onClick={() => {
              move.mutate(
                {
                  taskId: task.id,
                  status: to,
                  ...(note.trim() === '' ? {} : { note }),
                },
                { onSuccess: () => { setNote(''); } },
              );
            }}
          >
            {move.isPending
              ? strings.tasks.moving
              : to === 'in_progress' && task.status === 'completed'
                ? strings.tasks.sendBack
                : label(to)}
          </Button>
        ))}
      </div>

      {move.error === null ? null : <Notice tone="critical" {...errorProps(move.error)} />}
    </section>
  );
}

function History({ events }: { events: TaskEvent[] }): ReactElement {
  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-lg font-medium">{strings.tasks.historyTitle}</h2>
      <ol className="flex flex-col gap-2">
        {events.map((event) => (
          <li key={event.id} className="border-b border-border pb-2 text-sm">
            {strings.tasks.historyEntry(
              event.actor_name ?? '',
              event.to_status === null
                ? (event.note ?? '')
                : strings.tasks.status[event.to_status],
            )}
            {event.to_status !== null && event.note !== null ? (
              <span className="block text-muted-foreground">{event.note}</span>
            ) : null}
          </li>
        ))}
      </ol>
    </section>
  );
}
