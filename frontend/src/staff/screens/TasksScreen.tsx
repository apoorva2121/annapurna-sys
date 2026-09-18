import { type ReactElement, useState } from 'react';
import { Link } from 'react-router-dom';

import type { TaskPriority, TaskStatus } from '@shared/enums';
import { Permission } from '@shared/permissions';
import { Button } from '@shared/ui/button';
import { Notice } from '@staff/components/Notice';
import { QueryState } from '@staff/components/QueryState';
import { errorProps } from '@staff/components/errorProps';
import { strings } from '@staff/strings';
import { useAuth } from '@staff/auth/AuthContext';
import { useEmployees } from '@staff/api/staff';
import { type Task, useCommunicationStream, useCreateTask, useTasks } from '@staff/api/communication';

/**
 * The board: what has been asked for, who has it, and what is late.
 *
 * **Overdue is a word and a colour, never a colour alone**, and it comes from the server — nothing
 * here compares a date to now, because a screen left open overnight would otherwise be wrong in
 * the morning and confidently so.
 *
 * **The assignee picker appears only for `task.assign`.** A disabled control that 403s reads as a
 * bug in the product rather than as a boundary in it, and the P1 design's line is real: writing
 * down your own work is not the same act as giving work out.
 *
 * **Grouped by status rather than sorted by it.** A manager's question is "what is stuck", which a
 * list sorted by date cannot answer at a glance.
 */
const COLUMNS: readonly TaskStatus[] = [
  'created',
  'assigned',
  'accepted',
  'in_progress',
  'completed',
];

export default function TasksScreen(): ReactElement {
  const { can } = useAuth();
  const [mineOnly, setMineOnly] = useState(false);
  const tasks = useTasks(mineOnly);
  useCommunicationStream();

  return (
    <div className="flex flex-col gap-page p-page">
      <h1 className="text-xl font-semibold md:text-2xl">{strings.tasks.title}</h1>

      {can(Permission.TASK_ASSIGN) ? (
        <div className="flex flex-wrap gap-2">
          <Button
            variant={mineOnly ? 'secondary' : 'primary'}
            onClick={() => { setMineOnly(false); }}
          >
            {strings.tasks.allFilter}
          </Button>
          <Button
            variant={mineOnly ? 'primary' : 'secondary'}
            onClick={() => { setMineOnly(true); }}
          >
            {strings.tasks.mineFilter}
          </Button>
        </div>
      ) : null}

      <NewTask />

      <QueryState isPending={tasks.isPending} error={tasks.error} pendingLabel={strings.tasks.loading}>
        {tasks.data === undefined ? null : tasks.data.items.length === 0 ? (
          <p className="text-sm text-muted-foreground">{strings.tasks.empty}</p>
        ) : (
          <div className="flex flex-col gap-page">
            {COLUMNS.map((status) => {
              const inColumn = tasks.data.items.filter((task) => task.status === status);
              if (inColumn.length === 0) {
                return null;
              }
              return (
                <section key={status} className="flex flex-col gap-2">
                  <h2 className="text-lg font-medium">{strings.tasks.status[status]}</h2>
                  <ul className="flex flex-col">
                    {inColumn.map((task) => (
                      <Card key={task.id} task={task} />
                    ))}
                  </ul>
                </section>
              );
            })}
          </div>
        )}
      </QueryState>
    </div>
  );
}

function Card({ task }: { task: Task }): ReactElement {
  return (
    <li className="border-b border-border">
      <Link to={`/tasks/${task.id}`} className="flex min-h-target flex-col justify-center gap-1 py-3">
        <span className="font-medium">{task.title}</span>
        <span className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <span>
            {task.assigned_to_name === null
              ? strings.tasks.unassigned
              : strings.tasks.assignedTo(task.assigned_to_name)}
          </span>
          {task.priority === 'normal' || task.priority === 'low' ? null : (
            <span className="rounded-full bg-warning-soft px-2 py-0.5 text-xs font-medium text-warning">
              {strings.tasks.priority[task.priority]}
            </span>
          )}
          {task.is_overdue ? (
            <span className="rounded-full bg-critical-soft px-2 py-0.5 text-xs font-medium text-critical">
              {strings.tasks.overdue}
            </span>
          ) : null}
        </span>
      </Link>
    </li>
  );
}

function NewTask(): ReactElement {
  const { can } = useAuth();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [assignedTo, setAssignedTo] = useState<string | null>(null);
  const [priority, setPriority] = useState<TaskPriority>('normal');
  const create = useCreateTask();
  const mayAssign = can(Permission.TASK_ASSIGN);
  const people = useEmployees(false);

  if (!open) {
    return (
      <Button variant="secondary" onClick={() => { setOpen(true); }}>
        {strings.tasks.newTitle}
      </Button>
    );
  }

  return (
    <section className="flex flex-col gap-2 border-b border-border pb-4">
      <h2 className="text-lg font-medium">{strings.tasks.newTitle}</h2>

      <label className="text-sm font-medium" htmlFor="task-title">
        {strings.tasks.titleLabel}
      </label>
      <input
        id="task-title"
        className="min-h-target rounded-md border border-border bg-background px-3 text-base"
        value={title}
        onChange={(event) => { setTitle(event.target.value); }}
        placeholder={strings.tasks.titlePlaceholder}
      />

      <label className="text-sm font-medium" htmlFor="task-description">
        {strings.tasks.descriptionLabel}
      </label>
      <textarea
        id="task-description"
        className="min-h-target rounded-md border border-border bg-background px-3 py-2 text-base"
        rows={2}
        value={description}
        onChange={(event) => { setDescription(event.target.value); }}
      />

      <div className="flex flex-wrap gap-2">
        {(['low', 'normal', 'high', 'urgent'] as const).map((level) => (
          <Button
            key={level}
            variant={priority === level ? 'primary' : 'secondary'}
            onClick={() => { setPriority(level); }}
          >
            {strings.tasks.priority[level]}
          </Button>
        ))}
      </div>

      {mayAssign ? (
        <>
          <p className="text-sm font-medium">{strings.tasks.assigneeLabel}</p>
          <div className="flex flex-wrap gap-2">
            <Button
              variant={assignedTo === null ? 'primary' : 'secondary'}
              onClick={() => { setAssignedTo(null); }}
            >
              {strings.tasks.assigneeNobody}
            </Button>
            {(people.data?.pages ?? [])
              .flatMap((page) => page.items)
              .map((person) => (
                <Button
                  key={person.id}
                  variant={assignedTo === person.id ? 'primary' : 'secondary'}
                  onClick={() => { setAssignedTo(person.id); }}
                >
                  {person.full_name}
                </Button>
              ))}
          </div>
        </>
      ) : (
        <p className="text-sm text-muted-foreground">{strings.tasks.assigneeHint}</p>
      )}

      <Button
        disabled={title.trim() === '' || create.isPending}
        onClick={() => {
          create.mutate(
            {
              title,
              ...(description.trim() === '' ? {} : { description }),
              assignedTo,
              priority,
            },
            {
              onSuccess: () => {
                setOpen(false);
                setTitle('');
                setDescription('');
                setAssignedTo(null);
                setPriority('normal');
              },
            },
          );
        }}
      >
        {create.isPending ? strings.tasks.creating : strings.tasks.create}
      </Button>

      {create.error === null ? null : <Notice tone="critical" {...errorProps(create.error)} />}
    </section>
  );
}
